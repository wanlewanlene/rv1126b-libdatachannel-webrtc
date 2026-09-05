// ============================================================================
// RV1126B 板卡端: 接收浏览器反向推流 (WebRTC) 并实时播放
// 架构: 浏览器(摄像头+麦克风) --H.264+Opus RTP--> libdatachannel (接收/解包)
//       --> GStreamer appsrc --> mppvideodec 硬解 --> rkximagesink (MIPI 屏)
//       --> opusdec --> ALSA 喇叭
// 信令: 复用现有 Node 信令 (viewer 角色, answerer), 与正向推流共用协议
//
// 注: 板卡 GStreamer webrtcbin 的 action 信号经 PyGObject 调用存在缺陷
//     (set-remote-description 静默失效), 故采用与正向推流一致的 libdatachannel。
//
// 编译:
//   g++ -O2 -std=c++17 reverse_player.cpp -o reverse_player \
//       -I/userdata/rtc/ldc_install/include \
//       -L/userdata/rtc/lib -ldatachannel \
//       $(pkg-config --cflags --libs gstreamer-1.0 gstreamer-app-1.0) -pthread
// ============================================================================

#include <rtc/rtc.hpp>
#include <rtc/websocket.hpp>
#include <rtc/h264rtpdepacketizer.hpp>
#include <rtc/rtpdepacketizer.hpp>
#include <rtc/rtcpreceivingsession.hpp>

#include <gst/gst.h>
#include <gst/app/gstappsrc.h>

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstring>
#include <ctime>
#include <deque>
#include <functional>
#include <iostream>
#include <map>
#include <memory>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

static std::atomic<bool> g_running{true};
static void onSigint(int) { g_running = false; }

// 本地 SSRC (offer 中已声明, 浏览器回显后无实际意义, 仅用于 RTCP 反馈的 sender)
static constexpr uint32_t SRC_VIDEO = 42;
static constexpr uint32_t SRC_AUDIO = 43;

// 时钟辅助: 秒(带小数), 基于墙钟 (与浏览器 NTP 近同步, 板卡运行 NTP)
static double nowSecs() {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}

// 网络序 32 位读写
static uint32_t rd32be(const uint8_t* p) { return (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) | (uint32_t(p[2]) << 8) | p[3]; }
static void wr32be(uint8_t* p, uint32_t v) {
    p[0] = uint8_t(v >> 24); p[1] = uint8_t(v >> 16); p[2] = uint8_t(v >> 8); p[3] = uint8_t(v);
}

// ----------------------------------------------------------------------------
// GStreamer 解码显示管道 (appsrc 动态喂数据)
// ----------------------------------------------------------------------------
class MediaPipeline {
public:
    // 统计 (主循环每秒打印)
    std::atomic<uint64_t> v_frames{0}, v_bytes{0}, a_frames{0}, a_bytes{0};
    std::atomic<uint64_t> dec_frames{0};   // mppvideodec 输出帧计数
    std::atomic<bool> v_overflow{false};
    std::atomic<bool> v_open{false}, a_open{false};   // track open 状态诊断
    // OSD 指标 (由 RTP 质量监控线程更新, 主循环读)
    std::atomic<int> osd_fps{0};          // 实时帧率
    std::atomic<int> osd_lat_ms{-1};      // 估算网络单向延迟(ms), -1=无数据
    std::atomic<bool> osd_warn_lat{false};// 延迟超阈值提醒
    std::atomic<int> osd_loss_pct{0};     // 丢包率估算(0-100)

