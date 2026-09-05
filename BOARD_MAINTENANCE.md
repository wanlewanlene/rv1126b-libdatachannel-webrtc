# 板端（RV1126B ELF 板）系统设置与维护手册

> 2026-09-06 整理。记录反向推流功能涉及的所有板端系统级修改，供后续维护。
> 板卡 IP 为 DHCP 动态（热点拓扑 192.168.137.184，路由器拓扑 192.168.2.x），SSH 用户 `elf` 密码 `elf`。

## 一、服务与守护

### reverse-player.service（systemd 守护，已 enable）
- 路径：`/etc/systemd/system/reverse-player.service`
- 作用：播放器崩溃/退出 3 秒自动重启；开机自启（无需手动拉起）
- 常用命令：
  ```bash
  sudo systemctl status reverse-player    # 查看状态/日志
  sudo systemctl restart reverse-player   # 重启播放器
  sudo systemctl stop reverse-player      # 停止
  journalctl -u reverse-player -f         # 跟踪日志
  ```
- 注意：手动测试时若用 `pkill` 杀进程，systemd 会在 3 秒后重新拉起——属预期行为

### 信令（WebSocket.js）
- 未做 systemd，位于 `/userdata/rtc/server/`，手动拉起：
  ```bash
  cd /userdata/rtc/server && nohup node WebSocket.js > /tmp/sig.log 2>&1 &
  ```
- HTTP 3000（页面）/ WS 8080（信令）。重启板卡后需检查是否存活。

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
- 视频链路（零 CPU 转换）：`appsrc → h264parse → mppvideodec → rkximagesink sync=false`
  - **严禁**加 videoconvert/videoscale（CPU 转换 640x360→1024x600 只能跑 ~7fps，慢动作根因）
- appsrc：`max-bytes=1048576 block=false`（1MB 水位 + 非阻塞）；积压 >512KB 进入丢帧模式 + PLI；>900KB 持续 2 周期自动重建管道（自愈）
- H264 profile-level-id：offer 中强制 `42e028`（L4.0）；L3.1 会让 Chrome 降级 640x360
- 码率驱动：板端 `Track::requestBitrate()` → RtcpReceivingSession 发 REMB（1.5M→3M 阶梯）；PC 级 MediaHandler 的 send 回调**静默丢包不可用**（所有 RTCP 必须走 track 级路径）
- 浏览器端：`getUserMedia ideal 1280x720@30`；`sender.setParameters` maxBitrate=3M + degradationPreference=maintain-resolution

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

- lightdm conf.d 的 `xserver-command=X -s 0 dpms` 未被 Xorg 实际采纳（Xorg 参数里无 `-s 0`），依赖会话启动后的 xset（如有需要可挂到 LXDE autostart 首行）
- dw-mci（WiFi SDIO）空闲中断 ~1655 次/s，CPU 开销 <1%，暂不处理
- 视频窗口尺寸：初始按视频分辨率创建，管道重建后由 X 分配（尺寸可能不同），如需统一可给 rkximagesink 固定窗口
- HTTPS/wss（浏览器 getUserMedia 的安全上下文限制）与正向/反向推流页面合并仍在待办
