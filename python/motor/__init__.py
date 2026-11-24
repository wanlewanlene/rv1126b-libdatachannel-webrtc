#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MG310 + TB6612 电机控制包（RV1126B / Linux sysfs）。

模块分层（下方箭头 = 依赖方向，无环）：
    config                      纯常量，无依赖
    gpio      -> config         sysfs GPIO 封装
    pwm       -> config,gpio    软件 PWM
    encoder   -> config,gpio    正交编码器 4 倍频 / 寄存器直读
    motor     -> config,gpio,encoder,pwm   单电机方向 + 开环/速度环/位置环
    control   -> config,motor   10ms 调度
    protocol  -> config        文本命令解析（含 STBY 注入）
    server    -> config,protocol        Unix socket 服务端
    client    -> config                 Unix socket 客户端
    app       -> 以上全部               组合根（CLI/初始化/退出）

对外公共 API 只导出下面 __all__ 中的符号。
"""
from . import config
from .client import request
from .control import control_loop
from .encoder import Encoder, calibrate
from .gpio import Gpio
from .motor import Motor
from .protocol import bind_stby, handle, set_stby
from .pwm import SoftPwm
from .server import serve

__all__ = [
    "config",
    "Gpio",
    "SoftPwm",
    "Encoder",
    "calibrate",
    "Motor",
    "control_loop",
    "handle",
    "set_stby",
    "bind_stby",
    "serve",
    "request",
]
