#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MG310 + TB6612 电机控制（RV1126B / Linux sysfs）——CLI 入口。

实现已按职责拆分到 motor/ 包（config/gpio/pwm/encoder/motor/control/protocol/server/client/app），
本文件只保留命令行入口与旧的模块级别名，命令行用法与行为保持不变。

后台常驻 + unix socket 命令：
  sudo python3 motor_ctl.py                 # 启动守护进程（前台）
  sudo python3 motor_ctl.py --cmd "A speed 500"
命令：A|B speed <千分比 -1000~1000> | stop | brake | rpm <输出轴转速> | pos <角度> | status
引脚（P1 排针）：A: pwm176 in1_178 in2_179 ea182 eb183 ; B: pwm177 180 181 184 185
"""
from motor import config as _config
from motor.app import main

# 向后兼容：旧代码/文档可能引用 motor_ctl.CFG 与 motor_ctl.PWM_HZ
CFG = _config.MOTORS
PWM_HZ = _config.PWM_HZ


if __name__ == "__main__":
    raise SystemExit(main())
