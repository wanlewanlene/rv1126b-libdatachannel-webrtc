# 架构与模块划分（v1.2.0 重构后）

本文是仓库的**结构与接口权威说明**。修改代码结构时请同步更新本文与 `python/README.md`。

- 重构基线：`refactor-baseline-v1.1.3`（tag）/ `archive/pre-refactor-20261115`（分支）
- 重构完成：`refactor-v1.2.0`（tag，见文末"留档与回溯"）

## 1. 目录结构

```
rv1106/
├── cpp/                        C++ 板端程序（单文件单体，未拆分，见 §6）
│   ├── main.cpp                正向推流：V4L2 → MPP(H.264) + ALSA → Opus → WebRTC
│   └── reverse_player.cpp      反向播放：GStreamer + webrtbin 收流解码
├── attic/                      未被编译的历史草稿（仅存档，不参与构建）
│   ├── Video_capture_and_encoding.cpp
│   └── WebRTC_Connection_Management.cpp
├── python/
│   ├── motor/                  ★ 电机控制包（按职责拆分）
│   │   ├── config.py           常量：引脚/机械/整定/节拍/IPC（叶子模块）
│   │   ├── gpio.py             sysfs GPIO 封装
│   │   ├── pwm.py              软件 PWM（单线程多路）
│   │   ├── encoder.py          AB 相 4 倍频 + 寄存器直读 + 自校准
│   │   ├── motor.py            单电机：方向 + 开环 + 速度环 + 位置环
│   │   ├── control.py          10ms 调度：读计数/测速/跑环
│   │   ├── protocol.py         文本命令解析 + STBY 注入
│   │   ├── server.py           Unix socket 服务端
│   │   ├── client.py           Unix socket 客户端
│   │   ├── app.py              组合根：CLI/初始化/信号/安全退出
│   │   └── __init__.py         公共 API（__all__）
│   ├── motor_ctl.py            守护进程入口（薄壳，保持原 CLI）
│   ├── motor_web.py            电机 HTTP 网桥（:8081）
│   ├── motor_selftest.py       板端自检（info/loopback/encoder/video）
│   ├── reverse_player.py       反向播放器（GStreamer Python 版）
│   └── rtc_push_ctl.py         PC 端推流运维（IP 探测/重启/帧计数）
├── web/                        前端页面（自包含，可整体部署）
│   ├── Browser_client.html     观看端
│   ├── Dual_webrtc.html        双端页（正向+反向）
│   ├── Reverse_pusher.html     反向推流页
│   └── assets/js/
│       ├── motor-panel.js      电机面板共享逻辑（两页复用）
│       └── webrtc-config.js    STUN/TURN 与信令 URL（三页复用）
├── assets/                     静态图片（raw_640.png）
├── docs/                       文档（本文/接线/设计/测试/维护/变更）
├── systemd/                    服务单元参考副本
├── WebSocket.js                Node 信令服务 + HTTP(:3000) + /motor 反代
├── package.json                Node 依赖与启动入口
├── build.sh                    编译 cpp/main.cpp
├── Compilation_script.sh       Docker 内构建入口
├── run.sh                      板端启动（TURN + 信令 + 推流）
├── start_tunnel.bat            Cloudflare 隧道（外网访问）
├── backup_to_rootfs.sh         工程全量备份到 rootfs
└── dockerfile.Dockerfile       交叉编译环境
```

## 2. Python 电机包：分层与依赖

依赖方向单向、无环（箭头指向被依赖方）：

```
config  ←  gpio  ←  pwm
config  ←  gpio  ←  encoder  ←  motor  ←  control
config  ←  protocol  ←  server
config  ←  client
                    app  →（以上全部）
```

| 模块 | 职责（内聚边界） | 明确**不**负责 |
| --- | --- | --- |
| `config` | 唯一参数来源；`set_pwm_hz()` 运行时改频 | 任何硬件访问 |
| `gpio` | export/dir/read/write/edge/fd/unexport | PWM 语义、编码器解码 |
| `pwm` | 占空比 → 电平时序，边沿精度 | 方向、闭环 |
| `encoder` | 计数增减（4 倍频），寄存器校准 | 测速换算、闭环 |
| `motor` | 单机方向真值表、开环、速度环、位置目标 | 调度、命令解析 |
| `control` | 10ms/100ms 节拍、测速、位置状态机推进 | 底层 IO |
| `protocol` | 文本命令 → Motor 方法调用；STBY 注入 | socket、进程生命周期 |
| `server` | AF_UNIX 收发一行命令 | 业务判定 |
| `client` | 一行命令的请求/应答 | 命令语义 |
| `app` | 组装、root 检查、信号、安全退出 | 控制律、协议细节 |

公共 API 见 `python/motor/__init__.py` 的 `__all__`：

```python
config, Gpio, SoftPwm, Encoder, calibrate, Motor,
control_loop, handle, set_stby, bind_stby, serve, request
```

## 3. 运行时控制流

```
systemd ──> python3 /userdata/rtc/motor_ctl.py --pwm-hz 500
              └─ motor.app.main()
                   ├─ config.set_pwm_hz(500)
                   ├─ build_runtime(): GPIO → 校准 → PWM → Motor×2
                   ├─ Thread(control_loop)   # 10ms 读计数 / 100ms 跑速度环
                   └─ serve(motors)          # 阻塞接收命令

浏览器 ──> WebSocket.js(:3000/motor) ──> motor_web.py(:8081) ──> client.request()
                                                                    │ AF_UNIX
CLI   ──> motor_ctl.py --cmd "A rpm 60" ────────────────────────────┘
                                                                    ▼
                                                        /run/motor_ctl.sock
```

