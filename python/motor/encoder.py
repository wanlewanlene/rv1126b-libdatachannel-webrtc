#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""增量式正交编码器：AB 相 4 倍频解码 + GPIO5 电平寄存器直读。

边界：依赖 gpio.Gpio 与 config；只负责"计数"，不做测速换算与闭环。
采样策略（按优先级自动选择）：
  1. 寄存器模式：mmap /dev/mem 直读 GPIO5 电平寄存器，~5kHz 单点采样，天然免疫对称毛刺对；
  2. sysfs 模式：poll() 监听 POLLPRI 边沿中断（寄存器不可用时回退）。
"""
import mmap
import os
import select
import struct
import threading
import time

from . import config

# [mmap 对象, 寄存器偏移]；自校准成功后填充，全进程共享
_REG = [None, None]


def calibrate():
    """自校准 GPIO5 电平寄存器偏移。

    前置条件：方向脚已摆出 AIN1=0,AIN2=1,BIN1=1,BIN2=0（config.CAL_PATTERN）。
    成功返回 True 并填充 _REG，失败返回 False。
    """
    try:
        f = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
        mm = mmap.mmap(f, 0x1000, offset=config.GPIO5_BASE)
        os.close(f)
    except OSError:
        return False
    for off in config.REG_CANDIDATES:
        try:
            v = struct.unpack_from("<I", mm, off)[0]
        except Exception:
            continue
        b = [(v >> n) & 1 for n in (18, 19, 20, 21)]
        if b == list(config.CAL_PATTERN):
            _REG[0], _REG[1] = mm, off
            return True
    return False


def reg_ready():
    """寄存器采样是否可用（calibrate() 是否成功）。"""
    return _REG[0] is not None


def reg_offset():
    """寄存器偏移；未校准时为 None。"""
    return _REG[1]


class Encoder(threading.Thread):
    """A/B 相 4 倍频解码（寄存器直读或 sysfs POLLPRI）"""

    TABLE = [0, 1, -1, 0, -1, 0, 0, 1, 1, 0, 0, -1, 0, -1, 1, 0]

    # 保持旧的调用方式 Encoder.calibrate() 可用
    calibrate = staticmethod(calibrate)

    def __init__(self, ga, gb, name, sign=1):
        super().__init__(name="enc-" + name, daemon=True)
        self.ga, self.gb, self.name = ga, gb, name
        self.sign = sign                     # 编码器方向符号（+1/-1）
        self.count = 0
        self.state = None
        self.pending = None
        self.last_change = 0.0
        self.run_flag = True
        self.bit_a = self.ga.n % 32          # GPIO5 bank 内位号
        self.bit_b = self.gb.n % 32

    def _level_reg(self):
        """返回 (A相,B相) 当前电平，来自寄存器直读"""
        v = struct.unpack_from("<I", _REG[0], _REG[1])[0]
        return (v >> self.bit_a) & 1, (v >> self.bit_b) & 1

    def _run_reg(self):
        """寄存器采样解码（~5kHz）：单点采样天然免疫对称毛刺对"""
        a, b = self._level_reg()
        self.state = (a << 1) | b
        while self.run_flag:
            time.sleep(0.0002)
            a, b = self._level_reg()
            new = (a << 1) | b
            if new == self.state:
                continue
            now = time.monotonic()
            if now - self.last_change < config.DEBOUNCE_S:
                continue
            self.count += self.sign * self.TABLE[(self.state << 2) | new]
            self.state = new
            self.last_change = now

    def run(self):
        for g in (self.ga, self.gb):
            g.dir("in")
        if _REG[0] is not None:
            return self._run_reg()
        self.ga.edge("both")
        self.gb.edge("both")
        time.sleep(0.05)
        fda = os.open(self.ga.path + "/value", os.O_RDONLY)
        fdb = os.open(self.gb.path + "/value", os.O_RDONLY)
        for fd in (fda, fdb):                     # 清中断标志
            os.lseek(fd, 0, os.SEEK_SET)
            os.read(fd, 16)
        self.state = (self._lv(fda) << 1) | self._lv(fdb)
        pl = select.poll()
        for fd in (fda, fdb):                     # 只关心 POLLPRI！
            pl.register(fd, select.POLLPRI)       # 注册 POLLIN 会一直就绪→空转
        while self.run_flag:
            evs = pl.poll(50)
            for fd, _ev in evs:                   # 必须 lseek+read 才能清 POLLPRI
                os.lseek(fd, 0, os.SEEK_SET)
                os.read(fd, 16)
            a, b = self._lv(fda), self._lv(fdb)
            new = (a << 1) | b
            if new != self.state:                 # 标准正交 4 倍频（实测信号干净）
                self.count += self.sign * self.TABLE[(self.state << 2) | new]
                self.state = new

    @staticmethod
    def _lv(fd):
        return 1 if os.pread(fd, 4, 0).startswith(b"1") else 0

    def read_reset(self):
        c, self.count = self.count, 0
        return c