    bool start() {
        gst_init(nullptr, nullptr);

        // 视频: H264 Annex-B -> 硬解 -> 缩放到屏 1024x600
        // 决定性实测: videoconvert+videoscale(640x360->1024x600 CPU转换)只能跑 ~7fps,
        // 是慢动作的真正根因 (gst-launch 对照: 有转换 6.5fps / 无转换 29fps)
        // 去掉转换缩放, mppvideodec 直连 rkximagesink (NV12 协商可行, 实验E已验证)
        // REVERSE_FAKESINK=1 时用 fakesink 替代显示 (诊断用)
        const char* nodisp = std::getenv("REVERSE_FAKESINK");
        std::string sink = (nodisp && nodisp[0] == '1')
            ? "fakesink silent=true" : "rkximagesink sync=false";
        std::string vdesc =
            "appsrc name=vsrc is-live=true do-timestamp=false format=time "
            "max-bytes=16777216 "
            "caps=video/x-h264,stream-format=(string)byte-stream "
            "! h264parse ! mppvideodec name=dec "
            "! " + sink;

        // 音频: Opus -> 解码 -> 喇叭
        std::string adesc =
            "appsrc name=asrc is-live=true do-timestamp=true format=time "
            "max-bytes=1048576 "
            "caps=audio/x-opus,channel-mapping-family=0,channels=2,rate=48000 "
            "! opusdec ! audioconvert ! audioresample "
            "! autoaudiosink sync=false";

        vpipe_ = gst_parse_launch(vdesc.c_str(), nullptr);
        apipe_ = gst_parse_launch(adesc.c_str(), nullptr);
        if (!vpipe_ || !apipe_) {
            std::cerr << "[gst] 管道创建失败" << std::endl;
            return false;
        }

        vsrc_ = gst_bin_get_by_name(GST_BIN(vpipe_), "vsrc");
        asrc_ = gst_bin_get_by_name(GST_BIN(apipe_), "asrc");
        tov_  = gst_bin_get_by_name(GST_BIN(vpipe_), "tov");

        // 诊断: 统计解码器实际输出帧率 (对比输入帧率判断板卡解码是否瓶颈)
        GstElement* dec = gst_bin_get_by_name(GST_BIN(vpipe_), "dec");
        if (dec) {
            GstPad* srcpad = gst_element_get_static_pad(dec, "src");
            if (srcpad) {
                gst_pad_add_probe(srcpad, GST_PAD_PROBE_TYPE_BUFFER,
                    [](GstPad*, GstPadProbeInfo* info, gpointer data) -> GstPadProbeReturn {
                        static_cast<MediaPipeline*>(data)->dec_frames++;
                        return GST_PAD_PROBE_OK;
                    }, this, nullptr);
                gst_object_unref(srcpad);
            }
            gst_object_unref(dec);
        }
        if (!tov_) std::cerr << "[gst] 警告: textoverlay 未创建 (OSD 不可用)" << std::endl;
        else setOsa("[init] 等待视频流...");

        // 统计线程: 每 500ms 更新 OSD 帧率/延迟
        osd_stop_ = false;
        osd_thread_ = std::thread([this]() {
            uint64_t last = 0;
            auto lastT = std::chrono::steady_clock::now();
            while (!osd_stop_.load()) {
                std::this_thread::sleep_for(std::chrono::milliseconds(500));
                auto now = std::chrono::steady_clock::now();
                double dt = std::chrono::duration<double>(now - lastT).count();
                if (dt < 0.4) continue;
                uint64_t cur = v_frames.load();
                int fps = int(double(cur - last) / dt + 0.5);
                last = cur; lastT = now;
                osd_fps.store(fps);

                char buf[128];
                int lat = osd_lat_ms.load();
                int loss = osd_loss_pct.load();
                bool wlat = osd_warn_lat.load();
                if (lat < 0)
                    snprintf(buf, sizeof buf, "FPS: %d   延迟: --   丢包: %d%%", fps, loss);
                else if (wlat)
                    snprintf(buf, sizeof buf, "FPS: %d   延迟: %dms !!!   丢包: %d%%", fps, lat, loss);
                else
                    snprintf(buf, sizeof buf, "FPS: %d   延迟: %dms   丢包: %d%%", fps, lat, loss);
                setOsa(buf);
            }
        });

        // 总线监听: 打印管道错误/警告 (否则 mppvideodec 协商失败等无法察觉)
        installBusWatch(vpipe_, "video");
        installBusWatch(apipe_, "audio");

        GstStateChangeReturn r1 = gst_element_set_state(vpipe_, GST_STATE_PLAYING);
        GstStateChangeReturn r2 = gst_element_set_state(apipe_, GST_STATE_PLAYING);
        std::cout << "[gst] video pipe -> " << r1 << ", audio pipe -> " << r2 << std::endl;
        return true;
    }

    void pushVideo(const uint8_t* data, size_t len, double ptsSec = -1.0) {
        if (!vsrc_) return;
        pushBuffer(vsrc_, data, len, ptsSec, [&](bool ok){ if (!ok) v_overflow = true; });
        v_frames++; v_bytes += len;
    }

    void pushAudio(const uint8_t* data, size_t len) {
        if (!asrc_) return;
        pushBuffer(asrc_, data, len, -1.0, nullptr);
        a_frames++; a_bytes += len;
    }

