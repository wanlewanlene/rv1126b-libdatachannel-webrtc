#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""进程装配：CLI 解析、硬件初始化、线程启动、信号与安全退出。

边界：唯一允许依赖全部下层模块的"组合根"；不实现控制律与协议细节。
"""
import argparse
import os
import signal
import threading

from . import config, encoder, protocol
from .client import request
from .control import control_loop
from .gpio import Gpio
from .motor import Motor
from .pwm import SoftPwm
from .server import serve


def build_runtime():
    """按顺序初始化 GPIO/PWM/编码器/电机，返回 (pwm, motors, stby)。

    GPIO 上电安全：PWM 先置 0；校准后方向脚恢复 0。
    """
    pins = [Gpio(config.MOTORS[n]["pwm"]) for n in config.MOTOR_NAMES]
    for p in pins:
        p.dir("out")
        p.write(0)                                  # 上电安全：占空比先为 0

    cal = [Gpio(n) for n in config.CAL_PINS]        # 方向脚摆出校准图案 (0,1,1,0)
    for g in cal:
        g.dir("out")
    for g, v in zip(cal, config.CAL_PATTERN):
        g.write(v)
    ok = encoder.calibrate()
    print("编码器采样:",
          ("寄存器模式 reg+0x%X" % encoder.reg_offset()) if ok else "寄存器不可用，退回 sysfs poll")
    for g in cal:
        g.write(0)                                  # 恢复安全态

    stby = None
    if config.STBY_GPIO:
        stby = Gpio(config.STBY_GPIO)
        stby.dir("out")
        stby.write(1)                               # 默认使能；急停用 stby 0
        protocol.bind_stby(stby)

    pwm = SoftPwm(pins)
    pwm.start()
    motors = {n: Motor(n, config.MOTORS[n], pwm, i)
              for i, n in enumerate(config.MOTOR_NAMES)}
    return pwm, motors, stby


def shutdown(pwm, motors, stby):
    """安全退出：停 PWM → 全部刹车 → 驱动芯片进待机。"""
    pwm.run_flag = False
    for m in motors.values():
        m.brake()
    if stby is not None:
        stby.write(0)
    print("已停止（PWM=0，刹车，STBY=待机）")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--cmd", help="发送命令后退出，如 'A speed 500'")
    ap.add_argument("--pwm-hz", type=float, default=config.PWM_HZ,
                    help="软件 PWM 频率（默认 1000）")
    a = ap.parse_args(argv)

    if a.cmd:                                  # 客户端模式
        print(request(a.cmd))
        return 0

    if os.geteuid() != 0:
        print("请用 sudo 运行（GPIO sysfs 需要 root）")
        return 2

    config.set_pwm_hz(a.pwm_hz)
    pwm, motors, stby = build_runtime()
    threading.Thread(target=control_loop, args=(list(motors.values()),),
                     name="ctrl", daemon=True).start()
    print("motor_ctl 启动：PWM %g Hz，socket %s" % (config.PWM_HZ, config.SOCK))

    def _on_term(signum, _frame):          # systemd stop 时也走安全退出
        raise KeyboardInterrupt()

    signal.signal(signal.SIGTERM, _on_term)
    try:
        serve(motors)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown(pwm, motors, stby)
    return 0
