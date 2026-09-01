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

#include <alsa/asoundlib.h>   // ALSA 音频采集 (板载 MIC)
#include <opus/opus.h>        // Opus 音频编码 (WebRTC 标准音频编解码)
#include <speex/speex_preprocess.h>  // SpeexDSP 实时降噪 + AGC

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

// 音频采集/编码参数 (板载 MIC -> Opus -> WebRTC 音频 track)
static constexpr const char* AUDIO_DEV      = "default";   // ALSA 录音设备 (arecord -l 的 card0)
static constexpr int         AUDIO_RATE     = 48000;       // 采样率 (Opus 原生 48kHz)
static constexpr int         AUDIO_CHANNELS = 2;           // 声道数 (立体声, 与 mic 采样一致)
static constexpr int         AUDIO_FRAME_MS = 20;          // Opus 帧长 20ms (960 样本 @48k)
static constexpr uint32_t    AUDIO_BITRATE  = 32000;       // Opus 目标码率 32 kbps
static constexpr int         AUDIO_PAYLOAD_TYPE = 111;     // Opus RTP payload type (避免与视频 96 冲突)

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

        fps_ = fps;
        if (!applyCfg(bitrate)) return false;

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

    // 构建完整编码配置并应用 (init 与运行时调码率共用)
    bool applyCfg(uint32_t bitrate) {
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
        mpp_enc_cfg_set_s32(cfg, "rc:fps_in_num", fps_);
        mpp_enc_cfg_set_s32(cfg, "rc:fps_in_denorm", 1);
        mpp_enc_cfg_set_s32(cfg, "rc:fps_out_flex", 0);
        mpp_enc_cfg_set_s32(cfg, "rc:fps_out_num", fps_);
        mpp_enc_cfg_set_s32(cfg, "rc:fps_out_denorm", 1);
        mpp_enc_cfg_set_s32(cfg, "rc:gop", fps_ * 2);
        mpp_enc_cfg_set_s32(cfg, "codec:type", MPP_VIDEO_CodingAVC);
        mpp_enc_cfg_set_s32(cfg, "h264:profile", 100);       // High
        mpp_enc_cfg_set_s32(cfg, "h264:level", 40);

        MPP_RET ret = mpi_->control(ctx_, MPP_ENC_SET_CFG, cfg);
        mpp_enc_cfg_deinit(cfg);
        if (ret != MPP_OK) {
            std::cerr << "[MPP] MPP_ENC_SET_CFG failed" << std::endl;
            return false;
        }
        current_bitrate_ = bitrate;
        return true;
    }

    // 运行时动态调整码率 (MPP 热更新码控, 不中断编码)
    void setBitrate(uint32_t bps) {
        if (!ctx_ || !mpi_ || bps == current_bitrate_) return;
        if (applyCfg(bps)) {
            std::cout << "[MPP] bitrate adjusted -> " << (bps / 1024) << "kbps" << std::endl;
        }
    }

    uint32_t currentBitrate() const { return current_bitrate_; }

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
    int fps_ = 30;
    uint32_t current_bitrate_ = 0;
    size_t src_stride_ = 0;   // 源 YUYV 行字节跨度
    size_t frame_size_ = 0;
    int64_t pts_ = 0;
};