    void setOsa(const char* text) {
        if (tov_) g_object_set(tov_, "text", text, nullptr);
    }

    ~MediaPipeline() {
        osd_stop_ = true;
        if (osd_thread_.joinable()) osd_thread_.join();
        if (vpipe_) { gst_element_set_state(vpipe_, GST_STATE_NULL); gst_object_unref(vpipe_); }
        if (apipe_) { gst_element_set_state(apipe_, GST_STATE_NULL); gst_object_unref(apipe_); }
    }

private:
    static void installBusWatch(GstElement* pipe, const char* tag) {
        GstBus* bus = gst_element_get_bus(pipe);
        gst_bus_add_watch(bus, [](GstBus*, GstMessage* msg, gpointer data) -> gboolean {
            const char* t = static_cast<const char*>(data);
            GError* err = nullptr; gchar* dbg = nullptr;
            switch (GST_MESSAGE_TYPE(msg)) {
                case GST_MESSAGE_ERROR:
                    gst_message_parse_error(msg, &err, &dbg);
                    std::cerr << "[bus:" << t << "] ERROR " << GST_OBJECT_NAME(msg->src)
                              << ": " << (err ? err->message : "?") << " (" << (dbg ? dbg : "") << ")" << std::endl;
                    if (err) g_error_free(err); g_free(dbg);
                    break;
                case GST_MESSAGE_WARNING:
                    gst_message_parse_warning(msg, &err, &dbg);
                    std::cerr << "[bus:" << t << "] WARN " << GST_OBJECT_NAME(msg->src)
                              << ": " << (err ? err->message : "?") << std::endl;
                    if (err) g_error_free(err); g_free(dbg);
                    break;
                default: break;
            }
            return TRUE;
        }, g_strdup(tag));
        gst_object_unref(bus);
    }

    void pushBuffer(GstElement* src, const uint8_t* data, size_t len, double ptsSec,
                    const std::function<void(bool)>& onErr) {
        GstBuffer* buf = gst_buffer_new_allocate(nullptr, len, nullptr);
        gst_buffer_fill(buf, 0, data, len);
        if (ptsSec >= 0)
            GST_BUFFER_PTS(buf) = GstClockTime(ptsSec * GST_SECOND);
        GstFlowReturn ret = GST_FLOW_OK;
        g_signal_emit_by_name(src, "push-buffer", buf, &ret);
        gst_buffer_unref(buf);
        if (ret != GST_FLOW_OK && onErr) onErr(false);
    }

    GstElement* vpipe_ = nullptr;
    GstElement* apipe_ = nullptr;
    GstElement* vsrc_ = nullptr;
    GstElement* asrc_ = nullptr;
    GstElement* tov_ = nullptr;
    std::thread osd_thread_;
    std::atomic<bool> osd_stop_{false};
    std::atomic<int> capture_count_{0};
};

// ----------------------------------------------------------------------------
// PC 级媒体处理器: 直接处理解密后的 RTP (绕过 track SSRC 路由/track open 限制)
// libdatachannel 的预添加本地 track 从不被 openTracks() 打开, track.onMessage 永不
// 触发; 而 PC 级 MediaHandler 在 forwardMedia 中先于 SSRC 路由执行, 100% 可达。
// ----------------------------------------------------------------------------
// 经基类指针分发调用 (子类 incoming 为 private 时唯一的合法调用方式)
class DepackChain final : public rtc::MediaHandler {
public:
    explicit DepackChain(std::shared_ptr<rtc::MediaHandler> h) : h_(std::move(h)) {}
    void incoming(rtc::message_vector &messages,
                  const rtc::message_callback &send) override {
        h_->incoming(messages, send);
    }
private:
    std::shared_ptr<rtc::MediaHandler> h_;
};

class ReverseMediaHandler final : public rtc::MediaHandler {
public:
    explicit ReverseMediaHandler(MediaPipeline* media)
        : media_(media),
          vdepack_(std::make_shared<DepackChain>(std::make_shared<rtc::H264RtpDepacketizer>(
              rtc::NalUnit::Separator::LongStartSequence))),
          adepack_(std::make_shared<DepackChain>(std::make_shared<rtc::OpusRtpDepacketizer>())) {}

