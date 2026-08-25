// ============================================================================
// RV1126B (ELF 板) WebRTC 低延迟视频推流主程序
// 架构: V4L2 摄像头采集 -> RK MPP 硬编码 (H.264) -> libdatachannel WebRTC 推流
// 信令: 通过 libdatachannel 内置 WebSocket 连接 Node.js 信令服务器
// ============================================================================

#include <rtc/rtc.hpp>

#include <rockchip/rk_mpi.h>

#include <linux/videodev2.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <cstring>
#include <functional>
#include <iostream>
#include <string>
#include <thread>
#include <variant>
#include <vector>

// ----------------------------------------------------------------------------
// 可调配置
// ----------------------------------------------------------------------------
static constexpr int    WIDTH          = 640;       // 采集/编码宽度 (USB 摄像头 YUYV 640x480@30fps)
static constexpr int    HEIGHT         = 480;       // 采集/编码高度
static constexpr int    FPS            = 30;        // 帧率
static constexpr uint32_t BITRATE      = 1024 * 1024; // 目标码率 1 Mbps
static constexpr const char* CAM_DEV    = "/dev/video52"; // HD USB Camera
static constexpr const char* SIGNALING_URL = "ws://127.0.0.1:8080";
static constexpr const char* ROOM       = "cam1";
static constexpr const char* STUN_SERVER = "stun:stun.l.google.com:19302";

static std::atomic<bool> g_running{true};
// 浏览器通过 RTCP PLI/FIR 请求关键帧时置位, 主循环据此强制编码器输出 IDR
static std::atomic<bool> g_request_idr{false};

// ----------------------------------------------------------------------------
// 极简 JSON 工具 (避免外部依赖, 只处理本项目固定格式的信令消息)
// ----------------------------------------------------------------------------
static std::string json_escape(const std::string& s) {
    std::string out;
    out.reserve(s.size());
    for (char c : s) {
        switch (c) {
            case '"':  out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n";  break;
            case '\r': out += "\\r";  break;
            case '\t': out += "\\t";  break;
            default:   out += c;      break;
        }
    }
    return out;
}

static std::string json_unescape(const std::string& s) {
    std::string out;
    out.reserve(s.size());
    for (size_t i = 0; i < s.size(); ++i) {
        if (s[i] == '\\' && i + 1 < s.size()) {
            char n = s[++i];
            switch (n) {
                case 'n':  out += '\n'; break;
                case 'r':  out += '\r'; break;
                case 't':  out += '\t'; break;
                case '"':  out += '"';  break;
                case '\\': out += '\\'; break;
                default:   out += n;    break;
            }
        } else {
            out += s[i];
        }
    }
    return out;
}

// 从形如 {"type":"answer","sdp":"..."} 的 JSON 中提取某个字符串字段值
static std::string json_get_str(const std::string& json, const std::string& key) {
    std::string needle = "\"" + key + "\"";
    size_t p = json.find(needle);
    if (p == std::string::npos) return "";
    p = json.find(':', p + needle.size());
    if (p == std::string::npos) return "";
    p = json.find('"', p + 1);
    if (p == std::string::npos) return "";
    size_t start = p + 1;
    size_t end = json.find('"', start);
    if (end == std::string::npos) return "";
    return json_unescape(json.substr(start, end - start));
}

// ----------------------------------------------------------------------------
// V4L2 摄像头采集 (mmap 方式, 输出 YUYV)
// ----------------------------------------------------------------------------
class V4L2Capture {
public:
    size_t row_stride() const { return bytesperline_ ? bytesperline_ : width_ * 2; }

