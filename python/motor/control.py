#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""控制环调度：10ms 节拍读编码器，100ms 跑速度环，逐拍跑位置环。

边界：依赖 motor.Motor 与 config；只管调度，不含控制律。
"""
import time

from . import config


def control_loop(motors, dt=config.CTRL_DT, speed_win=config.SPEED_WIN):
    """10ms 节拍：读计数；每 100ms 计算速度并跑 PI / 位置环"""
    tick = 0
    last = {}
    last_t = {}
    while True:
        t0 = time.monotonic()
        tick += 1
        for m in motors:
            d = m.enc.read_reset()
            m.total += d
            if tick % speed_win == 0:                       # 100ms 一次
                now = time.monotonic()
                if m.name in last:
                    dtt = max(0.02, now - last_t.get(m.name, dt * speed_win))
                    rpm = (m.total - last[m.name]) / config.CPR / dtt * 60.0
                    if m.mode == "rpm":
                        m.rpm_step(rpm)
                        m.last_rpm = m.rpm_f
                last[m.name] = m.total
                last_t[m.name] = now
            if m.mode == "pos" and m.pos_target is not None:
                err = m.pos_target - m.total
                ad = abs(err)
                now = time.monotonic()
                crossed = m.last_err is not None and ((err > 0) != (m.last_err > 0))
                if ad <= config.POS_EPS:                     # 到位：抱闸锁死
                    m.hold_brake()
                    m.pos_target = None
                    m.mode = "idle"
                elif crossed or now >= m.pos_deadline:
                    m.hold_brake()                           # 过冲/超时：立即刹车
                    m.pos_cool = now + config.POS_COOL
                elif now < m.pos_cool:
                    m.hold_brake()                           # 刹车保持期
                elif ad <= config.POS_ZONE:                  # 近目标：脉冲爬行
                    if now >= m.next_pulse:
                        m._apply((config.POS_PULSE_DUTY if err > 0 else -config.POS_PULSE_DUTY))
                        m.next_pulse = now + config.POS_PULSE_MS
                        m.last_pulse_total = m.total
                    else:
                        m.hold_brake()
                        if m.last_pulse_total is not None and m.total == m.last_pulse_total:
                            m.pulse_duty = min(config.POS_PULSE_MAX,
                                               m.pulse_duty + config.POS_PULSE_STEP)  # 没动：加力
                else:                                        # 远端：比例逼近
                    m._apply(max(-config.POS_LIMIT, min(config.POS_LIMIT, config.POS_KP * err)))
                m.last_err = err
            else:
                m.last_err = None
        time.sleep(max(0, dt - (time.monotonic() - t0)))