    void incoming(rtc::message_vector &messages,
                  const rtc::message_callback &send) override {
        send_ = send;   // 保存用于发 RTCP 反馈 (NACK/PLI)
        for (auto &m : messages) {
            if (m->size() < 4) continue;

            if (m->type == rtc::Message::Control) {
                parseRtcp(m);                    // SR -> 时间基准; 其余忽略
                continue;
            }
            if (m->size() < 12) continue;

            uint8_t pt = std::to_integer<uint8_t>(m->data()[1]) & 0x7F;
            if (pt == 96) {
                onVideoRtp(m);                   // 丢包检测/延迟估算
                rtc::message_vector one;
                one.push_back(m);
                vdepack_->incoming(one, send_);
                for (auto &f : one)
                    if (!f->empty()) {
                        // 决定性实测结论: 带 PTS(33ms 递增)时 mppvideodec 按 PTS 节流输出
                        // (30fps 输入仅 7fps 输出 -> 慢动作+延迟持续累积);
                        // 无 PTS 按到达顺序全速解码 (gst-launch 节奏实验: 29fps 正常)。
                        // 渲染端 rkximagesink sync=false, 无需 PTS。
                        media_->pushVideo(reinterpret_cast<const uint8_t*>(f->data()),
                                          f->size(), -1.0);
                    }
            } else if (pt == 111) {
                rtc::message_vector one;
                one.push_back(m);
                adepack_->incoming(one, send_);
                for (auto &f : one)
                    if (!f->empty())
                        media_->pushAudio(reinterpret_cast<const uint8_t*>(f->data()),
                                          f->size());
            }
        }
        messages.clear();                        // 全部已消费
    }

    void resetSession() {                        // 新连接会话时由外部调用
        v_remote_ssrc_ = 0;
        v_last_seq_ = 0;
        v_have_seq_ = false;
        have_sr_ = false;
        sr_ntp_ = sr_rtpts_ = 0;
        v_pending_ts_ = 0;
        v_pending_arrive_ = 0;
        v_have_pending_ = false;
        last_pli_ = 0;
        raw_delays_.clear();
        clock_bias_min_ = -1.0;
        total_pkt_ = lost_pkt_ = 0;
        sr_warned_ = false;
    }

private:
    // ---- RTP 解析辅助 (大端) ----
    static uint16_t rtpSeq(const uint8_t* p) { return uint16_t(rd32be(p + 2) & 0xFFFF); }
    static uint32_t rtpTs(const uint8_t* p)  { return rd32be(p + 4); }
    static uint32_t rtpSsrc(const uint8_t* p){ return rd32be(p + 8); }

    // ---- 视频 RTP: 丢包检测 + NACK/PLI + 帧到达延迟估算 ----
    void onVideoRtp(const rtc::message_ptr &m) {
        const uint8_t* p = reinterpret_cast<const uint8_t*>(m->data());
        uint32_t ssrc = rtpSsrc(p);
        uint16_t seq = rtpSeq(p);
        uint32_t ts = rtpTs(p);
        if (v_remote_ssrc_ == 0) v_remote_ssrc_ = ssrc;

        total_pkt_++;
        if (!v_have_seq_) {
            v_last_seq_ = seq; v_have_seq_ = true;
        } else {
            int gap = int(int32_t(seq) - int32_t(v_last_seq_));
            v_last_seq_ = seq;
            if (gap > 0 && gap < 4096) {         // 丢包: 连续小间隔
                lost_pkt_ += gap;
                if (gap < 256) {
                    // 细粒度恢复: 单包丢失用 NACK 请求重传 (最多带 8 个 PID)
                    sendNack(ssrc, seq, gap);
                } else {
                    sendPli();                    // 大量丢失直接请求关键帧
                }
            } else if (gap >= 4096 || gap < -4096) {
                // 序列号大跳变: 流重置 (可能是新编码会话), 请求关键帧
                v_have_seq_ = false;
                sendPli();
            }
        }

        // 帧级到达延迟估算: 记录每帧 (新 timestamp) 首包到达时刻
        double now = nowSecs();
        if (ts != v_pending_ts_) {
            if (v_have_pending_ && have_sr_ && v_remote_ssrc_) {
                double sendSecs = sr_ntp_ + double(int64_t(v_pending_ts_) - int64_t(sr_rtpts_)) / 90000.0;
                double raw = v_pending_arrive_ - sendSecs;
                if (raw > -1.0 && raw < 10.0) {
                    // 时钟偏差基线: 取滚动窗口最小值近似 (网络最佳帧 ≈ 偏差)
                    raw_delays_.push_back(raw);
                    if (raw_delays_.size() > 120) raw_delays_.pop_front();
                    double mn = *std::min_element(raw_delays_.begin(), raw_delays_.end());
                    clock_bias_min_ = mn;
                    double latMs = (raw - mn) * 1000.0;
                    if (latMs < 0) latMs = 0;
                    media_->osd_lat_ms.store(int(latMs));
                    media_->osd_warn_lat.store(latMs > 300);
                }
            }
            v_pending_ts_ = ts;
            v_pending_arrive_ = now;
            v_have_pending_ = true;
        }

        int lossPct = int(100.0 * lost_pkt_ / std::max(total_pkt_, uint64_t(1)));
        media_->osd_loss_pct.store(lossPct);

        // 周期保底 PLI: 仅长间隔一次 (过大 IDR 帧在软编端会造成周期性卡顿, 频率必须低)
        if (now - last_pli_ > 10.0) sendPli();
    }