    bool init(const char* dev, int width, int height) {
        fd_ = open(dev, O_RDWR | O_NONBLOCK);
        if (fd_ < 0) {
            std::cerr << "[V4L2] open " << dev << " failed" << std::endl;
            return false;
        }

        // USB 摄像头为单平面 (Video Capture), YUYV 格式
        v4l2_format fmt{};
        fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        fmt.fmt.pix.width = width;
        fmt.fmt.pix.height = height;
        fmt.fmt.pix.pixelformat = V4L2_PIX_FMT_YUYV;
        fmt.fmt.pix.field = V4L2_FIELD_NONE;
        if (ioctl(fd_, VIDIOC_S_FMT, &fmt) < 0) {
            std::cerr << "[V4L2] VIDIOC_S_FMT failed" << std::endl;
            close(fd_); fd_ = -1; return false;
        }
        if (fmt.fmt.pix.pixelformat != V4L2_PIX_FMT_YUYV) {
            std::cerr << "[V4L2] driver does not support YUYV (got 0x"
                      << std::hex << fmt.fmt.pix.pixelformat << std::dec
                      << ")" << std::endl;
            close(fd_); fd_ = -1; return false;
        }
        width_ = fmt.fmt.pix.width;
        height_ = fmt.fmt.pix.height;
        bytesperline_ = fmt.fmt.pix.bytesperline;  // YUYV 行字节跨度 (通常 = width*2)

        v4l2_requestbuffers req{};
        req.count = 4;
        req.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        req.memory = V4L2_MEMORY_MMAP;
        if (ioctl(fd_, VIDIOC_REQBUFS, &req) < 0) {
            std::cerr << "[V4L2] VIDIOC_REQBUFS failed" << std::endl;
            close(fd_); fd_ = -1; return false;
        }

        buffers_.resize(req.count);
        for (uint32_t i = 0; i < req.count; ++i) {
            v4l2_buffer buf{};
            buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
            buf.memory = V4L2_MEMORY_MMAP;
            buf.index = i;
            if (ioctl(fd_, VIDIOC_QUERYBUF, &buf) < 0) {
                std::cerr << "[V4L2] VIDIOC_QUERYBUF failed" << std::endl;
                close(fd_); fd_ = -1; return false;
            }
            buffers_[i].length = buf.length;
            buffers_[i].start = mmap(nullptr, buf.length,
                                     PROT_READ | PROT_WRITE, MAP_SHARED, fd_, buf.m.offset);
            if (buffers_[i].start == MAP_FAILED) {
                std::cerr << "[V4L2] mmap failed" << std::endl;
                close(fd_); fd_ = -1; return false;
            }
        }

        for (uint32_t i = 0; i < req.count; ++i) {
            v4l2_buffer buf{};
            buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
            buf.memory = V4L2_MEMORY_MMAP;
            buf.index = i;
            if (ioctl(fd_, VIDIOC_QBUF, &buf) < 0) {
                std::cerr << "[V4L2] VIDIOC_QBUF failed" << std::endl;
                close(fd_); fd_ = -1; return false;
            }
        }

        v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        if (ioctl(fd_, VIDIOC_STREAMON, &type) < 0) {
            std::cerr << "[V4L2] VIDIOC_STREAMON failed" << std::endl;
            close(fd_); fd_ = -1; return false;
        }
        std::cout << "[V4L2] camera initialized: " << width_ << "x" << height_
                  << " YUYV" << std::endl;
        return true;
    }

    // 阻塞获取一帧, 返回 true 表示成功; data/size 指向 mmap 缓冲 (下次 dequeue 前有效)
    bool dequeue(const uint8_t** data, size_t* size) {
        v4l2_buffer buf{};
        buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        buf.memory = V4L2_MEMORY_MMAP;
        if (ioctl(fd_, VIDIOC_DQBUF, &buf) < 0) {
            if (errno == EAGAIN) return false; // 非阻塞无数据
            std::cerr << "[V4L2] VIDIOC_DQBUF failed" << std::endl;
            return false;
        }
        *data = static_cast<const uint8_t*>(buffers_[buf.index].start);
        *size = buf.bytesused;
        last_index_ = buf.index;
        return true;
    }

    void requeue() {
        v4l2_buffer buf{};
        buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        buf.memory = V4L2_MEMORY_MMAP;
        buf.index = last_index_;
        ioctl(fd_, VIDIOC_QBUF, &buf);
    }

