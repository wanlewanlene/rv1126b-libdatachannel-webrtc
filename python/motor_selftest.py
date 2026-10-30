#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RV1126B 电机接入自检工具（板上运行，需 root）

用法:
  sudo python3 motor_selftest.py --info
  sudo python3 motor_selftest.py --loopback                 # 默认 176:182,177:183,178:184,179:185
  sudo python3 motor_selftest.py --loopback --pairs 176:182,178:184
  sudo python3 motor_selftest.py --encoder --seconds 10
  sudo python3 motor_selftest.py --video --seconds 60

报告写入 /userdata/rtc/motor_test_<时间戳>.json
"""
import argparse
import glob
import json
import os
import select
import subprocess
import time

GPIO = "/sys/class/gpio"
DEF_PAIRS = "176:182,177:183,178:184,179:185"


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()


def gpio_path(n, name):
    return "%s/gpio%d/%s" % (GPIO, n, name)


def export(n):
    if not os.path.isdir("%s/gpio%d" % (GPIO, n)):
        with open("%s/export" % GPIO, "w") as f:
            f.write(str(n))
        time.sleep(0.05)


def unexport(n):
    try:
        with open("%s/unexport" % GPIO, "w") as f:
            f.write(str(n))
    except Exception:
        pass


def do_info():
    r = {}
    r["kernel"] = sh("uname -r")
    r["pwm_dbg"] = sh("cat /sys/kernel/debug/pwm 2>/dev/null")
    r["pwm_dt"] = sh("for p in /proc/device-tree/pwm@*; do echo $(basename $p) $(tr -d '\\0' < $p/status); done")
    r["gpio_dbg"] = sh("cat /sys/kernel/debug/gpio 2>/dev/null")
    r["load"] = sh("uptime")
    r["services"] = sh("systemctl is-active rtc-signal reverse-player 2>/dev/null | tr '\\n' ' '")
    return r


def do_loopback(pairs, cycles=20):
    """驱动输出脚，用输入脚回读并统计中断次数；需先用杜邦线短接每对引脚"""
    results = []
    for pair in pairs:
        out_n, in_n = [int(x) for x in pair.split(":")]
        res = {"pair": pair, "ok": False}
        try:
            export(out_n)
            export(in_n)
            with open(gpio_path(out_n, "direction"), "w") as f:
                f.write("out")
            with open(gpio_path(in_n, "direction"), "w") as f:
                f.write("in")
            with open(gpio_path(in_n, "edge"), "w") as f:
                f.write("both")
            time.sleep(0.05)
            fd = open(gpio_path(in_n, "value"), "r")
            os.set_blocking(fd.fileno(), False)
            fd.read()  # 清中断标志
            events = 0
            start = time.time()
            for i in range(cycles):
                for v in (1, 0):
                    with open(gpio_path(out_n, "value"), "w") as f:
                        f.write(str(v))
                    time.sleep(0.02)
                    lvl = open(gpio_path(in_n, "value")).read().strip()
                    if lvl != str(v):
                        res["level_mismatch"] = "cycle=%d expect=%d got=%s" % (i, v, lvl)
            end = time.time()
            while time.time() - end < 0.2:
                if select.select([fd], [], [], 0.05)[0]:
                    fd.seek(0)
                    fd.read()
                    events += 1
            res["events"] = events
            res["elapsed_ms"] = round((end - start) * 1000)
            res["ok"] = "level_mismatch" not in res and events >= cycles
        except Exception as e:
            res["error"] = str(e)
        finally:
            unexport(out_n)
            unexport(in_n)
        results.append(res)
        print("[loopback] %s -> %s" % (pair, "PASS" if res["ok"] else "FAIL %s" % res))
    return results


def do_encoder(a_pin, b_pin, seconds):
    """统计 A 相边沿次数并按 B 相电平判方向（需手动转动电机或电机通电）"""
    for p in (a_pin, b_pin):
        export(p)
        with open(gpio_path(p, "direction"), "w") as f:
            f.write("in")
    with open(gpio_path(a_pin, "edge"), "w") as f:
        f.write("both")
    time.sleep(0.05)
    fd = open(gpio_path(a_pin, "value"), "r")
    os.set_blocking(fd.fileno(), False)
    fd.read()
    count = 0
    t0 = time.time()
    while time.time() - t0 < seconds:
        if select.select([fd], [], [], 0.2)[0]:
            fd.seek(0)
            fd.read()
            count += 1
    b_now = open(gpio_path(b_pin, "value")).read().strip()
    unexport(a_pin)
    unexport(b_pin)
    r = {"a": a_pin, "b": b_pin, "seconds": seconds, "edges": count,
         "edges_per_sec": round(count / float(seconds), 1), "b_level_now": b_now}
    print("[encoder] A=%d B=%d edges=%d (%.1f/s)" % (a_pin, b_pin, count, count / float(seconds)))
    return r


def do_video(seconds, interval=5):
    """采样系统负载，用于视频基线 / 叠加对比"""
    samples = []
    err_before = sh("dmesg | grep -c -i 'rkvdec\\|timeout' || true")
    t0 = time.time()
    while time.time() - t0 < seconds:
        samples.append({
            "t": round(time.time() - t0, 1),
            "load": sh("cut -d' ' -f1-3 /proc/loadavg"),
            "temp": sh("cat /sys/class/thermal/thermal_zone0/temp"),
            "mem_avail": sh("awk '/MemAvailable/{print $2}' /proc/meminfo"),
            "webrtc_cpu": sh("ps -o pcpu= -C rv1126b_webrtc_push 2>/dev/null | tr -d ' '"),
            "top5": sh("top -bn1 | sed -n '7,12p' | tr '\\n' ';'"),
        })
        time.sleep(interval)
    err_after = sh("dmesg | grep -c -i 'rkvdec\\|timeout' || true")
    return {"seconds": seconds, "samples": samples, "rkvdec_err_before": err_before,
            "rkvdec_err_after": err_after}


def main():
    ap = argparse.ArgumentParser(description="RV1126B 电机自检")
    ap.add_argument("--info", action="store_true")
    ap.add_argument("--loopback", action="store_true")
    ap.add_argument("--encoder", action="store_true")
    ap.add_argument("--video", action="store_true")
    ap.add_argument("--pairs", default=DEF_PAIRS)
    ap.add_argument("--seconds", type=int, default=30)
    ap.add_argument("--out", default="/userdata/rtc")
    args = ap.parse_args()

    if os.geteuid() != 0:
        print("请用 sudo 运行（需要写 /sys/class/gpio）")
        return 2

    report = {"ts": time.strftime("%Y%m%d_%H%M%S"), "args": vars(args)}
    if args.info or not (args.loopback or args.encoder or args.video):
        report["info"] = do_info()
    if args.loopback:
        report["loopback"] = do_loopback(args.pairs.split(","))
    if args.encoder:
        report["encoder"] = [do_encoder(182, 183, args.seconds // 2),
                             do_encoder(184, 185, args.seconds // 2)]
    if args.video:
        report["video"] = do_video(args.seconds)

    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "motor_test_%s.json" % report["ts"])
    with open(path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("报告: %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