    // ---- RTCP 解析: Sender Report 提供 (NTP <-> RTP ts) 时间基准 ----
    void parseRtcp(const rtc::message_ptr &m) {
        const uint8_t* p = reinterpret_cast<const uint8_t*>(m->data());
        size_t len = m->size();
        size_t off = 0;
        while (off + 4 <= len) {
            uint8_t byte0 = p[off];
            uint8_t pt = p[off + 1];
            size_t words = (size_t(rd32be(p + off + 2)) & 0xFFFF) + 1;
            if (off + 4 * words > len) break;
            if ((byte0 >> 6) == 2 && pt == 200 && words >= 7 && len >= off + 24) {
                // Sender Report: 解析 sender ssrc + NTP + RTP ts
                uint32_t srSsrc = rd32be(p + off + 4);
                if (v_remote_ssrc_ != 0 && srSsrc == v_remote_ssrc_) {
                    uint32_t ntpMsw = rd32be(p + off + 8);
                    uint32_t ntpLsw = rd32be(p + off + 12);
                    double ntp = ntpMsw + ntpLsw / 4294967296.0;
                    sr_ntp_ = ntp;
                    sr_rtpts_ = rd32be(p + off + 16);
                    have_sr_ = true;
                } else if (!sr_warned_) {
                    sr_warned_ = true;
                    std::cout << "[qos] 收到 SR sender ssrc=" << srSsrc
                              << " (期待 video ssrc=" << v_remote_ssrc_ << "), 等待后续匹配"
                              << std::endl;
                }
            }
            off += 4 * words;
        }
    }

    // ---- RTCP 反馈发送 ----
    void sendPli() {
        double now = nowSecs();
        if (now - last_pli_ < 0.5 || v_remote_ssrc_ == 0) return;
        last_pli_ = now;
        std::vector<std::byte> b(12);
        uint8_t* p = reinterpret_cast<uint8_t*>(b.data());
        p[0] = 0x80 | 4; p[1] = 206;            // PSFB / PLI
        p[2] = 0; p[3] = 2;
        wr32be(p + 4, SRC_VIDEO);
        wr32be(p + 8, v_remote_ssrc_);
        sendRtcp(std::move(b));
    }

    void sendNack(uint32_t mediaSsrc, uint16_t newestSeq, int gap) {
        double now = nowSecs();
        if (now - last_nack_ < 0.1) return;      // 限流: 每 100ms 最多一次
        last_nack_ = now;
        // 对 [newestSeq-gap, newestSeq-1] 的连续丢失号请求重传
        std::vector<std::byte> b(16);
        uint8_t* p = reinterpret_cast<uint8_t*>(b.data());
        p[0] = 0x80 | 1; p[1] = 205;            // RTPFB / NACK
        p[2] = 0; p[3] = 3;
        wr32be(p + 4, SRC_VIDEO);
        wr32be(p + 8, mediaSsrc);
        // FCI: PID = 最老丢失号, BLP 位图覆盖后续 16 个
        uint16_t oldest = uint16_t(int32_t(newestSeq) - gap);
        uint16_t blp = 0;
        for (int i = 1; i < 16 && i < gap; ++i) {
            uint16_t s = uint16_t(int32_t(oldest) + i);
            // 此处简化: 不逐号校验缺失 (gap 内假定全丢)
            blp |= uint16_t(1 << i);
        }
        wr32be(p + 12, (uint32_t(oldest) << 16) | blp);
        sendRtcp(std::move(b));
    }

