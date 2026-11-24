#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""motor_web：电机控制 HTTP 网桥（:8081 → /run/motor_ctl.sock）

socket 通信由 motor.client 统一提供，本文件只负责 HTTP 路由与 JSON 包装。

GET /api/status              → 电机状态 JSON
GET /api/cmd?m=A&op=rpm&v=300 → 转发命令（op: speed/rpm/pos/stop/brake/stby）
GET /api/push_restart        → 重启推流进程
GET /ping                    → 存活探测
"""
import json
import os
import subprocess
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from motor.client import request


def forward(cmd):
    """转发一行命令到 motor_ctl 守护进程；失败时返回 JSON 错误体。"""
    try:
        return request(cmd, timeout=2) or "ok"
    except OSError as e:
        return json.dumps({"err": str(e)}, ensure_ascii=False)


class H(BaseHTTPRequestHandler):
    def _reply(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/api/status":
            try:
                self._reply(json.loads(forward("status")))
            except Exception:
                self._reply({"err": "bad status"}, 502)
        elif u.path == "/api/cmd":
            m = (q.get("m", [""])[0] or "").upper()
            op = (q.get("op", [""])[0] or "").lower()
            v = q.get("v", [""])[0]
            if op == "stby":
                self._reply({"reply": forward("stby " + (v or "1"))})
            elif m in ("A", "B") and op in ("speed", "rpm", "pos", "stop", "brake"):
                argv = [m, op] + ([v] if v != "" else [])
                self._reply({"reply": forward(" ".join(argv))})
            else:
                self._reply({"err": "bad params"}, 400)
        elif u.path == "/api/push_restart":
            subprocess.run(["pkill", "-f", "rv1126b_webrtc_push"],
                           capture_output=True)
            time.sleep(1.2)
            subprocess.Popen(
                ["./bin/rv1126b_webrtc_push"],
                cwd="/userdata/rtc",
                env=dict(os.environ, LD_LIBRARY_PATH="/userdata/rtc/lib"),
                stdout=open("/tmp/rtc_run.log", "ab"),
                stderr=subprocess.STDOUT,
                start_new_session=True)
            time.sleep(3)
            self._reply({"reply": "push restarted"})
        elif u.path == "/ping":
            self._reply({"ok": True})
        else:
            self._reply({"err": "not found"}, 404)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8081), H).serve_forever()
