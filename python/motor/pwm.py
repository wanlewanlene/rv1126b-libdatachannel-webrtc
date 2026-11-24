#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""软件 PWM：单线程驱动多路 sysfs GPIO，占空比 0~1000（千分比）。

边界：只依赖 gpio.Gpio；不感知电机方向与闭环逻辑。
职责：把占空比请求转为按周期翻转的电平，并以自旋保证边沿精度。
"""
import os
import threading
import time

from . import config


class SoftPwm(threading.Thread):
    """软件 PWM：一个线程驱动 2 路，占空比 0~1000（千分比）"""

    def __init__(self, pins):
        super().__init__(name="softpwm", daemon=True)
        self.pins = pins                      # [Gpio, Gpio]
        self.duty = [0, 0]
        self.lock = threading.Lock()
        self.run_flag = True
        self.period = 1.0 / config.PWM_HZ

    def set(self, ch, thousandths):
        with self.lock:
            self.duty[ch] = max(0, min(1000, int(thousandths)))

    def run(self):
        # 提升调度优先级（失败不影响功能）
        try:
            os.sched_setscheduler(0, os.SCHED_FIFO, os.sched_param(10))
        except OSError:
            pass
        period = self.period
        t_next = time.monotonic()
        while self.run_flag:
            with self.lock:
                d0, d1 = self.duty
            t0 = time.monotonic()
            for i, di in ((0, d0), (1, d1)):          # 上升沿：占空比 >0 才输出高
                if di:
                    self.pins[i].write(1)
            offs = sorted((d / 1000.0 * period, i)
                          for i, d in ((0, d0), (1, d1)) if 0 < d < 1000)
            for t_off, i in offs:                     # 到点关断
                self._wait(t0 + t_off)
                self.pins[i].write(0)
            time.sleep(max(0.0, t0 + period - time.monotonic()))

    @staticmethod
    def _wait(t):
        """睡眠到目标时刻，最后 150µs 用自旋保证边沿精度"""
        while True:
            dt = t - time.monotonic()
            if dt <= 0:
                return
            if dt > 0.00015:
                time.sleep(dt - 0.0001)
            else:
                while time.monotonic() < t:
                    pass