节拍说明：控制线程 10ms 一拍读编码器并推进位置环；每 10 拍（100ms）用计数差算 rpm 并执行速度环 `rpm_step`。速度环为"前馈 + PI + 死区 + 斜率 + 反向归零"，位置环为"远端比例 + 近端脉冲爬行 + 过冲抱闸"。

## 4. 接口契约

### 4.1 Unix socket 文本协议（`/run/motor_ctl.sock`）

- 传输：`AF_UNIX` / `SOCK_STREAM`，请求单行文本（≤256B），应答单行 + `\n`
- 命令：

| 命令 | 说明 |
| --- | --- |
| `A\|B speed <v>` | 开环，v ∈ [-1000,1000] 千分比 |
| `A\|B rpm <n>` | 速度闭坏，目标为输出轴 rpm |
| `A\|B pos <deg>` | 位置模式，相对当前角度转动 deg |
| `A\|B stop` / `brake` | 滑行 / 短接刹车 |
| `A\|B status` | 单机状态 JSON |
| `status` | 双机状态 JSON |
| `stby <0\|1>` | 驱动芯片使能（未接 GPIO 时返回提示，不报错） |

- 应答：`ok` / `err: <reason>` / JSON 字符串

### 4.2 HTTP 网桥（`:8081`，经 3000 端口以 `/motor` 反代）

| 路径 | 说明 |
| --- | --- |
| `GET /api/status` | 透传 `status` 的 JSON |
| `GET /api/cmd?m=A&op=rpm&v=60` | 转发命令，返回 `{"reply": "..."}` |
| `GET /api/push_restart` | 重启推流进程 |
| `GET /ping` | 存活探测 |

### 4.3 前端共享接口（`web/assets/js/`）

| 文件 | 暴露 | 依赖 DOM |
| --- | --- | --- |
| `motor-panel.js` | `mcmd(m, op)`、`mrestart()`、`mrefresh()` | `#aCtl` `#bCtl` `#motorStatus` |
| `webrtc-config.js` | `WEBRTC_CFG`、`iceServers(ip)`、`signalingUrl(ip, port)` | 无（参数传入） |

`express.static` 同时挂载仓库根与 `web/`，因此 `/Browser_client.html` 等**原有 URL 保持不变**。

### 4.4 C++ 程序 CLI

| 程序 | 参数 | 默认 |
| --- | --- | --- |
| `rv1126b_webrtc_push` | 无 | 信令 `ws://127.0.0.1:8080`，房间 `cam1` |
| `reverse_player` | `argv[1]` 信令 URL，`argv[2]` 房间 | `ws://127.0.0.1:8080`，`reverse1` |

## 5. 部署映射（仓库 → 板端）

| 仓库路径 | 板端路径 | 说明 |
| --- | --- | --- |
| `python/motor_ctl.py` + `python/motor/` | `/userdata/rtc/motor_ctl.py` + `/userdata/rtc/motor/` | **包必须随入口一起上传** |
| `python/motor_web.py` | `/userdata/rtc/motor_web.py` | 依赖 `/userdata/rtc/motor/` |
| `WebSocket.js` | `/userdata/rtc/server/WebSocket.js` | `package.json` 同目录 |
| `web/`（整目录） | `/userdata/rtc/server/web/` | 页面与 `assets/js` 保持相对布局 |
| `cpp/main.cpp` 编译产物 | `/userdata/rtc/bin/rv1126b_webrtc_push` | `build.sh` 输出 |
| `cpp/reverse_player.cpp` 编译产物 | `/userdata/rtc/reverse_player_bin` | 见 `BOARD_MAINTENANCE.md` |

## 6. 本次未拆分的部分及原因

`cpp/main.cpp`（961 行）与 `cpp/reverse_player.cpp`（约 1090 行）仍为单体文件：

- 依赖 `libdatachannel` / `librockchip_mpp` / GStreamer / Opus / SpeexDSP，**只能在板端或交叉编译容器内验证**；当前开发机无该工具链，拆分后无法证明"行为不变"。
- 两者存在约 10 处同构逻辑（JSON 转义、信令分发、ICE 应用、PC 建连、SSRC/PT 常量），已记录为后续工作：抽 `cpp/common/`（json 工具、信令消息、RTP 常量）后再分文件。
- 在完成板端编译验证前，保持单文件是风险最低的选择。

## 7. 留档与回溯

| 时点 | 形式 | 内容 |
| --- | --- | --- |
| 重构前 | tag `refactor-baseline-v1.1.3` | 指向 `45690ce`（v1.1.3 发布点） |
| 重构前 | 分支 `archive/pre-refactor-20261115` | 同一点位，便于长期保留 |
| 重构前 | 仓库外快照 | `../_refactor_archive/rv1106_pre-refactor_20261115.bundle`（全历史）+ `..._worktree_20261115.zip`（工作树） |
| 重构后 | tag `refactor-v1.2.0` | 本次重构完成点 |
| 重构后 | 仓库外快照 | `../_refactor_archive/rv1106_post-refactor_*.{bundle,zip}` |

对比命令：

```bash
git diff refactor-baseline-v1.1.3 refactor-v1.2.0 --stat
git diff refactor-baseline-v1.1.3 refactor-v1.2.0 -- python/motor_ctl.py
```

回退：`git checkout refactor-baseline-v1.1.3 -- .`（或直接 `git switch archive/pre-refactor-20261115`）。