// ----------------------------------------------------------------------------
// ALSA 音频采集 (板载 MIC, S16_LE 交错)
// ----------------------------------------------------------------------------
class AlsaCapture {
public:
    bool init(const char* dev, unsigned int rate, unsigned int channels, unsigned int frame_samples) {
        int err = snd_pcm_open(&handle_, dev, SND_PCM_STREAM_CAPTURE, 0);
        if (err < 0) {
            std::cerr << "[ALSA] open '" << dev << "' failed: " << snd_strerror(err) << std::endl;
            return false;
        }

        snd_pcm_hw_params_t* params;
        snd_pcm_hw_params_alloca(&params);
        snd_pcm_hw_params_any(handle_, params);

        snd_pcm_hw_params_set_access(handle_, params, SND_PCM_ACCESS_RW_INTERLEAVED);
        snd_pcm_hw_params_set_format(handle_, params, SND_PCM_FORMAT_S16_LE);
        snd_pcm_hw_params_set_channels(handle_, params, channels);

        unsigned int r = rate;
        snd_pcm_hw_params_set_rate_near(handle_, params, &r, 0);

        snd_pcm_uframes_t period = frame_samples;
        snd_pcm_hw_params_set_period_size_near(handle_, params, &period, 0);
        snd_pcm_hw_params_set_periods(handle_, params, 4, 0);   // 4 个 period 缓冲 (~80ms)

        if ((err = snd_pcm_hw_params(handle_, params)) < 0) {
            std::cerr << "[ALSA] hw_params failed: " << snd_strerror(err) << std::endl;
            snd_pcm_close(handle_);
            handle_ = nullptr;
            return false;
        }
        if ((err = snd_pcm_prepare(handle_)) < 0) {
            std::cerr << "[ALSA] prepare failed: " << snd_strerror(err) << std::endl;
            snd_pcm_close(handle_);
            handle_ = nullptr;
            return false;
        }

        rate_ = r;
        channels_ = channels;
        frame_samples_ = static_cast<unsigned int>(period);
        std::cout << "[ALSA] capture ready: " << rate_ << "Hz " << channels_
                  << "ch period=" << frame_samples_ << " frames" << std::endl;
        return true;
    }

    // 读取 frames 帧 (阻塞), 返回实际读取帧数; 负数表示错误, 0 表示欠载已恢复
    int read(int16_t* buf, unsigned int frames) {
        snd_pcm_sframes_t n = snd_pcm_readi(handle_, buf, frames);
        if (n < 0) {
            if (n == -EPIPE) {          // xrun, 恢复后返回 0
                snd_pcm_prepare(handle_);
                return 0;
            }
            return static_cast<int>(n); // 其他错误
        }
        return static_cast<int>(n);
    }

    ~AlsaCapture() {
        if (handle_) snd_pcm_close(handle_);
    }

private:
    snd_pcm_t* handle_ = nullptr;
    unsigned int rate_ = 0;
    unsigned int channels_ = 0;
    unsigned int frame_samples_ = 0;
};

// ----------------------------------------------------------------------------
// SpeexDSP 实时降噪 + AGC (板载 MIC 底噪/交流声抑制)
// 立体声交错 S16_LE 输入: 左右声道各一个 preprocess 实例, 就地处理
// ----------------------------------------------------------------------------
class SpeexNoiseReducer {
public:
    bool init(int rate, int frame_samples) {
        st_l_ = speex_preprocess_state_init(frame_samples, rate);
        st_r_ = speex_preprocess_state_init(frame_samples, rate);
        if (!st_l_ || !st_r_) return false;

        // 降噪强度 0~30 (约 -1~-30 dB 抑制量), 18 为较激进但保音质
        int denoise = 18;
        speex_preprocess_ctl(st_l_, SPEEX_PREPROCESS_SET_NOISE_SUPPRESS, &denoise);
        speex_preprocess_ctl(st_r_, SPEEX_PREPROCESS_SET_NOISE_SUPPRESS, &denoise);
        // 自动增益: 稳定输出电平, 防止降噪后音量忽大忽小
        int agc = 1;
        speex_preprocess_ctl(st_l_, SPEEX_PREPROCESS_SET_AGC, &agc);
        speex_preprocess_ctl(st_r_, SPEEX_PREPROCESS_SET_AGC, &agc);
        int level = 8000;   // AGC 目标电平 (0~32767)
        speex_preprocess_ctl(st_l_, SPEEX_PREPROCESS_SET_AGC_LEVEL, &level);
        speex_preprocess_ctl(st_r_, SPEEX_PREPROCESS_SET_AGC_LEVEL, &level);

        l_.resize(frame_samples);
        r_.resize(frame_samples);
        std::cout << "[AUDIO] speex denoise enabled (NS " << denoise << "dB, AGC on)" << std::endl;
        return true;
    }

