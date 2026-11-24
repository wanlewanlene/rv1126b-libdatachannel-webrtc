#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单路直流有刷电机：方向控制 + 开环 + 速度环 + 位置环状态机。

边界：依赖 gpio（方向脚）、encoder（计数）、pwm（占空比）与 config；
      不负责调度（control.py）与命令解析（protocol.py）。
"""
import time

from . import config
from .encoder import Encoder
from .gpio import Gpio


class Motor:
    def __init__(self, name, cfg, pwm, ch):
        self.name, self.pwm, self.ch = name, pwm, ch
        self.inv = bool(cfg.get("inv"))
        self.in1, self.in2 = Gpio(cfg["in1"]), Gpio(cfg["in2"])
        self.in1.dir("out")
        self.in2.dir("out")
        self.enc = Encoder(Gpio(cfg["ea"]), Gpio(cfg["eb"]), name,
                           sign=(-1 if cfg.get("enc_inv") else 1))
        self.enc.start()
        self.mode = "idle"
        self.target = 0.0
        self.total = 0
        self.integral = 0.0
        self.iout = 0.0        # 速度环积分（duty 单位，幅值域）
        self.prev_out = 0.0    # 上一拍输出（斜率限制用）
        self.rpm_f = None      # 测速低通状态
        self.pos_target = None
        self.pos_deadline = 0.0
        self.last_err = None
        self.pos_cool = 0.0
        self.next_pulse = 0.0
        self.pulse_duty = config.POS_PULSE_DUTY
        self.last_pulse_total = None
        self._apply(0)

    # ---------------- 底层输出 ----------------
    def _apply(self, v):
        """-1000~1000 千分比：>0 正转，<0 反转，0 滑行（IN1=IN2=0）。"""
        v = max(-1000, min(1000, int(v)))
        if v > 0:
            self.in1.write(1 if self.inv else 0)
            self.in2.write(0 if self.inv else 1)
        elif v < 0:
            self.in1.write(0 if self.inv else 1)
            self.in2.write(1 if self.inv else 0)
        else:
            self.in1.write(0)
            self.in2.write(0)
        self.pwm.set(self.ch, abs(v))

    def stop(self):
        self.mode = "idle"
        self.iout = 0.0
        self.prev_out = 0.0
        self._apply(0)

    def brake(self):
        self.mode = "idle"
        self.iout = 0.0
        self.prev_out = 0.0
        self.pwm.set(self.ch, 0)
        self.in1.write(1)
        self.in2.write(1)

    def hold_brake(self):
        """短接刹车但保持当前模式（位置环/速度环用）"""
        self.pwm.set(self.ch, 0)
        self.in1.write(1)
        self.in2.write(1)

    def open_loop(self, v):
        self.mode = "open"
        self.iout = 0.0
        self.prev_out = float(v)
        self._apply(v)

    # ---------------- 速度环 ----------------
    def set_rpm(self, r):
        self.mode = "rpm"
        self.target = float(r)
        self.iout = 0.0            # 保留 prev_out：变目标时输出平滑过渡
        self.rpm_f = None          # 重置测速滤波（新目标重新收敛）

    def rpm_step(self, rpm):
        """速度环一拍（100ms）：前馈定主输出，PI 小幅修正；输出不反向、不进刹车
        —— 前馈标定准确后占空比始终在平衡点附近，电机不会进入"冲过头→停→再冲"循环"""
        # 测速低通：抑制 100ms 窗口的量化抖动（±15rpm），减小占空比纹波
        a = config.RPM_LPF_NEW
        self.rpm_f = rpm if self.rpm_f is None else a * rpm + (1.0 - a) * self.rpm_f
        err = self.target - self.rpm_f
        sgn = 1.0 if self.target >= 0 else -1.0
        e = err * sgn                        # 归一化：>0 需加速，<0 超速
        base = max(config.DB_DUTY, abs(config.FF_DUTY * self.target)) * sgn
        # 抗积分饱和：输出将饱和且误差继续同向push时冻结积分
        # 积分存于幅值域（e>0 增大），应用时乘 sgn → 反向目标也正确
        slew = config.SLEW
        out_p = base + config.KP * err + sgn * self.iout
        if not (out_p > 1000 - slew and e > 0) and not (out_p < -1000 + slew and e < 0):
            self.iout = max(-config.I_CLAMP, min(config.I_CLAMP, self.iout + config.KI * e))
        out = base + config.KP * err + sgn * self.iout
        if out * sgn < 0:                    # 需求反向（大幅降速）→ 滑行并清积分
            out = 0.0
            self.iout = 0.0
        elif e > 0 and abs(out) < config.DB_DUTY:   # 落后且输出低于死区：给死区占空比
            out = config.DB_DUTY * sgn
        out = max(self.prev_out - slew, min(self.prev_out + slew, out))
        if self.prev_out * out < 0:          # 需要换向：先归零
            out = 0.0
        self.prev_out = out
        self._apply(out)

    # ---------------- 位置环 ----------------
    def set_pos(self, deg):
        self.mode = "pos"
        self.pos_target = self.total + deg / 360.0 * config.CPR
        self.pos_deadline = time.monotonic() + config.POS_TIMEOUT
        self.last_err = None
        self.pos_cool = 0.0
        self.next_pulse = 0.0
        self.pulse_duty = config.POS_PULSE_DUTY
        self.last_pulse_total = None

    def status(self):
        return dict(mode=self.mode, target=self.target, total=self.total,
                    duty=self.pwm.duty[self.ch], iout=round(self.iout, 1),
                    last_rpm=getattr(self, "last_rpm", 0.0))
