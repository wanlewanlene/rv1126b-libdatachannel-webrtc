#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Linux sysfs GPIO 封装。

边界：只依赖 config.GPIO；不感知 PWM/编码器/电机语义。
职责：export/unexport、方向、电平读写、边沿配置、可 poll 的文件对象。
"""
import os
import time

from . import config


class Gpio:
    """一个 sysfs GPIO 引脚（按全局 GPIO 编号访问）。"""

    def __init__(self, n):
        self.n = n
        self.path = "%s/gpio%d" % (config.GPIO, n)
        if not os.path.isdir(self.path):
            with open(config.GPIO + "/export", "w") as f:
                f.write(str(n))
            time.sleep(0.02)

    def dir(self, d):
        try:                                        # 清上次进程残留的 edge 中断配置
            with open(self.path + "/edge", "w") as f:
                f.write("none")
        except OSError:
            pass
        with open(self.path + "/direction", "w") as f:
            f.write(d)

    def write(self, v):
        with open(self.path + "/value", "w") as f:
            f.write("1" if v else "0")

    def read(self):
        with open(self.path + "/value") as f:
            return f.read().strip() == "1"

    def edge(self, e):
        with open(self.path + "/edge", "w") as f:
            f.write(e)

    def fd(self):
        return open(self.path + "/value", "r")

    def unexport(self):
        try:
            with open(config.GPIO + "/unexport", "w") as f:
                f.write(str(self.n))
        except OSError:
            pass