    // 就地处理一帧交错立体声 S16_LE
    void process(int16_t* interleaved, int frames) {
        for (int i = 0; i < frames; ++i) {
            l_[i] = interleaved[2 * i];
            r_[i] = interleaved[2 * i + 1];
        }
        speex_preprocess_run(st_l_, l_.data());
        speex_preprocess_run(st_r_, r_.data());
        for (int i = 0; i < frames; ++i) {
            interleaved[2 * i]     = l_[i];
            interleaved[2 * i + 1] = r_[i];
        }
    }

    ~SpeexNoiseReducer() {
        if (st_l_) speex_preprocess_state_destroy(st_l_);
        if (st_r_) speex_preprocess_state_destroy(st_r_);
    }

private:
    SpeexPreprocessState* st_l_ = nullptr;
    SpeexPreprocessState* st_r_ = nullptr;
    std::vector<int16_t> l_, r_;
};

// ----------------------------------------------------------------------------
// Opus 编码器封装 (PCM S16_LE -> Opus 帧)
// ----------------------------------------------------------------------------
class OpusEncoderWrap {
public:
    bool init(int rate, int channels, uint32_t bitrate) {
        int err = 0;
        enc_ = opus_encoder_create(rate, channels, OPUS_APPLICATION_VOIP, &err);
        if (err != OPUS_OK || !enc_) {
            std::cerr << "[OPUS] encoder_create failed: " << opus_strerror(err) << std::endl;
            return false;
        }
        opus_encoder_ctl(enc_, OPUS_SET_BITRATE(static_cast<opus_int32>(bitrate)));
        // 语音场景关闭 DTX, 保持连续 (避免静音段浏览器检测异常)
        opus_encoder_ctl(enc_, OPUS_SET_DTX(0));
        channels_ = channels;
        return true;
    }

    // 返回编码后字节数 (>0), 负数错误
    int encode(const int16_t* pcm, int frame_samples, unsigned char* out, int max_out) {
        return opus_encode(enc_, pcm, frame_samples, out, max_out);
    }

    ~OpusEncoderWrap() {
        if (enc_) opus_encoder_destroy(enc_);
    }

private:
    OpusEncoder* enc_ = nullptr;
    int channels_ = 0;
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
        video.addSSRC(42, std::string("video-send"), std::string("stream1"), std::string("video"));

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

        // 创建 Opus 音频 track (SendOnly) —— 与视频共用 msid="stream1" 以便浏览器音视频同步
        rtc::Description::Audio audio("audio", rtc::Description::Direction::SendOnly);
        audio.addOpusCodec(AUDIO_PAYLOAD_TYPE);  // Opus, 默认 profile: minptime=10;stereo=1;useinbandfec=1
        audio.addSSRC(43, std::string("audio-send"), std::string("stream1"), std::string("audio"));

        audio_track_ = pc_->addTrack(audio);

        audio_rtp_config_ = std::make_shared<rtc::RtpPacketizationConfig>(
            43, "audio-send", AUDIO_PAYLOAD_TYPE, 48000);  // Opus RTP 时钟 48kHz
        auto audio_packetizer = std::make_shared<rtc::OpusRtpPacketizer>(audio_rtp_config_);
        // RTCP SR 上报: 音频与视频共用同一 start_time_ 时钟源, 浏览器据此将 RTP 时间戳
        // 对齐到同一 NTP 时间轴, 实现唇音同步 (lip-sync)
        audio_packetizer->addToChain(std::make_shared<rtc::RtcpSrReporter>(audio_rtp_config_));
        audio_track_->setMediaHandler(audio_packetizer);

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

    // 发送 Opus 音频帧 (与视频共用 start_time_ 时钟, 保证音视频时间戳同源)
    void send_audio(const uint8_t* data, size_t size) {
        if (!connected_ || !audio_track_ || !audio_track_->isOpen()) return;
        try {
            auto elapsed = std::chrono::duration<double>(
                std::chrono::steady_clock::now() - start_time_);
            audio_track_->sendFrame(reinterpret_cast<const std::byte*>(data), size,
                                    rtc::FrameInfo(elapsed));
        } catch (const std::exception& e) {
            std::cerr << "[RTC] audio send failed: " << e.what() << std::endl;
        }
    }

