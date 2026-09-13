#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MG310 + TB6612 电机控制（RV1126B / Linux sysfs）

后台常驻 + unix socket 命令：
  sudo python3 motor_ctl.py                 # 启动守护进程（前台）
  sudo python3 motor_ctl.py --cmd "A speed 500"
命令：A|B speed <千分比 -1000~1000> | stop | brake | rpm <输出轴转速> | pos <角度> | status
引脚（P1 排针）：A: pwm176 in1_178 in2_179 ea182 eb183 ; B: pwm177 180 181 184 185
"""
import argparse
import json
import mmap
import os
import select
import signal
import socket
import struct
import sys
import threading
import time

CFG = {
    "A": dict(pwm=176, in1=178, in2=179, ea=182, eb=183, inv=False, enc_inv=True),
    "B": dict(pwm=177, in1=180, in2=181, ea=184, eb=185, inv=False, enc_inv=False),
}
GPIO = "/sys/class/gpio"
PPR = 13.0            # 编码器线数（电机轴）
GEAR = 20.409         # 减速比
MULT = 4              # 4 倍频
CPR = PPR * GEAR * MULT      # 输出轴每圈计数 ≈1061.3
PWM_HZ = 1000         # 软件 PWM 频率
DEBOUNCE_S = 0.00005  # 编码器状态确认窗（真实状态间隔 ≥290µs，毛刺对 <100µs）
SOCK = "/run/motor_ctl.sock"
# STBY 使能：电机功率全部来自外部 12V（D153B VM），与板端电源无关。
# 默认 STBY 硬接模块 3V3（模块自供电）；若改接板端 GPIO 做软件急停，填编号（如 186/224）
STBY_GPIO = None
STBY = None            # 运行时的 Gpio 对象
ENC_REG = [None, None]  # [mmap对象, 寄存器偏移] GPIO5 电平寄存器（自校准后填充）
GPIO5_BASE = 0x21900000  # gpiochip5 parent platform/21900000.gpio


def sh(cmd):
    return os.system(cmd)


class Gpio:
    def __init__(self, n):
        self.n = n
        self.path = "%s/gpio%d" % (GPIO, n)
        if not os.path.isdir(self.path):
            with open(GPIO + "/export", "w") as f:
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
            with open(GPIO + "/unexport", "w") as f:
                f.write(str(self.n))
        except OSError:
            pass


class SoftPwm(threading.Thread):
    """软件 PWM：一个线程驱动 2 路，占空比 0~1000（千分比）"""

    def __init__(self, pins):
        super().__init__(name="softpwm", daemon=True)
        self.pins = pins                      # [Gpio, Gpio]
        self.duty = [0, 0]
        self.lock = threading.Lock()
        self.run_flag = True
        self.period = 1.0 / PWM_HZ

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


class Encoder(threading.Thread):
    """A/B 相 4 倍频解码（epoll 监听 sysfs value 的 POLLPRI）"""

    TABLE = [0, 1, -1, 0, -1, 0, 0, 1, 1, 0, 0, -1, 0, -1, 1, 0]

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

    @staticmethod
    def calibrate():
        """自校准 GPIO5 电平寄存器偏移：要求方向脚已摆出 AIN1=0,AIN2=1,BIN1=1,BIN2=0"""
        try:
            f = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
            mm = mmap.mmap(f, 0x1000, offset=GPIO5_BASE)
            os.close(f)
        except OSError:
            return False
        for off in (0x50, 0x58, 0x00, 0x64, 0x54):
            try:
                v = struct.unpack_from("<I", mm, off)[0]
            except Exception:
                continue
            b = [(v >> n) & 1 for n in (18, 19, 20, 21)]
            if b == [0, 1, 1, 0]:
                ENC_REG[0], ENC_REG[1] = mm, off
                return True
        return False

    def _level_reg(self):
        """返回 (A相,B相) 当前电平，来自寄存器直读"""
        v = struct.unpack_from("<I", ENC_REG[0], ENC_REG[1])[0]
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
            if now - self.last_change < DEBOUNCE_S:
                continue
            self.count += self.sign * self.TABLE[(self.state << 2) | new]
            self.state = new
            self.last_change = now

    def run(self):
        for g in (self.ga, self.gb):
            g.dir("in")
        if ENC_REG[0] is not None:
            return self._run_reg()
        import select as _sel
        self.ga.edge("both")
        self.gb.edge("both")
        time.sleep(0.05)
        fda = os.open(self.ga.path + "/value", os.O_RDONLY)
        fdb = os.open(self.gb.path + "/value", os.O_RDONLY)
        for fd in (fda, fdb):                     # 清中断标志
            os.lseek(fd, 0, os.SEEK_SET)
            os.read(fd, 16)
        self.state = (self._lv(fda) << 1) | self._lv(fdb)
        pl = _sel.poll()
        for fd in (fda, fdb):                     # 只关心 POLLPRI！
            pl.register(fd, _sel.POLLPRI)         # 注册 POLLIN 会一直就绪→空转
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


FF_DUTY = 1.38           # 前馈：duty/rpm（开环标定 150~1000 duty 平均斜率）
DB_DUTY = 60             # 死区补偿：维持转动所需最小占空比（起动力矩靠积分顶上去）
KP, KI = 2.0, 0.2        # 速度环 PI（前馈承担主输出，PI 只做小幅修正）
I_CLAMP = 400            # 积分限幅（duty 单位）：预留负载变化的自适应权限
SLEW = 50                # 每拍(100ms)占空比最大变化：软启动+防猛冲
POS_KP = 0.6              # 位置环比例（千分比 / count）
POS_EPS = 8               # 到位判据（count）
POS_ZONE = 60             # 进入脉冲爬行区（count）
POS_PULSE_DUTY = 60       # 脉冲占空比（自适应上限 400）
POS_PULSE_MS = 0.04       # 脉冲间隔（秒）


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
        self.pulse_duty = POS_PULSE_DUTY
        self.last_pulse_total = None
        self._apply(0)

    def _apply(self, v):
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

    def set_rpm(self, r):
        self.mode = "rpm"
        self.target = float(r)
        self.iout = 0.0            # 保留 prev_out：变目标时输出平滑过渡
        self.rpm_f = None          # 重置测速滤波（新目标重新收敛）

    def rpm_step(self, rpm):
        """速度环一拍（100ms）：前馈定主输出，PI 小幅修正；输出不反向、不进刹车
        —— 前馈标定准确后占空比始终在平衡点附近，电机不会进入"冲过头→停→再冲"循环"""
        # 测速低通：抑制 100ms 窗口的量化抖动（±15rpm），减小占空比纹波
        self.rpm_f = rpm if self.rpm_f is None else 0.6 * rpm + 0.4 * self.rpm_f
        err = self.target - self.rpm_f
        sgn = 1.0 if self.target >= 0 else -1.0
        e = err * sgn                        # 归一化：>0 需加速，<0 超速
        base = max(DB_DUTY, abs(FF_DUTY * self.target)) * sgn
        # 抗积分饱和：输出将饱和且误差继续同向push时冻结积分
        # 积分存于幅值域（e>0 增大），应用时乘 sgn → 反向目标也正确
        out_p = base + KP * err + sgn * self.iout
        if not (out_p > 1000 - SLEW and e > 0) and not (out_p < -1000 + SLEW and e < 0):
            self.iout = max(-I_CLAMP, min(I_CLAMP, self.iout + KI * e))
        out = base + KP * err + sgn * self.iout
        if out * sgn < 0:                    # 需求反向（大幅降速）→ 滑行并清积分
            out = 0.0
            self.iout = 0.0
        elif e > 0 and abs(out) < DB_DUTY:   # 落后且输出低于死区：给死区占空比
            out = DB_DUTY * sgn
        out = max(self.prev_out - SLEW, min(self.prev_out + SLEW, out))
        if self.prev_out * out < 0:          # 需要换向：先归零
            out = 0.0
        self.prev_out = out
        self._apply(out)

    def set_pos(self, deg):
        self.mode = "pos"
        self.pos_target = self.total + deg / 360.0 * CPR
        self.pos_deadline = time.monotonic() + 30
        self.last_err = None
        self.pos_cool = 0.0
        self.next_pulse = 0.0
        self.pulse_duty = POS_PULSE_DUTY
        self.last_pulse_total = None

    def status(self):
        return dict(mode=self.mode, target=self.target, total=self.total,
                    duty=self.pwm.duty[self.ch], iout=round(self.iout, 1),
                    last_rpm=getattr(self, "last_rpm", 0.0))


def control_loop(motors, dt=0.01, speed_win=10):
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
                    rpm = (m.total - last[m.name]) / CPR / dtt * 60.0
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
                if ad <= POS_EPS:                     # 到位：抱闸锁死
                    m.hold_brake()
                    m.pos_target = None
                    m.mode = "idle"
                elif crossed or now >= m.pos_deadline:
                    m.hold_brake()                    # 过冲/超时：立即刹车
                    m.pos_cool = now + 0.05
                elif now < m.pos_cool:
                    m.hold_brake()                    # 刹车保持期
                elif ad <= POS_ZONE:                  # 近目标：脉冲爬行
                    if now >= m.next_pulse:
                        m._apply((POS_PULSE_DUTY if err > 0 else -POS_PULSE_DUTY))
                        m.next_pulse = now + POS_PULSE_MS
                        m.last_pulse_total = m.total
                    else:
                        m.hold_brake()
                        if m.last_pulse_total is not None and m.total == m.last_pulse_total:
                            m.pulse_duty = min(400, m.pulse_duty + 40)   # 没动：加力
                else:                                 # 远端：比例逼近
                    m._apply(max(-400, min(400, POS_KP * err)))
                m.last_err = err
            else:
                m.last_err = None
        time.sleep(max(0, dt - (time.monotonic() - t0)))


def set_stby(on):
    """STBY 全局使能：0=驱动芯片待机（电机无输出），1=工作"""
    global STBY
    if STBY is None:
        return "stby 未接 GPIO（硬件拉高，忽略）"
    STBY.write(1 if on else 0)
    return "ok"


def handle(cmd, motors):
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


def serve(motors):
    if os.path.exists(SOCK):
        os.unlink(SOCK)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCK)
    srv.listen(4)
    os.chmod(SOCK, 0o666)
    while True:
        conn, _ = srv.accept()
        try:
            data = conn.recv(256).decode(errors="ignore").strip()
            conn.sendall((handle(data, motors) + "\n").encode())
        except OSError:
            pass
        finally:
            conn.close()


def main():
    global PWM_HZ
    ap = argparse.ArgumentParser()
    ap.add_argument("--cmd", help="发送命令后退出，如 'A speed 500'")
    ap.add_argument("--pwm-hz", type=float, default=PWM_HZ, help="软件 PWM 频率（默认 1000）")
    a = ap.parse_args()

    if a.cmd:                                  # 客户端模式
        c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        c.connect(SOCK)
        c.sendall(a.cmd.encode())
        print(c.recv(4096).decode().strip())
        c.close()
        return 0

    if os.geteuid() != 0:
        print("请用 sudo 运行（GPIO sysfs 需要 root）")
        return 2
    PWM_HZ = a.pwm_hz
    pins = [Gpio(CFG["A"]["pwm"]), Gpio(CFG["B"]["pwm"])]
    for p in pins:
        p.dir("out")
        p.write(0)                                  # 上电安全：占空比先为 0
    cal = [Gpio(n) for n in (178, 179, 180, 181)]   # 方向脚摆出校准图案 (0,1,1,0)
    for g in cal:
        g.dir("out")
    for g, v in zip(cal, (0, 1, 1, 0)):
        g.write(v)
    ok = Encoder.calibrate()
    print("编码器采样:", ("寄存器模式 reg+0x%X" % ENC_REG[1]) if ok else "寄存器不可用，退回 sysfs poll")
    for g in cal:
        g.write(0)                                  # 恢复安全态
    global STBY
    if STBY_GPIO:
        STBY = Gpio(STBY_GPIO)
        STBY.dir("out")
        STBY.write(1)                               # 默认使能；急停用 stby 0
    pwm = SoftPwm(pins)
    pwm.start()
    motors = {n: Motor(n, CFG[n], pwm, i) for i, n in enumerate(("A", "B"))}
    threading.Thread(target=control_loop, args=(list(motors.values()),),
                     name="ctrl", daemon=True).start()
    print("motor_ctl 启动：PWM %g Hz，socket %s" % (PWM_HZ, SOCK))

    def _on_term(signum, _frame):          # systemd stop 时也走安全退出
        raise KeyboardInterrupt()

    signal.signal(signal.SIGTERM, _on_term)
    try:
        serve(motors)
    except KeyboardInterrupt:
        pass
    finally:
        pwm.run_flag = False
        for m in motors.values():
            m.brake()
        if STBY is not None:
            STBY.write(0)                           # 退出时驱动芯片进入待机
        print("已停止（PWM=0，刹车，STBY=待机）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
