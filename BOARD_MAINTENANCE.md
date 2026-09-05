# 板端（RV1126B ELF 板）系统设置与维护手册

> 2026-09-06 整理。记录反向推流功能涉及的所有板端系统级修改，供后续维护。
> 板卡 IP 为 DHCP 动态（热点拓扑 192.168.137.184，路由器拓扑 192.168.2.x），SSH 用户 `elf` 密码 `elf`。

## 一、服务与守护（双 systemd 服务，已 enable）

### rtc-signal.service（信令）
- 路径：`/etc/systemd/system/rtc-signal.service`
- User=elf，工作目录 `/userdata/rtc/server`，崩溃 2 秒自动重启，开机自启
- 端口：HTTP 3000（页面）/ WS 8080（信令）

### reverse-player.service（播放器）
- 路径：`/etc/systemd/system/reverse-player.service`
- **User=root**（需要 evdev 键盘读取 + DRM master 权限）
- After/Wants=rtc-signal；崩溃/断连 3 秒自动重启；开机自启
- **待命模式（重要）**：启动时不创建显示管道；收到浏览器推流请求（request_offer）时自动 `systemctl stop lightdm`（释放 DRM master）→ 建管道全屏显示；按 **Q 键** 销毁管道 → 自动 `systemctl start lightdm` 回桌面 → 播放器回待命。kmssink 与桌面 X 因 DRM master 互斥，由播放器按推流状态自动切换
- 常用命令：
  ```bash
  sudo systemctl status reverse-player rtc-signal
  sudo systemctl restart reverse-player
  journalctl -u reverse-player -f
  ```
- 注意：手动 `pkill` 杀进程后 systemd 会重新拉起——属预期行为

## 二、息屏问题（曾导致视频管道卡死）

### 根因链
无操作计时息屏（light-locker / xscreensaver）→ DPMS Off → 内核关闭 VOP CRTC/DSI
→ rkximagesink 等待 vblank 死锁 → GStreamer 管道冻结 → 视频窗口卡死。

### 已实施的禁用项（勿恢复，否则息屏即卡死）
| 项 | 位置 | 状态 |
|---|---|---|
| light-locker（主凶：空闲计时强制 DPMS） | `chmod -x /usr/bin/light-locker` + `/root/.config/autostart/light-locker.desktop`(Hidden) + `~/.config/autostart/light-locker.desktop`(Hidden) | 已根除（去执行位最可靠，用户级 Hidden 会被会话复活绕过） |
| xscreensaver | 用户级 `~/.config/lxsession/LXDE/autostart` 覆盖（只留 lxpanel/pcmanfm） | 已禁 |
| lxsession 内置息屏 | `~/.config/lxsession/LXDE/desktop.conf` 增加 `[SS]` 段：`saver/command=/bin/true`、`dpms/command=/bin/true` | 已禁 |
| X 屏保/DPMS | `xset s off; xset s noblank; xset -dpms`（当前会话）+ `/etc/lightdm/lightdm.conf.d/50-disable-dpms.conf`（`xserver-command=X -s 0 dpms`） | 已禁（注：实测 lightdm conf.d 未被 Xorg 参数采纳，以 xset 为准，X 显示 timeout 0 / DPMS Disabled） |
| console blank | 内核参数 `consoleblank=0` | 默认已 0 |

### 验证息屏是否被禁
```bash
DISPLAY=:0 xset q | grep -A2 'DPMS'      # 期望: DPMS is Disabled（或超时全 0）
pgrep -af 'xscreensaver|light-locker'    # 期望: 无输出
```

### 如需息屏功能（省电）
只关背光，不动显示管线（推流不中断）：
```bash
echo 4 | sudo tee /sys/class/backlight/backlight-dsi/bl_power   # 息屏(仅背光)
echo 0 | sudo tee /sys/class/backlight/backlight-dsi/bl_power   # 亮屏
```
**切勿**用 DPMS/fb blank 方式息屏（会触发上述卡死链路）。

## 三、曾失控并已处理的后台进程

| 进程 | 问题 | 处置 |
|---|---|---|
| blueman（蓝牙管理器） | 双会话各拉一份，4 进程共吃 94% CPU（蓝牙扫描死循环），系统卡顿 | 杀进程 + `/etc/xdg/autostart/blueman.desktop` 改名 `.disabled` |
| root 残留 LXDE 桌面会话 | 第二套桌面并行跑（blueman/xscreensaver 双份来源） | 已清理，只保留 elf 会话 |
| rkvdec timeout / rk3x-i2c timeout | 息屏切换期间伴生（显示管线关闭导致），息屏禁用后不再出现 | 观察项 |

