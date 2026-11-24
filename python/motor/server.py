#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unix domain socket 服务端：一行命令换一行应答。

边界：依赖 protocol.handle 与 config.SOCK；不做业务判断。
协议：AF_UNIX / SOCK_STREAM，客户端发送单行文本，服务端回 `应答\\n`。
"""
import os
import socket

from . import config
from .protocol import handle


def serve(motors, sock=None):
    """阻塞式应答循环。motors: {名称: Motor}。"""
    sock = config.SOCK if sock is None else sock
    if os.path.exists(sock):
        os.unlink(sock)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock)
    srv.listen(4)
    os.chmod(sock, 0o666)
    while True:
        conn, _ = srv.accept()
        try:
            data = conn.recv(256).decode(errors="ignore").strip()
            conn.sendall((handle(data, motors) + "\n").encode())
        except OSError:
            pass
        finally:
            conn.close()