    void sendRtcp(std::vector<std::byte> &&data) {
        if (!send_) return;
        try {
            auto msg = rtc::make_message(std::move(data), rtc::Message::Type::Control);
            send_(msg);
        } catch (const std::exception &e) {
            // 反馈发送失败不影响收流
        }
    }

    MediaPipeline* media_;
    std::shared_ptr<rtc::MediaHandler> vdepack_;
    std::shared_ptr<rtc::MediaHandler> adepack_;
    rtc::message_callback send_;

    // 丢包检测状态
    uint32_t v_remote_ssrc_ = 0;
    uint16_t v_last_seq_ = 0;
    bool v_have_seq_ = false;
    uint64_t total_pkt_ = 0, lost_pkt_ = 0;
    double last_pli_ = 0, last_nack_ = 0;

    // SR 时间基准
    bool sr_warned_ = false;
    bool have_sr_ = false;
    double sr_ntp_ = 0;
    uint32_t sr_rtpts_ = 0;


    // 帧延迟估算
    uint32_t v_pending_ts_ = 0;
    double v_pending_arrive_ = 0;
    bool v_have_pending_ = false;
    std::deque<double> raw_delays_;
    double clock_bias_min_ = -1.0;
};

// ----------------------------------------------------------------------------
// WebRTC 接收器 (offerer) + 信令
// ----------------------------------------------------------------------------
class ReversePlayer {
public:
    bool start(const std::string& sigUrl, const std::string& room, MediaPipeline* media) {
        room_ = room;
        media_ = media;

        // 信令 WebSocket
        ws_ = std::make_shared<rtc::WebSocket>();
        ws_->onOpen([this]() {
            std::cout << "[sig] 已连接, 加入房间 " << room_ << std::endl;
            sendJson({{"type", "viewer_join"}, {"room", room_}});
        });
        ws_->onMessage([this](rtc::message_variant data) {
            if (auto* s = std::get_if<rtc::string>(&data))
                handleSignal(*s);
        });
        ws_->onClosed([]() { std::cout << "[sig] 连接关闭" << std::endl; });
        ws_->onError([](std::string e) { std::cerr << "[sig] 错误: " << e << std::endl; });
        ws_->open(sigUrl);
        return true;
    }

private:
    void sendJson(const std::map<std::string, std::string>& kv) {
        // 简易 JSON 拼装 (值含 SDP 转义)
        std::string json = "{";
        bool first = true;
        for (auto& [k, v] : kv) {
            if (!first) json += ",";
            first = false;
            json += "\"" + k + "\":\"" + jsonEscape(v) + "\"";
        }
        json += "}";
        if (ws_ && ws_->isOpen()) ws_->send(json);
    }

    static std::string jsonEscape(const std::string& s) {
        std::string out;
        for (char c : s) {
            switch (c) {
                case '"':  out += "\\\""; break;
                case '\\': out += "\\\\"; break;
                case '\n': out += "\\n"; break;
                case '\r': out += "\\r"; break;
                case '\t': out += "\\t"; break;
                default:
                    if ((unsigned char)c < 0x20) { char b[8]; snprintf(b, sizeof b, "\\u%04x", c); out += b; }
                    else out += c;
            }
        }
        return out;
    }

    // 极简 JSON 字符串字段提取 (够用于信令消息)
    static bool extractStr(const std::string& json, const std::string& key, std::string& out) {
        std::string pat = "\"" + key + "\"";
        size_t p = json.find(pat);
        if (p == std::string::npos) return false;
        p = json.find(':', p + pat.size());
        if (p == std::string::npos) return false;
        p = json.find('"', p);
        if (p == std::string::npos) return false;
        p++;
        out.clear();
        while (p < json.size() && json[p] != '"') {
            if (json[p] == '\\' && p + 1 < json.size()) {
                char n = json[p + 1];
                if (n == 'n') out += '\n';
                else if (n == 'r') out += '\r';
                else if (n == 't') out += '\t';
                else out += n;   // \" \\ \/ \uXXXX 简化
                p += 2;
            } else {
                out += json[p++];
            }
        }
        return p < json.size();
    }

