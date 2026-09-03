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

// ----------------------------------------------------------------------------
// GStreamer 解码显示管道 (appsrc 动态喂数据)
// ----------------------------------------------------------------------------
class MediaPipeline {
public:
    // 统计 (主循环每秒打印)
    std::atomic<uint64_t> v_frames{0}, v_bytes{0}, a_frames{0}, a_bytes{0};
    std::atomic<bool> v_overflow{false};
    std::atomic<bool> v_open{false}, a_open{false};   // track open 状态诊断

    bool start() {
        gst_init(nullptr, nullptr);

        // 视频: H264 Annex-B -> 硬解 -> 缩放到屏 1024x600 -> 显示
        std::string vdesc =
            "appsrc name=vsrc is-live=true do-timestamp=true format=time "
            "max-bytes=16777216 "
            "caps=video/x-h264,stream-format=(string)byte-stream,alignment=(string)au "
            "! h264parse ! mppvideodec "
            "! videoconvert ! videoscale "
            "! video/x-raw,width=1024,height=600 "
            "! rkximagesink sync=false";

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

        // 总线监听: 打印管道错误/警告 (否则 mppvideodec 协商失败等无法察觉)
        installBusWatch(vpipe_, "video");
        installBusWatch(apipe_, "audio");

        GstStateChangeReturn r1 = gst_element_set_state(vpipe_, GST_STATE_PLAYING);
        GstStateChangeReturn r2 = gst_element_set_state(apipe_, GST_STATE_PLAYING);
        std::cout << "[gst] video pipe -> " << r1 << ", audio pipe -> " << r2 << std::endl;
        return true;
    }

    void pushVideo(const uint8_t* data, size_t len) {
        if (!vsrc_) return;
        pushBuffer(vsrc_, data, len, [&](bool ok){ if (!ok) v_overflow = true; });
        v_frames++; v_bytes += len;
    }

    void pushAudio(const uint8_t* data, size_t len) {
        if (!asrc_) return;
        pushBuffer(asrc_, data, len, nullptr);
        a_frames++; a_bytes += len;
    }

    ~MediaPipeline() {
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

    void pushBuffer(GstElement* src, const uint8_t* data, size_t len,
                    const std::function<void(bool)>& onErr) {
        GstBuffer* buf = gst_buffer_new_allocate(nullptr, len, nullptr);
        gst_buffer_fill(buf, 0, data, len);
        GstFlowReturn ret = GST_FLOW_OK;
        g_signal_emit_by_name(src, "push-buffer", buf, &ret);
        gst_buffer_unref(buf);
        if (ret != GST_FLOW_OK && onErr) onErr(false);
    }

    GstElement* vpipe_ = nullptr;
    GstElement* apipe_ = nullptr;
    GstElement* vsrc_ = nullptr;
    GstElement* asrc_ = nullptr;
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
        for (auto &m : messages) {
            if (m->type == rtc::Message::Control)
                continue;                       // RTCP: 忽略 (无 RTCP 反馈也能工作)
            if (m->size() < 12)
                continue;

            uint8_t pt = std::to_integer<uint8_t>(m->data()[1]) & 0x7F;
            if (pt == 96) {
                // 视频 H264: RTP 分片重组为 Annex-B 帧
                rtc::message_vector one;
                one.push_back(m);
                vdepack_->incoming(one, send);
                for (auto &f : one)
                    if (!f->empty())
                        media_->pushVideo(reinterpret_cast<const uint8_t*>(f->data()),
                                          f->size());
            } else if (pt == 111) {
                // 音频 Opus: depacketizer 去 RTP 头输出 payload
                rtc::message_vector one;
                one.push_back(m);
                adepack_->incoming(one, send);
                for (auto &f : one)
                    if (!f->empty())
                        media_->pushAudio(reinterpret_cast<const uint8_t*>(f->data()),
                                          f->size());
            }
        }
        messages.clear();                        // 全部已消费
    }

private:
    MediaPipeline* media_;
    std::shared_ptr<rtc::MediaHandler> vdepack_;
    std::shared_ptr<rtc::MediaHandler> adepack_;
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
        pc_->setMediaHandler(std::make_shared<ReverseMediaHandler>(media_));

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
};

// ----------------------------------------------------------------------------
int main(int argc, char* argv[]) {
    std::string sigUrl = argc > 1 ? argv[1] : "ws://127.0.0.1:8080";
    std::string room   = argc > 2 ? argv[2] : "reverse1";

    std::signal(SIGINT, onSigint);
    std::signal(SIGTERM, onSigint);
    setvbuf(stdout, nullptr, _IONBF, 0);   // 关闭 stdout 缓冲: nohup 重定向时保证日志实时写盘
    rtc::InitLogger(rtc::LogLevel::Verbose);   // VERBOSE: 逐包打印各层处理轨迹, 定位断点

    std::cout << "[init] 反向播放器  room=" << room << "  signaling=" << sigUrl << std::endl;
    std::cout << "[init] 视频: H264 硬解(mppvideodec) -> 1024x600 (rkximagesink)" << std::endl;
    std::cout << "[init] 音频: Opus 解码 -> ALSA" << std::endl;

    MediaPipeline media;
    if (!media.start()) return 1;

    ReversePlayer player;
    player.start(sigUrl, room, &media);

    auto lastV = media.v_frames.load(), lastA = media.a_frames.load();
    auto lastVB = media.v_bytes.load(), lastAB = media.a_bytes.load();
    auto lastT = std::chrono::steady_clock::now();
    while (g_running) {
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        g_main_context_iteration(nullptr, FALSE);   // 派发总线消息

        auto now = std::chrono::steady_clock::now();
        if (now - lastT >= std::chrono::seconds(2)) {
            auto v = media.v_frames.load(), a = media.a_frames.load();
            auto vb = media.v_bytes.load(), ab = media.a_bytes.load();
            std::cout << "[stat] 视频 " << (v - lastV) / 2 << " 帧/秒 ("
                      << (vb - lastVB) / 2 / 1024 << " KB/s), 音频 "
                      << (a - lastA) / 2 << " 帧/秒"
                      << (media.v_overflow.load() ? "  [视频溢出!]" : "") << std::endl;
            lastV = v; lastA = a; lastVB = vb; lastAB = ab; lastT = now;
        }
    }
    std::cout << "[init] 退出" << std::endl;
    rtc::Cleanup();
    return 0;
}
