# python/ —— Python 生产脚本

本目录由 2026-10-30 的工作区整理产生（第三轮归类），原位于仓库根目录。
文件名与内容均未改动（仅移动位置），未被删除。

- `motor_ctl.py`      电机控制守护进程：sysfs GPIO + 软件 PWM + 4 倍频编码器 + 速度/位置环 + unix socket 命令
- `motor_web.py`      电机 HTTP 网桥（:8081，网页面板后端；反代入口 `/motor`）
- `motor_selftest.py` 板端自检工具（--info/--loopback/--encoder/--video）
- `reverse_player.py` 板端反向播放器（GStreamer/webrtcbin 方案）
- `rtc_push_ctl.py`   PC 端推流运维工具（IP 探测 / restart / stop / 帧计数验证）

## 部署位置说明
板卡上实际运行的文件位于 `/userdata/rtc/`（`motor-ctl.service`、`motor-web.service`
的 ExecStart 均指向该路径），与本目录位置无关；上传时请使用 `python/<文件名>`。
