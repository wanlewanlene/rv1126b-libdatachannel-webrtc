# python/ —— Python 生产脚本

## 结构

```
python/
├── motor/                 电机控制包（v1.2.0 由 motor_ctl.py 拆分而来）
│   ├── config.py          引脚/机械/整定/节拍/IPC 常量（唯一参数来源）
│   ├── gpio.py            sysfs GPIO 封装
│   ├── pwm.py             软件 PWM
│   ├── encoder.py         AB 相 4 倍频 + 寄存器直读
│   ├── motor.py           单电机方向/开环/速度环/位置环
│   ├── control.py         10ms 调度
│   ├── protocol.py        文本命令解析
│   ├── server.py          Unix socket 服务端
│   ├── client.py          Unix socket 客户端
│   ├── app.py             组合根（CLI/初始化/退出）
│   └── __init__.py        公共 API
├── motor_ctl.py           守护进程入口（薄壳，CLI 与旧版一致）
├── motor_web.py           电机 HTTP 网桥（:8081）
├── motor_selftest.py      板端自检（--info/--loopback/--encoder/--video）
├── reverse_player.py      板端反向播放器（GStreamer/webrtcbin 方案）
└── rtc_push_ctl.py        PC 端推流运维工具
```

完整模块边界、依赖图与接口契约见 `docs/ARCHITECTURE.md`。

## 常用命令

```bash
# 守护进程（需 root；systemd 用 --pwm-hz 500）
sudo python3 motor_ctl.py
sudo python3 motor_ctl.py --cmd "A rpm 60"
sudo python3 motor_ctl.py --cmd status

# HTTP 网桥
python3 motor_web.py            # 监听 0.0.0.0:8081

# 板端自检
sudo python3 motor_selftest.py --info
sudo python3 motor_selftest.py --loopback --pairs 176:182,178:184
```

## 作为库使用

```python
from motor import Gpio, Motor, SoftPwm, control_loop, handle, request

print(request("A rpm 60", timeout=2))     # 与守护进程通信
```

## 部署说明

板卡上实际运行位置为 `/userdata/rtc/`（`systemd/motor-ctl.service`、`motor-web.service`
的 `ExecStart` 指向该路径）：

- 必须**同时上传** `motor_ctl.py` 与 `motor/` 整个包目录，否则 `import motor` 失败
- `motor_web.py` 同样依赖 `motor/`（复用 `motor.client`）
- 上传时保持相对位置：`/userdata/rtc/motor_ctl.py` + `/userdata/rtc/motor/*.py`