    ~V4L2Capture() {
        if (fd_ >= 0) {
            v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
            ioctl(fd_, VIDIOC_STREAMOFF, &type);
            for (auto& b : buffers_) {
                if (b.start) munmap(b.start, b.length);
            }
            close(fd_);
        }
    }

private:
    struct Buffer { void* start = nullptr; size_t length = 0; };
    int fd_ = -1;
    int width_ = 0;
    int height_ = 0;
    size_t bytesperline_ = 0;
    uint32_t last_index_ = 0;
    std::vector<Buffer> buffers_;
};

// ----------------------------------------------------------------------------
// RK MPP 硬编码器 (H.264, Annex-B 输出)
// ----------------------------------------------------------------------------
class MppEncoder {
public:
    bool init(int width, int height, int fps, uint32_t bitrate) {
        width_ = width;
        height_ = height;
        // 改用 NV12 (MPP_FMT_YUV420SP) 输入 —— VPU 原生格式, stride 语义无歧义:
        //   hor_stride = 宽度按 16 对齐 (像素), ver_stride = 高度按 16 对齐
        //   Y 平面: hor_stride*ver_stride 字节; UV 交错平面紧随其后, 大小为其一半
        // (YUYV 打包格式在 MPP 内部转换路径存在 stride 二义性: hs=640 输出二分屏,
        //  hs=1280 单幅但整体偏绿(色度错位), 故改为软件 YUYV->NV12 后送编码器)
        hor_stride_ = (width + 15) & ~15;
        ver_stride_ = (height + 15) & ~15;

        MPP_RET ret = mpp_create(&ctx_, &mpi_);
        if (ret != MPP_OK) {
            std::cerr << "[MPP] mpp_create failed" << std::endl;
            return false;
        }
        ret = mpp_init(ctx_, MPP_CTX_ENC, MPP_VIDEO_CodingAVC);
        if (ret != MPP_OK) {
            std::cerr << "[MPP] mpp_init failed" << std::endl;
            return false;
        }

        MppEncCfg cfg;
        mpp_enc_cfg_init(&cfg);
        mpp_enc_cfg_set_s32(cfg, "prep:width", width_);
        mpp_enc_cfg_set_s32(cfg, "prep:height", height_);
        mpp_enc_cfg_set_s32(cfg, "prep:hor_stride", hor_stride_);
        mpp_enc_cfg_set_s32(cfg, "prep:ver_stride", ver_stride_);
        mpp_enc_cfg_set_s32(cfg, "prep:format", MPP_FMT_YUV420SP);
        mpp_enc_cfg_set_s32(cfg, "rc:mode", MPP_ENC_RC_MODE_CBR);
        mpp_enc_cfg_set_s32(cfg, "rc:bps_target", (RK_S32)bitrate);
        mpp_enc_cfg_set_s32(cfg, "rc:bps_max", (RK_S32)bitrate);
        mpp_enc_cfg_set_s32(cfg, "rc:bps_min", (RK_S32)bitrate);
        mpp_enc_cfg_set_s32(cfg, "rc:fps_in_flex", 0);
        mpp_enc_cfg_set_s32(cfg, "rc:fps_in_num", fps);
        mpp_enc_cfg_set_s32(cfg, "rc:fps_in_denorm", 1);
        mpp_enc_cfg_set_s32(cfg, "rc:fps_out_flex", 0);
        mpp_enc_cfg_set_s32(cfg, "rc:fps_out_num", fps);
        mpp_enc_cfg_set_s32(cfg, "rc:fps_out_denorm", 1);
        mpp_enc_cfg_set_s32(cfg, "rc:gop", fps * 2);
        mpp_enc_cfg_set_s32(cfg, "codec:type", MPP_VIDEO_CodingAVC);
        mpp_enc_cfg_set_s32(cfg, "h264:profile", 100);       // High
        mpp_enc_cfg_set_s32(cfg, "h264:level", 40);

        ret = mpi_->control(ctx_, MPP_ENC_SET_CFG, cfg);
        if (ret != MPP_OK) {
            std::cerr << "[MPP] MPP_ENC_SET_CFG failed" << std::endl;
            return false;
        }
        mpp_enc_cfg_deinit(cfg);

        // 输入 buffer group (DRM 优先, 回退 ION)
        ret = mpp_buffer_group_get_internal(&group_, MPP_BUFFER_TYPE_DRM);
        if (ret != MPP_OK) {
            ret = mpp_buffer_group_get_internal(&group_, MPP_BUFFER_TYPE_ION);
        }
        if (ret != MPP_OK) {
            std::cerr << "[MPP] buffer group get failed" << std::endl;
            return false;
        }

        // 一次性分配输入缓冲区并复用 (关键: 避免每帧 mpp_buffer_get 新建 dmabuf fd 造成泄漏)
        // NV12: Y 平面 + UV 平面 (Y 的一半)
        frame_size_ = hor_stride_ * ver_stride_ * 3 / 2;
        if (mpp_buffer_get(group_, &enc_buf_, frame_size_) != MPP_OK) {
            std::cerr << "[MPP] alloc input buffer failed" << std::endl;
            return false;
        }
        std::cout << "[MPP] encoder initialized: H.264 " << width_ << "x" << height_
                  << " @" << fps << "fps " << (bitrate / 1024) << "kbps (input NV12, conv from YUYV)" << std::endl;
        return true;
    }