    void handleSignal(const std::string& text) {
        std::string type;
        if (!extractStr(text, "type", type)) return;

        if (type == "request_offer") {
            // 浏览器(answerer)请求: 板卡作为 offerer 主动发 offer
            // (正向推流已验证 offerer 模式的 offer 生成正常; answerer 自动 answer 存在
            //  m-line 端口 0 被拒的缺陷, 故反转协商角色)
            std::cout << "[sig] 收到 request_offer, 板卡作为 offerer 生成 offer..." << std::endl;
            createOfferer();
        } else if (type == "answer") {
            std::string sdp;
            if (!extractStr(text, "sdp", sdp)) return;
            if (!pc_) return;
            // 诊断: 存 answer 全文 + 打印 SSRC 声明 (收流路由依赖 a=ssrc -> track 映射)
            {
                FILE* f = fopen("/tmp/answer_real.sdp", "wb");
                if (f) { fwrite(sdp.data(), 1, sdp.size(), f); fclose(f); }
                size_t p = 0;
                int ssrcLines = 0;
                while ((p = sdp.find("a=ssrc", p)) != std::string::npos) {
                    size_t e = sdp.find("\r\n", p);
                    if (e == std::string::npos) e = sdp.size();
                    std::cout << "[diag] " << sdp.substr(p, e - p) << std::endl;
                    ssrcLines++;
                    p = e + 1;
                }
                std::cout << "[diag] answer 含 a=ssrc 行数: " << ssrcLines << std::endl;
            }
            try {
                std::cout << "[sig] 收到 answer (" << sdp.size() << " 字节), 应用中..." << std::endl;
                pc_->setRemoteDescription(rtc::Description(sdp, rtc::Description::Type::Answer));
            } catch (const std::exception& e) {
                std::cerr << "[sig] setRemoteDescription 失败: " << e.what() << std::endl;
            }
        } else if (type == "ice") {
            std::string cand, mid;
            extractStr(text, "candidate", cand);
            extractStr(text, "mid", mid);
            if (!cand.empty() && pc_) {
                try {
                    pc_->addRemoteCandidate(rtc::Candidate(cand, mid));
                } catch (const std::exception& e) {
                    std::cerr << "[sig] addRemoteCandidate: " << e.what() << std::endl;
                }
            }
        }
    }

    void createOfferer() {
        // 浏览器重推流时重建 PeerConnection (新 ICE 凭据)
        if (pc_) {
            try { pc_->close(); } catch (...) {}
            pc_.reset();
        }

        rtc::Configuration config;   // 同网段直连/浏览器侧 TURN, 本端无需 STUN
        // 关闭自动重协商: answer 应用后 libdatachannel 会误判 negotiationNeeded 触发二次
        // offer, 浏览器对二次 offer 的 answer 被板卡拒绝("no active media"), 打断 ICE
        config.disableAutoNegotiation = true;
        pc_ = std::make_shared<rtc::PeerConnection>(config);

        // RecvOnly track (与正向 SendOnly 相同的 addTrack + setLocalDescription 模式)
        // 必须声明编解码: 否则 offer 的 m-line 无 payload 列表, 浏览器解析报 "Invalid value"
        // 注意: track 仅用于 SDP 协商; 收流处理走 PC 级 ReverseMediaHandler (见类注释),
        //       因为预添加本地 track 不会被 openTracks() 打开, track.onMessage 永不触发
        rtc::Description::Video vdesc("video", rtc::Description::Direction::RecvOnly);
        vdesc.addH264Codec(96);
        vdesc.addSSRC(42, std::string("video-recv"), std::string("stream1"), std::string("video"));
        // 必须持有返回的 shared_ptr: libdatachannel 的 mTracks 存 weak_ptr, 返回值一析构
        // track 即销毁, setLocalDescription 会报 "No DataChannel or Track to negotiate"
        vtrack_ = pc_->addTrack(vdesc);

        rtc::Description::Audio adesc("audio", rtc::Description::Direction::RecvOnly);
        adesc.addOpusCodec(111);
        adesc.addSSRC(43, std::string("audio-recv"), std::string("stream1"), std::string("audio"));
        atrack_ = pc_->addTrack(adesc);

        // PC 级收流处理 (在 SSRC 路由之前, 直接拿到全部解密后的 RTP)
        handler_ = std::make_shared<ReverseMediaHandler>(media_);
        handler_->resetSession();
        pc_->setMediaHandler(handler_);

        // 板卡为 offerer: 发 offer (浏览器 answerer 应答)
        pc_->onLocalDescription([this](rtc::Description desc) {
            std::string sdp = std::string(desc);
            std::cout << "[sig] 发送 " << desc.typeString()
                      << " (SDP " << sdp.size() << " 字节)" << std::endl;
            sendJson({{"type", "offer"}, {"room", room_}, {"sdp", sdp}});
        });

        pc_->onLocalCandidate([this](rtc::Candidate cand) {
            // 必须用 cand.candidate(): 纯 candidate 行 (无 "a=" 前缀), 浏览器才能解析
            sendJson({{"type", "ice"}, {"room", room_},
                      {"candidate", cand.candidate()}, {"mid", cand.mid()}});
        });

        pc_->onStateChange([this](rtc::PeerConnection::State state) {
            static const char* names[] = {"New", "Connecting", "Connected", "Disconnected", "Failed", "Closed"};
            const char* n = (static_cast<int>(state) <= 5) ? names[static_cast<int>(state)] : "?";
            std::cout << "[rtc] state=" << n << std::endl;
            if (state == rtc::PeerConnection::State::Connected) {
                std::cout << "[rtc] ==== CONNECTED, 等待媒体流 ====" << std::endl;
                // 诊断: 延迟1秒检查 track open 状态 (flushPendingMessages 消费的前置条件)
                std::thread([this]() {
                    std::this_thread::sleep_for(std::chrono::seconds(1));
                    std::cout << "[diag] tracks open 状态: video=" << media_->v_open.load()
                              << " audio=" << media_->a_open.load() << std::endl;
                }).detach();
            }
            else if (state == rtc::PeerConnection::State::Failed)
                std::cerr << "[rtc] 连接失败 (ICE/DTLS)" << std::endl;
        });

        // 生成 offer (正向推流同款调用, 已验证)
        pc_->setLocalDescription();
    }

