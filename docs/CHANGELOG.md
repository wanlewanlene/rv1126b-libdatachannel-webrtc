# 更新日志（Changelog）

版本号规则：`主版本.次版本.修订号`（x.y.z）；未特别指定时，每次发布在修订号上 +1。

## v1.2.0 — 2026-11-15

**模块化重构（目标：功能行为不变，仅调整结构与去重）**

- 目录重组：
  - `cpp/`：`main.cpp`、`reverse_player.cpp`（原仓库根）
  - `attic/`：`Video_capture_and_encoding.cpp`、`WebRTC_Connection_Management.cpp`（未被编译的早期草稿，去空格重命名并加说明）
  - `web/`：三个页面 + `web/assets/js/`（共享脚本，目录自包含便于整体部署）
  - `assets/`：仅保留图片资源
- Python 电机栈拆分（`python/motor_ctl.py` 481 行 → 11 个模块）：
  `config / gpio / pwm / encoder / motor / control / protocol / server / client / app / __init__`；
  `motor_ctl.py` 变为薄壳入口，**CLI、socket 协议、控制参数、状态 JSON 全部保持不变**
- 消除重复代码：
  - `motor_web.py` 改用 `motor.client.request()`（原自带 socket 实现）
  - `motor_selftest.py` 改用 `motor.gpio.Gpio`（原自带 export/unexport/gpio_path）
  - 页面电机面板 JS 抽为 `web/assets/js/motor-panel.js`（两页复用）
  - STUN/TURN 与信令 URL 抽为 `web/assets/js/webrtc-config.js`（三页复用）
  - 删除 `Reverse_pusher.html` 中被覆盖的重复 `ws.onopen`；清理两页重复的 `</html>`
- 保持兼容：`express.static` 同时挂载仓库根与 `web/`，`/Browser_client.html` 等 URL 不变；
  `build.sh` 源路径更新为 `cpp/main.cpp`
- 等价性验证：用重构基线 tag 导出旧版 `motor_ctl.py`，在 Fake GPIO/PWM/Encoder 下对比
  17 条命令解析、4 组目标各 36 拍速度环输出、开环方向/占空比、位置目标 —— 0 差异；
  三个页面内联脚本与共享脚本通过 `node --check`，外部引用与 DOM 依赖检查通过
- 留档：重构前 tag `refactor-baseline-v1.1.3` / 分支 `archive/pre-refactor-20261115`；
  重构后 tag `refactor-v1.2.0`；仓库外 `_refactor_archive/` 保存前后 bundle 与工作树 zip
- 说明：`cpp/` 两个单体文件本次未拆分（需板端工具链验证），计划见 `ARCHITECTURE.md` §6
- 版本号：v1.1.3 → v1.2.0（结构调整属次版本变更）

## v1.1.3 — 2026-10-30

- **工程结构整理（无功能改动）**：按类别归档，文件内容不变、未删除任何文件
  - `docs/`：全部文档（BOARD_MAINTENANCE / CHANGELOG / MOTOR_* / 接线说明）
  - `systemd/`：服务单元参考副本（motor-ctl / motor-web）
  - `python/`：Python 生产脚本（motor_ctl / motor_web / motor_selftest / reverse_player / rtc_push_ctl）
  - `assets/`：静态资源（raw_640.png）
  - `debug/`：调试与被 `.gitignore` 忽略的诊断资料（不入库）
- 根目录仅保留存在硬路径耦合的文件：C++ 源码（build.sh 同目录编译）、`WebSocket.js` + 页面 + `package.json`（`express.static(__dirname)`）、构建/启动脚本与 `cloudflared.exe`
- 同步修正内部引用：发布脚本文件清单、部署脚本上传路径、文档中的文件位置说明
- 版本号自增：v1.1.2 → v1.1.3

## v1.1.2 — 2026-09-14

- 按版本规则自增修订号（v1.1.1 → v1.1.2），同步更新 `package.json` 与本人 CHANGELOG
- 说明：本次为版本号自增发布，无功能性代码改动（内容与 v1.1.1 一致，仅版本记录变更）

## v1.1.1 — 2026-09-14

- 修正版本号记录：`package.json` 与发布标签对齐（此前停留 1.0.0，现为 1.1.1）
- 公网访问：页面经 Cloudflare 隧道暴露时使用**同源**信令 `wss://<host>/ws`（3000 端口内提供）与同源电机接口 `/motor`（反代至 8081），新增 `start_tunnel.bat` 一键启动
- 修复 `build.sh` 链接缺失音频库（`opus` / `speexdsp` / `alsa`，音频线程依赖）
- 加固 `motor-web.service`：取消启动限流、日志落盘 `/tmp/motor_web.log`、保持 `Restart=always`

## v1.1.0 — 2026-09-14

- 新增 MG310 + TB6612 电机控制栈：`motor_ctl.py`（sysfs GPIO + 软件 PWM + 4 倍频编码器 + 速度/位置环）、`motor-web.service`、`motor_web.py`（HTTP 网桥）
- 双端页与观看页集成电机面板（设速/开环/停止/刹车/实时状态/重启推流）
- 修复设速时电机反复启停：前馈标定（1.38 duty/rpm）+ 死区补偿 + 幅值域积分（修复反向）+ 斜率限制 + 测速低通 + 墙钟计时
- 新增 `WIRING_TB6612_RV1126B.txt` 接线说明与 `MOTOR_*.md` 系列文档

## v1.0.0 — 2026-09-08

- 双端推流稳定版：正向（板→浏览器）与反向（浏览器→板卡）双向音视频
- 三层自愈（积压 / SPS 参数集变化 / 输出停摆）、DMC 锁频、日志与磁盘治理