    // 编码一帧 YUYV, 输出 Annex-B H.264 数据, 通过 onPacket 回调
    // 返回 false 表示失败 (程序应退出)
    bool encode(const uint8_t* yuyv, size_t yuyv_size,
                const std::function<void(const uint8_t*, size_t)>& on_packet) {
        (void)yuyv_size;
        MppFrame frame = nullptr;
        mpp_frame_init(&frame);
        mpp_frame_set_width(frame, width_);
        mpp_frame_set_height(frame, height_);
        mpp_frame_set_hor_stride(frame, hor_stride_);
        mpp_frame_set_ver_stride(frame, ver_stride_);
        mpp_frame_set_fmt(frame, MPP_FMT_YUV420SP);
        mpp_frame_set_eos(frame, 0);
        mpp_frame_set_pts(frame, pts_++);

        // 软件 YUYV -> NV12 转换 (写入复用缓冲区)
        // YUYV: [Y0 U0 Y1 V1 | Y2 U2 Y3 V3 | ...] 每行 src_stride 字节
        // NV12: Y 平面(hs*vs) + UV 交错平面(hs*vs/2), 4:2:0 (垂直方向色度减半取平均)
        uint8_t* y_plane  = static_cast<uint8_t*>(mpp_buffer_get_ptr(enc_buf_));
        uint8_t* uv_plane = y_plane + hor_stride_ * ver_stride_;
        const size_t src_stride = src_stride_ ? src_stride_ : width_ * 2;

        for (int r = 0; r < height_; ++r) {
            const uint8_t* s = yuyv + r * src_stride;
            uint8_t* d = y_plane + r * hor_stride_;
            for (int c = 0; c < width_; c += 2) {
                d[c]     = s[2 * c];      // Y(偶像素)
                d[c + 1] = s[2 * c + 2];  // Y(奇像素)
            }
        }
        for (int r = 0; r < height_; r += 2) {
            const uint8_t* s0 = yuyv +  r      * src_stride;  // 偶数行
            const uint8_t* s1 = yuyv + (r + 1) * src_stride;  // 奇数行
            uint8_t* duv = uv_plane + (r / 2) * hor_stride_;
            for (int c = 0; c < width_; c += 2) {
                duv[c]     = static_cast<uint8_t>((s0[2 * c + 1] + s1[2 * c + 1]) / 2);  // U
                duv[c + 1] = static_cast<uint8_t>((s0[2 * c + 3] + s1[2 * c + 3]) / 2);  // V
            }
        }

        mpp_frame_set_buffer(frame, enc_buf_);
        if (mpi_->encode_put_frame(ctx_, frame) != MPP_OK) {
            mpp_frame_deinit(&frame);
            return false;
        }
        mpp_frame_deinit(&frame);  // 释放 frame 描述符; enc_buf_ 由类持有, MPP 编码期间另持引用, 之后循环复用

        // 取出所有已编码的 packet
        MppPacket packet = nullptr;
        while (mpi_->encode_get_packet(ctx_, &packet) == MPP_OK && packet) {
            void* data = mpp_packet_get_pos(packet);
            size_t len = mpp_packet_get_length(packet);
            if (data && len > 0) {
                on_packet(static_cast<const uint8_t*>(data), len);
            }
            mpp_packet_deinit(&packet);
        }
        return true;
    }