    std::string room_;
    MediaPipeline* media_ = nullptr;
    std::shared_ptr<rtc::PeerConnection> pc_;
    std::shared_ptr<rtc::WebSocket> ws_;
    std::shared_ptr<rtc::Track> vtrack_;   // 持有强引用防止 track 析构
    std::shared_ptr<rtc::Track> atrack_;
    std::shared_ptr<ReverseMediaHandler> handler_;  // QoS 收流处理器
};

// ----------------------------------------------------------------------------
int main(int argc, char* argv[]) {
    std::string sigUrl = argc > 1 ? argv[1] : "ws://127.0.0.1:8080";
    std::string room   = argc > 2 ? argv[2] : "reverse1";

    std::signal(SIGINT, onSigint);
    std::signal(SIGTERM, onSigint);
    setvbuf(stdout, nullptr, _IONBF, 0);   // 关闭 stdout 缓冲: nohup 重定向时保证日志实时写盘
    rtc::InitLogger(rtc::LogLevel::Warning);   // Warning: 仅错误/警告 (OSD/帧率由程序自报)

    std::cout << "[init] 反向播放器  room=" << room << "  signaling=" << sigUrl << std::endl;
    std::cout << "[init] 视频: H264 硬解(mppvideodec) -> 1024x600 (rkximagesink)" << std::endl;
    std::cout << "[init] 音频: Opus 解码 -> ALSA" << std::endl;

    MediaPipeline media;
    if (!media.start()) return 1;

    ReversePlayer player;
    player.start(sigUrl, room, &media);

    auto lastV = media.v_frames.load(), lastA = media.a_frames.load();
    auto lastVB = media.v_bytes.load(), lastAB = media.a_bytes.load();
    auto lastD = media.dec_frames.load();
    auto lastT = std::chrono::steady_clock::now();
    while (g_running) {
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        g_main_context_iteration(nullptr, FALSE);   // 派发总线消息

        auto now = std::chrono::steady_clock::now();
        if (now - lastT >= std::chrono::seconds(2)) {
            auto v = media.v_frames.load(), a = media.a_frames.load();
            auto vb = media.v_bytes.load(), ab = media.a_bytes.load();
            auto d = media.dec_frames.load();
            int loss = media.osd_loss_pct.load();
            int lat = media.osd_lat_ms.load();
            std::cout << "[stat] 输入 " << (v - lastV) / 2 << "fps (" << (vb - lastVB) / 2 / 1024
                      << "KB/s) 解码输出 " << (d - lastD) / 2 << "fps, 音频 "
                      << (a - lastA) / 2 << "/s, 丢包 " << loss << "%, 单向延迟估算 " << lat << "ms"
                      << (media.v_overflow.load() ? "  [溢出!]" : "") << std::endl;
            lastV = v; lastA = a; lastVB = vb; lastAB = ab; lastD = d; lastT = now;
        }
    }
    std::cout << "[init] 退出" << std::endl;
    rtc::Cleanup();
    return 0;
}