    // 注册码率调整回调 (监测面板自动优化用)
    void setAdjustHandler(std::function<void(uint32_t)> cb) { adjust_cb_ = std::move(cb); }

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
        } else if (type == "adjust") {
            // 监测面板自动优化: 浏览器上报 FPS/延迟, 动态调整视频码率
            std::string bps_str = json_get_str(text, "bitrate");
            if (!bps_str.empty() && adjust_cb_) {
                uint32_t bps = 0;
                try { bps = (uint32_t)std::stoul(bps_str); } catch (...) { return; }
                std::cout << "[SIG] adjust: bitrate -> " << (bps / 1024) << "kbps" << std::endl;
                adjust_cb_(bps);
            }
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
    std::shared_ptr<rtc::Track> audio_track_;
    std::shared_ptr<rtc::WebSocket> ws_;
    std::shared_ptr<rtc::RtpPacketizationConfig> rtpConfig_;
    std::shared_ptr<rtc::RtpPacketizationConfig> audio_rtp_config_;
    std::chrono::steady_clock::time_point start_time_{std::chrono::steady_clock::now()};
    std::string room_;
    std::string local_sdp_;
    std::atomic<bool> connected_{false};
    std::function<void(uint32_t)> adjust_cb_;
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
    streamer.setAdjustHandler([&encoder](uint32_t bps) { encoder.setBitrate(bps); });
    streamer.start(SIGNALING_URL, ROOM);

    // 3.5 初始化音频: ALSA 采集 -> SpeexDSP 降噪 -> Opus 编码, 独立线程 (与视频共用 start_time_ 时钟)
    AlsaCapture audio_cap;
    OpusEncoderWrap opus_enc;
    SpeexNoiseReducer noise_reducer;
    std::thread audio_thread;
    const int audio_frame_samples = AUDIO_RATE * AUDIO_FRAME_MS / 1000;  // 960 样本 (20ms)
    if (audio_cap.init(AUDIO_DEV, AUDIO_RATE, AUDIO_CHANNELS, audio_frame_samples) &&
        opus_enc.init(AUDIO_RATE, AUDIO_CHANNELS, AUDIO_BITRATE) &&
        noise_reducer.init(AUDIO_RATE, audio_frame_samples)) {
        audio_thread = std::thread([&]() {
            std::vector<int16_t> pcm(audio_frame_samples * AUDIO_CHANNELS);
            std::vector<uint8_t> opus_buf(1500);  // Opus 帧最大 < 1275 字节
            while (g_running) {
                // 凑满一个 Opus 帧 (处理 ALSA 可能的短读)
                int got = 0;
                while (got < audio_frame_samples && g_running) {
                    int n = audio_cap.read(pcm.data() + got * AUDIO_CHANNELS,
                                           audio_frame_samples - got);
                    if (n < 0) {
                        std::cerr << "[ALSA] read error: " << snd_strerror(n) << std::endl;
                        break;
                    }
                    if (n == 0) continue;  // xrun 已恢复
                    got += n;
                }
                if (got <= 0) continue;

                // SpeexDSP 实时降噪 + AGC (就地处理交错立体声)
                noise_reducer.process(pcm.data(), got);

                int bytes = opus_enc.encode(pcm.data(), got, opus_buf.data(),
                                            static_cast<int>(opus_buf.size()));
                if (bytes > 0) {
                    streamer.send_audio(opus_buf.data(), static_cast<size_t>(bytes));
                }
            }
        });
        std::cout << "[AUDIO] audio capture thread started" << std::endl;
    } else {
        std::cerr << "[AUDIO] audio init failed, continuing with video only" << std::endl;
    }

    std::cout << "==> streaming started, waiting for viewer ..." << std::endl;

    // 4. 采集-编码-推流主循环 (视频)
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

    // 停止音频线程 (阻塞 readi 最多 20ms 后返回)
    if (audio_thread.joinable()) audio_thread.join();

    // 发送 EOS 并排空 MPP 内部缓冲
    encoder.flush([](const uint8_t* h264, size_t len) {
        (void)h264; (void)len; // 退出时丢弃最后几帧
    });

    rtc::Cleanup();
    return 0;
}