    // 发送 EOS 并排空剩余 packet (退出前调用, 释放 MPP 内部 buffer)
    void flush(const std::function<void(const uint8_t*, size_t)>& on_packet) {
        if (!ctx_ || !mpi_) return;
        MppFrame frame = nullptr;
        mpp_frame_init(&frame);
        mpp_frame_set_width(frame, width_);
        mpp_frame_set_height(frame, height_);
        mpp_frame_set_hor_stride(frame, hor_stride_);
        mpp_frame_set_ver_stride(frame, ver_stride_);
        mpp_frame_set_fmt(frame, MPP_FMT_YUV420SP);
        mpp_frame_set_eos(frame, 1);
        mpp_frame_set_pts(frame, pts_++);
        mpi_->encode_put_frame(ctx_, frame);

        MppPacket packet = nullptr;
        while (mpi_->encode_get_packet(ctx_, &packet) == MPP_OK && packet) {
            void* data = mpp_packet_get_pos(packet);
            size_t len = mpp_packet_get_length(packet);
            if (data && len > 0) {
                on_packet(static_cast<const uint8_t*>(data), len);
            }
            mpp_packet_deinit(&packet);
        }
        std::cout << "[MPP] encoder flushed" << std::endl;
    }

    // 请求下一帧编码为 IDR 关键帧 (响应浏览器 PLI/FIR, 快速出画面/丢包恢复)
    void forceIdr() {
        if (ctx_ && mpi_) {
            RK_U32 idr = 1;
            mpi_->control(ctx_, MPP_ENC_SET_IDR_FRAME, &idr);
        }
    }

    // 设置源 YUYV 数据的行字节跨度 (V4L2 bytesperline)
    void set_src_stride(size_t s) { src_stride_ = s; }

    ~MppEncoder() {
        if (ctx_) {
            mpi_->reset(ctx_);
            mpp_destroy(ctx_);
        }
        if (enc_buf_) { mpp_buffer_put(enc_buf_); enc_buf_ = nullptr; }
        if (group_) mpp_buffer_group_put(group_);
    }

private:
    MppCtx ctx_ = nullptr;
    MppApi* mpi_ = nullptr;
    MppBufferGroup group_ = nullptr;
    MppBuffer enc_buf_ = nullptr;  // 一次性分配、逐帧复用的输入缓冲区（避免每帧新建 dmabuf 导致 fd 泄漏）
    int width_ = 0, height_ = 0;
    int hor_stride_ = 0, ver_stride_ = 0;
    size_t src_stride_ = 0;   // 源 YUYV 行字节跨度
    size_t frame_size_ = 0;
    int64_t pts_ = 0;
};

