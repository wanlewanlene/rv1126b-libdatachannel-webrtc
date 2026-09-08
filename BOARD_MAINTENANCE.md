# 板端（RV1126B ELF 板）系统设置与维护手册

> 2026-09-06 整理。记录反向推流功能涉及的所有板端系统级修改，供后续维护。
> 板卡 IP 为 DHCP 动态（热点拓扑 192.168.137.184，路由器拓扑 192.168.2.x），SSH 用户 `elf` 密码 `elf`。

## 一、服务与守护（双 systemd 服务，已 enable）

### rtc-signal.service（信令）
- 路径：`/etc/systemd/system/rtc-signal.service`
- User=elf，工作目录 `/userdata/rtc/server`，崩溃 2 秒自动重启，开机自启
- 端口：HTTP 3000（页面）/ WS 8080（信令）

### rtc-forward.service（正向推流：板卡摄像头 → 浏览器）
- 路径：`/etc/systemd/system/rtc-forward.service`（2026-09-06 新增）
- User=root，`ExecStart=/bin/bash /userdata/rtc/run.sh`（run.sh 内含 TURN 拉起、MIC 增益固化、路由修复）
- `ExecStartPre=/bin/sleep 8`：等 USB 摄像头枚举完成（过早启动会 open /dev/video52 failed）
- 崩溃 5 秒自动重启；开机自启。此前正向推流靠手动 run.sh，**断电后不会自启**（曾造成"推流中断"假故障）

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

## 二、断电/异常关机后的恢复（SOP）

1. 上电后等待 **1-2 分钟**（USB 摄像头枚举 + 服务启动），再检查：
   ```bash
   systemctl is-active rtc-signal rtc-forward reverse-player   # 期望 3 个 active
   pgrep -af 'rv1126b_webrtc_push|reverse_player_bin|node WebSocket'
   ```
2. 三者均已 `enabled`，正常情况下自动恢复；若某服务未起：`sudo systemctl restart <服务名>`
3. **检查磁盘**（rootfs 满会导致 MIPI 死机、服务异常）：
   ```bash
   df -h /            # >90% 需清理
   sudo journalctl --vacuum-size=30M
   sudo apt-get clean
   sudo du -xh --max-depth=3 /var /root 2>/dev/null | sort -rh | head -8   # 找大目录
   ```
   已知大户：`/var/log`(586M)、`/root/elf-env`(220M python 环境)、`/root/libdatachannel`(202M 源码)
4. 内核检查（排除文件系统损坏/驱动初始化失败）：
   ```bash
   dmesg | grep -iE 'error|fail|ext4|fsck|corrupt|dsi|vop|drm|panic' | grep -viE 'RTW|gmac|dmc' | tail -20
   ```
   正常情况只会出现 `rkcif ... sensor info failed`（板子未接 MIPI CSI 摄像头，属预期）
5. 屏状态确认：
   ```bash
   cat /sys/class/backlight/backlight-dsi/bl_power   # 0=亮
   cat /sys/class/drm/card0-DSI-1/dpms               # On
   ```
6. **“屏幕卡住/进不了桌面”通常是预期状态**：lightdm 已禁用（推流模式无需桌面），反向推流未开始时屏上无内容。需要桌面：`sudo systemctl start lightdm`；推流时播放器会自动停桌面、按 Q 返回桌面。

## 三、息屏问题（曾导致视频管道卡死）

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

## 四.5、音频（P12 SPKOUT / 板载 MIC）

- 声卡：`rockchip,rv1126b-acodec`（card 0）；P12 = SPKOUT（Speaker 输出）；板载 MIC = 采集
- **`/etc/asound.conf`（关键！pulseaudio 移除后必须存在）**：
  ```
  pcm.!default {
      type plug
      slave.pcm "hw:0,0"
  }
  ctl.!default {
      type hw
      card 0
  }
  ```
  作用：把 ALSA `default` 设备直连硬件。**pulseaudio 已被移除**（`chmod -x /usr/bin/pulseaudio`），无此文件时 `default` 采集/播放失效——表现为：正向推流采集 closed 无声、反向播放器 asrc 线程自旋占 87% CPU + 无声
- **acodec 默认静音**（DAC Digital=0、Speaker/spkswitch off）——反向播放器启动时自动配置：
  ```bash
  amixer -c rockchiprv1126b sset 'Speaker' on
  amixer -c rockchiprv1126b sset 'spkswitch' on
  amixer -c rockchiprv1126b sset 'DAC Digital' 250   # 0-510, 250≈-18.75dB
  ```
- **正向推流 MIC 采集增益**（run.sh 固化）：`ACodec_LP PGA Gain 84%`、`ACodec_LP Digital Gain 75%`、`HPF on 60Hz`
- 采集/播放设备状态检查：`cat /proc/asound/card0/pcm0c/sub0/status`（采集）/ `pcm0p`（播放），期望 RUNNING 且 owner_pid 为对应进程
- 音频管道（低延迟，反向播放）：`appsrc(max-bytes=65536 block=false, do-timestamp) → opusdec → audioconvert → audioresample → alsasink device=plughw:0,0 sync=false latency-time=20000 buffer-time=80000`
  - **device=plughw:0,0 必须显式指定**（default 会解析到已移除的 pulse）
- 音画同步：两路均"到达即播"（视频无 PTS——PTS 会触发 mppvideodec 节流），缓冲最小化后实测已同步
- **pulseaudio 已移除的原因**：与正向推流 ALSA 采集占卡冲突时 alsa-sink 线程忙等占满 2 核（99.9%+88.2%），导致反向视频间歇卡顿+无声；且其 alsa-sink 状态卡 OPEN 不真正启动

## 五、磁盘/日志维护

- **2026-09-08 大清理**（rootfs 92% → 77%，释放 ~1.1G），完整记录在板卡
  `/userdata/archive/cleanup-2026-09-08.log`。要点：
  - **转移至 `/userdata/archive/`（/userdata 分区 47G 空闲，与 rootfs 物理分离）**：
    root-libdatachannel 202M、elf-env 220M、pyenv/dot-pyenv 34M、webrtc 15M、root-Desktop 8.6M、
    rtc-backup（main.cpp 6 个历史版本 + 旧日志）1.6M
  - **删除**：/var/log 三日志清空 502M、/userdata/rtc/__pycache__
  - **RTW 日志根治**：`/etc/rsyslog.d/01-rtw-filter.conf` 过滤 RTW/rtl8821c/H2C 消息（kern.log 已零增长）
  - **logrotate 限流**：`/etc/logrotate.d/rsyslog-sizecap` 三日志 size 50M / rotate 2 / compress
  - **pipewire/wireplumber/pipewire-pulse 已 global mask**（崩溃循环刷 syslog ~230B/s，桌面组件无桌面时无用）
  - 残余 syslog 增速 ~100B/s（root 用户实例启动消息等），logrotate 兜底，无需再处理
- rootfs 常态检查：`df -h /`（>90% 需清理）
- tcpdump 已安装（抓包诊断 RTCP：`sudo tcpdump -i wlan0 -n udp -w /tmp/x.pcap`，媒体走 wlan0，eth0 为 DOWN）
- 重编 libdatachannel 时需从 `/userdata/archive/root-libdatachannel` 移回 `/root/libdatachannel`

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
