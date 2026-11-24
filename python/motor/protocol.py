#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文本命令行协议：解析与应用。

边界：依赖 config 与 Motor 的公开方法；不碰 socket、不管进程生命周期。
命令格式（单行 ASCII）：
    stby <0|1>
    status
    A|B speed <千分比 -1000~1000>
    A|B rpm <输出轴转速>
    A|B pos <角度>
    A|B stop | brake | status
"""
import json

# 驱动芯片使能脚（运行时由 app 注入，未接则为 None）
_stby = None


def bind_stby(gpio):
    """注入 STBY 的 Gpio 对象；gpio=None 表示未接。"""
    global _stby
    _stby = gpio


def set_stby(on):
    """STBY 全局使能：0=驱动芯片待机（电机无输出），1=工作"""
    if _stby is None:
        return "stby 未接 GPIO（硬件拉高，忽略）"
    _stby.write(1 if on else 0)
    return "ok"


def handle(cmd, motors):
    """应用一行命令，返回应答文本（不含换行）。"""
    p = cmd.split()
    if not p:
        return "err: empty"
    if p[0].lower() == "stby":
        try:
            return set_stby(int(p[1]))
        except (IndexError, ValueError):
            return "err: args"
    if p[0].lower() == "status":
        return json.dumps({k: m.status() for k, m in motors.items()}, ensure_ascii=False)
    m = motors.get(p[0].upper())
    if m is None:
        return "err: motor (A/B)"
    act = p[1].lower() if len(p) > 1 else "status"
    try:
        if act == "speed":
            m.open_loop(int(p[2]))
        elif act == "stop":
            m.stop()
        elif act == "brake":
            m.brake()
        elif act == "rpm":
            m.set_rpm(float(p[2]))
        elif act == "pos":
            m.set_pos(float(p[2]))
        elif act == "status":
            return json.dumps(m.status(), ensure_ascii=False)
        else:
            return "err: cmd"
    except (IndexError, ValueError):
        return "err: args"
    return "ok"
