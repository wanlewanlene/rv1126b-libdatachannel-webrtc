# systemd/ —— 服务单元文件

本目录由 2026-10-30 的工作区整理产生（第二轮归类），原位于仓库根目录。
文件内容未改动，仅移动位置。

- `motor-ctl.service`  电机控制守护进程（motor_ctl.py）
- `motor-web.service`  电机 HTTP 网桥（motor_web.py，:8081）

注意：这是仓库内的参考副本，实际部署位置为板卡 `/etc/systemd/system/`，
其 ExecStart 指向板卡路径 `/userdata/rtc/...`，与本目录路径无关。