## 四、显示与性能参数

- MIPI 屏：**1024x600@56Hz**（DSI 4lane，300Mbps/lane；面板原生分辨率，勿尝试提高）
- **视频链路（当前）：`appsrc → h264parse → mppvideodec → kmssink driver-name=rockchip sync=false`**
  - kmssink DRM 直出：720p 由显示控制器**硬件缩放**全屏，零 CPU；无 X 合成层，无息屏/卡死问题
  - **桌面环境已停用**（`systemctl disable lightdm`），设备为专用视频终端；按 Q 键或停止推流后桌面可按需拉起（待命模式自动切换）
  - 曾用 rkximagesink（X 方案）：CPU 转换 7fps 慢动作、X 息屏 vblank 死锁两大问题均因此产生，勿回退
  - **严禁**加 videoconvert/videoscale（CPU 转换 640x360→1024x600 只能跑 ~7fps，慢动作根因）
- appsrc：`max-bytes=1048576 block=false`（1MB 水位 + 非阻塞）；积压 >512KB 进入丢帧模式 + PLI；>900KB 持续 2 周期自动重建管道（自愈）
- H264 profile-level-id：offer 中强制 `42e028`（L4.0）；L3.1 会让 Chrome 降级 640x360
- 码率驱动：板端 `Track::requestBitrate()` → RtcpReceivingSession 发 REMB（1.5M→3M 阶梯）；PC 级 MediaHandler 的 send 回调**静默丢包不可用**（所有 RTCP 必须走 track 级路径）
- 浏览器端：`getUserMedia ideal 1280x720@30`；`sender.setParameters` maxBitrate=3M + degradationPreference=maintain-resolution

## 四.5、音频（P12 SPKOUT）

- 声卡：`rockchip,rv1126b-acodec`（card 0）；P12 = SPKOUT（Speaker 输出）
- **acodec 默认静音**（DAC Digital=0、Speaker/spkswitch off）——播放器启动时自动配置（手测 3.1.8 章节）：
  ```bash
  amixer -c rockchiprv1126b sset 'Speaker' on
  amixer -c rockchiprv1126b sset 'spkswitch' on
  amixer -c rockchiprv1126b sset 'DAC Digital' 250   # 0-510, 250≈-18.75dB
  ```
- 音频管道（低延迟）：`appsrc(max-bytes=65536 block=false, do-timestamp) → opusdec → audioconvert → audioresample → alsasink sync=false latency-time=20000 buffer-time=80000`
- 音画同步：两路均"到达即播"（视频无 PTS——PTS 会触发 mppvideodec 节流），缓冲最小化后实测已同步

## 五、磁盘/日志维护

- rootfs（/dev/mmcblk0p6，6.9G）曾到 91%，journald 清理后 89%：
  ```bash
  sudo journalctl --vacuum-size=50M
  df -h /
  ```
- RTW WiFi 驱动每 2 秒刷 dmesg（H2C debug 日志），属驱动行为，可忽略
- tcpdump 已安装（抓包诊断 RTCP：`sudo tcpdump -i wlan0 -n udp -w /tmp/x.pcap`，媒体走 wlan0，eth0 为 DOWN）

## 六、关键部署位置

| 文件 | 位置 |
|---|---|
| 播放器二进制 | `/userdata/rtc/reverse_player_bin` |
| 播放器源码 | `/userdata/rtc/reverse_player.cpp`（Windows 侧同名文件为源） |
| 推流页面 | `/userdata/rtc/server/Reverse_pusher.html` |
| 信令 | `/userdata/rtc/server/WebSocket.js` |
| libdatachannel | `/userdata/rtc/lib/libdatachannel.so`（0.24.2） |
| 板卡编译命令 | `cd /userdata/rtc && g++ -O2 -std=c++17 reverse_player.cpp -o reverse_player_bin -I/userdata/rtc/ldc_install/include -L/userdata/rtc/lib -ldatachannel $(pkg-config --cflags --libs gstreamer-1.0 gstreamer-app-1.0) -pthread` |

## 七、已知未决项

- dw-mci（WiFi SDIO）空闲中断 ~1655 次/s，CPU 开销 <1%，暂不处理
- RTW WiFi 驱动每 2 秒刷 dmesg（H2C debug 日志），可忽略
- HTTPS/wss（浏览器 getUserMedia 的安全上下文限制）与正向/反向推流页面合并仍在待办
- 如需恢复桌面常驻：`sudo systemctl enable --now lightdm`（注意与推流显示互斥，播放器待命模式会自动处理）