// ----------------------------------------------------------------------------
// WebRTC 推流 + 信令
// ----------------------------------------------------------------------------
class WebRTCStreamer {
public:
    bool start(const std::string& signaling_url, const std::string& room) {
        room_ = room;
        rtc::Configuration config;
        config.iceServers.emplace_back(STUN_SERVER);
        pc_ = std::make_shared<rtc::PeerConnection>(config);

        // 创建 H.264 视频 track (SendOnly)
        rtc::Description::Video video("video", rtc::Description::Direction::SendOnly);
        video.addH264Codec(96);
        video.addSSRC(42, std::string("video-send"));

        track_ = pc_->addTrack(video);

        // RTP 打包配置 (SSRC/payloadType/时钟频率必须与 SDP 一致)
        // 注意: rtpConfig 不能为 nullptr, 否则连接建立后发送首帧即空指针崩溃
        rtpConfig_ = std::make_shared<rtc::RtpPacketizationConfig>(
            42, "video-send", 96, 90000);

        auto packetizer = std::make_shared<rtc::H264RtpPacketizer>(
            rtc::NalUnit::Separator::LongStartSequence, rtpConfig_);
        // RTCP SR 定期上报 (浏览器依赖 SR 做 RTT/带宽估计, 缺失会导致 stats 异常)
        packetizer->addToChain(std::make_shared<rtc::RtcpSrReporter>(rtpConfig_));
        // 响应浏览器 NACK 丢包重传请求 (防止花屏/卡顿)
        packetizer->addToChain(std::make_shared<rtc::RtcpNackResponder>());
        // 响应浏览器 PLI/FIR 关键帧请求 (快速出画面/丢包后快速恢复)
        packetizer->addToChain(std::make_shared<rtc::PliHandler>([]() {
            g_request_idr = true;
        }));
        track_->setMediaHandler(packetizer);

        ws_ = std::make_shared<rtc::WebSocket>();

        pc_->onLocalDescription([this](rtc::Description desc) {
            local_sdp_ = desc.generateSdp();
            send_offer();
            std::cout << "[SIG] offer sent (" << local_sdp_.size() << " bytes)" << std::endl;
        });

        pc_->onLocalCandidate([this](rtc::Candidate cand) {
            std::string msg = "{\"type\":\"ice\",\"room\":\"" + room_ +
                              "\",\"candidate\":\"" + json_escape(cand.candidate()) +
                              "\",\"mid\":\"" + json_escape(cand.mid()) + "\"}";
            send_msg(msg);
        });

        pc_->onStateChange([this](rtc::PeerConnection::State state) {
            std::cout << "[RTC] state: " << static_cast<int>(state) << std::endl;
            if (state == rtc::PeerConnection::State::Connected) {
                connected_ = true;
                g_request_idr = true;  // 连接建立立即输出关键帧, 浏览器尽快出画面
                std::cout << "[RTC] ===== CONNECTED =====" << std::endl;
            } else if (state == rtc::PeerConnection::State::Disconnected ||
                       state == rtc::PeerConnection::State::Failed ||
                       state == rtc::PeerConnection::State::Closed) {
                connected_ = false;    // 断线后停止发送, 防止向已失效的 track 发数据
            }
        });

        pc_->onGatheringStateChange([](rtc::PeerConnection::GatheringState state) {
            std::cout << "[RTC] gathering state: " << static_cast<int>(state) << std::endl;
        });

        ws_->onOpen([this]() {
            std::cout << "[SIG] websocket connected" << std::endl;
            std::string msg = "{\"type\":\"streamer_join\",\"room\":\"" + room_ + "\"}";
            send_msg(msg);
            // 加入后生成本地 offer (触发 onLocalDescription)
            pc_->setLocalDescription();
        });

        ws_->onMessage([this](rtc::message_variant data) {
            std::string text;
            if (auto* s = std::get_if<rtc::string>(&data)) {
                text = *s;
            } else if (auto* b = std::get_if<rtc::binary>(&data)) {
                text.assign(reinterpret_cast<const char*>(b->data()), b->size());
            } else {
                return;
            }
            handle_signal(text);
        });

        ws_->onClosed([]() {
            std::cout << "[SIG] websocket closed" << std::endl;
        });

        ws_->open(signaling_url);
        return true;
    }

    void send(const uint8_t* data, size_t size) {
        if (!connected_ || !track_ || !track_->isOpen()) return;
        try {
            // 用 sendFrame 携带帧时间(秒), packetizer 据此设置单调递增的 RTP timestamp
            // (若用 send() 不带时间信息, RTP timestamp 恒定, 浏览器无法正常渲染)
            auto elapsed = std::chrono::duration<double>(
                std::chrono::steady_clock::now() - start_time_);
            track_->sendFrame(reinterpret_cast<const std::byte*>(data), size,
                              rtc::FrameInfo(elapsed));
        } catch (const std::exception& e) {
            // 单帧发送失败不能杀死整个进程
            std::cerr << "[RTC] send failed: " << e.what() << std::endl;
        }
    }

    bool connected() const { return connected_; }

private:
    void send_msg(const std::string& msg) {
        if (ws_ && ws_->isOpen()) ws_->send(msg);
    }

