#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unix domain socket 客户端：供 CLI（--cmd）与 HTTP 网桥共用。

边界：只依赖 config.SOCK；不解析命令语义。
"""
import socket

from . import config


def request(cmd, timeout=None, sock=None):
    """发送一行命令并返回应答文本（已去除首尾空白）。

    timeout=None 表示阻塞等待（与旧 CLI 行为一致）；
    OSError（含连接失败/超时）由调用方决定如何呈现。
    """
    path = config.SOCK if sock is None else sock
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        if timeout is not None:
            s.settimeout(timeout)
        s.connect(path)
        s.sendall(cmd.encode())
        return s.recv(4096).decode().strip()
    finally:
        s.close()