    void handle_signal(const std::string& text) {
        std::string type = json_get_str(text, "type");
        if (type == "answer") {
            std::string sdp = json_get_str(text, "sdp");
            if (!sdp.empty()) {
                try {
                    rtc::Description answer(sdp, rtc::Description::Type::Answer);
                    pc_->setRemoteDescription(answer);
                    std::cout << "[SIG] answer received, remote description set" << std::endl;
                } catch (const std::exception& e) {
                    std::cerr << "[SIG] setRemoteDescription failed: " << e.what() << std::endl;
                }
            }
        } else if (type == "ice") {
            std::string cand_str = json_get_str(text, "candidate");
            std::string mid = json_get_str(text, "mid");
            if (!cand_str.empty()) {
                rtc::Candidate cand(cand_str, mid);
                pc_->addRemoteCandidate(cand);
            }
        } else if (type == "request_offer") {
            // viewer 加入后请求重新发送 offer (重发缓存的 SDP)
            std::cout << "[SIG] request_offer received, re-sending offer" << std::endl;
            send_offer();
        }
    }

    void send_offer() {
        if (local_sdp_.empty()) {
            std::cerr << "[SIG] send_offer: local_sdp_ empty!" << std::endl;
            return;
        }
        std::string msg = "{\"type\":\"offer\",\"room\":\"" + room_ +
                          "\",\"sdp\":\"" + json_escape(local_sdp_) + "\"}";
        send_msg(msg);
        std::cout << "[SIG] offer re-sent (" << local_sdp_.size() << " bytes)" << std::endl;
    }

    std::shared_ptr<rtc::PeerConnection> pc_;
    std::shared_ptr<rtc::Track> track_;
    std::shared_ptr<rtc::WebSocket> ws_;
    std::shared_ptr<rtc::RtpPacketizationConfig> rtpConfig_;
    std::chrono::steady_clock::time_point start_time_{std::chrono::steady_clock::now()};
    std::string room_;
    std::string local_sdp_;
    std::atomic<bool> connected_{false};
};

// ----------------------------------------------------------------------------
// 主函数
// ----------------------------------------------------------------------------
int main() {
    rtc::InitLogger(rtc::LogLevel::Warning);

    std::signal(SIGINT, [](int) { g_running = false; });
    std::signal(SIGTERM, [](int) { g_running = false; });

    // 1. 初始化摄像头
    V4L2Capture capture;
    if (!capture.init(CAM_DEV, WIDTH, HEIGHT)) {
        std::cerr << "camera init failed, exit" << std::endl;
        rtc::Cleanup();
        return 1;
    }

    // 2. 初始化 MPP 编码器 (NV12 输入, 软件转换自 YUYV)
    MppEncoder encoder;
    if (!encoder.init(WIDTH, HEIGHT, FPS, BITRATE)) {
        std::cerr << "encoder init failed, exit" << std::endl;
        rtc::Cleanup();
        return 1;
    }
    encoder.set_src_stride(capture.row_stride());  // 摄像头 YUYV 实际行跨度

    // 3. 初始化 WebRTC + 信令
    WebRTCStreamer streamer;
    streamer.start(SIGNALING_URL, ROOM);

    std::cout << "==> streaming started, waiting for viewer ..." << std::endl;

    // 4. 采集-编码-推流主循环
    const uint8_t* frame_data = nullptr;
    size_t frame_size = 0;
    while (g_running) {
        // 浏览器 PLI/FIR 请求或刚建立连接 → 强制下一帧为 IDR 关键帧
        if (g_request_idr.exchange(false)) {
            encoder.forceIdr();
        }

        if (!capture.dequeue(&frame_data, &frame_size)) {
            // 非阻塞无帧, 稍作等待
            std::this_thread::sleep_for(std::chrono::milliseconds(2));
            continue;
        }

        if (!encoder.encode(frame_data, frame_size,
                            [&streamer](const uint8_t* h264, size_t len) {
                                streamer.send(h264, len);
                            })) {
            std::cerr << "[MPP] encode failed, exiting" << std::endl;
            break;
        }

        capture.requeue();
    }

    std::cout << "==> stopping ..." << std::endl;

    // 发送 EOS 并排空 MPP 内部缓冲
    encoder.flush([](const uint8_t* h264, size_t len) {
        (void)h264; (void)len; // 退出时丢弃最后几帧
    });

    rtc::Cleanup();
    return 0;
}
