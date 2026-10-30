# -*- coding: utf-8 -*-
"""
RV1126B (ELF 板) WebRTC 推流运维工具
用法:
  python rtc_push_ctl.py                 # 自动探测板卡 IP 并重启推流
  python rtc_push_ctl.py restart         # 重启推流 (含摄像头/信令检查)
  python rtc_push_ctl.py start           # 仅启动 (跳过停止步骤)
  python rtc_push_ctl.py stop            # 停止推流 (信令保留)
  python rtc_push_ctl.py status          # 查看状态 (进程/解码计数/端口)
  python rtc_push_ctl.py 192.168.2.14 restart   # 指定板卡 IP

依赖: pip install paramiko   (已装于 C:\\Espressif\\python_env\\idf5.5_py3.11_env)
板卡: elf/<密码 elf>, 部署目录 /userdata/rtc/
"""
import sys, socket, subprocess, time, re
import paramiko

# ----------------------------------------------------------------------------
# 配置
# ----------------------------------------------------------------------------
BOARD_USER = 'elf'
BOARD_PASS = 'elf'
RTC_DIR    = '/userdata/rtc'
CAM_DEV    = '/dev/video52'
BIN        = f'{RTC_DIR}/bin/rv1126b_webrtc_push'
LOG_PUSH   = '/tmp/rtc_run.log'
LOG_SIG    = '/tmp/sig.log'
# 历史网段 (板卡 DHCP IP 会变, 自动探测时逐个尝试)
PROBE_NETS = ['192.168.137.', '192.168.2.']
PROBE_HOSTS = ['192.168.137.184', '192.168.2.14']   # 最近已知地址优先

def out(s):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print(s, flush=True)

# ----------------------------------------------------------------------------
# 板卡 IP 自动探测: arp -a 记录 + 历史地址, 逐个试 SSH 22 端口
# ----------------------------------------------------------------------------
def probe_boards():
    cands = list(PROBE_HOSTS)
    try:
        arp = subprocess.run(['arp', '-a'], capture_output=True, text=True,
                             timeout=10, encoding='gbk', errors='replace').stdout
        for m in re.finditer(r'(\d+\.\d+\.\d+\.\d+)', arp):
            ip = m.group(1)
            if any(ip.startswith(n) and ip not in cands for n in PROBE_NETS):
                cands.insert(0, ip)   # ARP 新记录优先
    except Exception:
        pass
    for ip in cands:
        try:
            s = socket.create_connection((ip, 22), timeout=2)
            banner = s.recv(64).decode(errors='replace')
            s.close()
            if banner.startswith('SSH'):
                return ip
        except Exception:
            continue
    return None

def connect(ip):
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(ip, port=22, username=BOARD_USER, password=BOARD_PASS, timeout=15)
    return cli

def run(cli, cmd, timeout=120):
    _, stdout, stderr = cli.exec_command(cmd, timeout=timeout)
    o = stdout.read().decode(errors='replace').rstrip()
    e = stderr.read().decode(errors='replace').rstrip()
    return o, e

# ----------------------------------------------------------------------------
# 原子操作
# ----------------------------------------------------------------------------
def stop_push(cli):
    o, _ = run(cli, "sudo pkill -TERM -f '[r]v1126b_webrtc_push'; sleep 3; "
                    "sudo pkill -9 -f '[r]v1126b_webrtc_push' 2>/dev/null; "
                    f"sudo fuser -k {CAM_DEV} 2>/dev/null; sleep 1; "
                    "pgrep -af '[r]v1126b_webrtc_push' | grep -v bash || echo STOPPED")
    out('  推流已停止' if 'STOPPED' in o else f'  [!] 推流残留: {o}')

def wait_camera(cli, max_wait=15):
    for i in range(max_wait):
        o, _ = run(cli, f"ls {CAM_DEV} >/dev/null 2>&1 && echo READY || echo WAIT")
        if 'READY' in o:
            o, _ = run(cli, f"cat /sys/class/video4linux/{CAM_DEV.split('/')[-1]}/name 2>/dev/null")
            out(f'  摄像头就绪: {CAM_DEV} ({o or "?"})' if o else f'  摄像头就绪: {CAM_DEV}')
            return True
        if i == 0:
            out(f'  摄像头未枚举, 等待 (最多 {max_wait}s, 断电重启后 USB 枚举有延迟)...')
        time.sleep(1)
    out('  [!] 摄像头超时未就绪')
    return False

def ensure_signaling(cli):
    o, _ = run(cli, "pgrep -f '[W]ebSocket.js' >/dev/null && echo RUN || echo DOWN")
    if 'RUN' in o:
        out('  信令服务器: 运行中 (保留)')
        return True
    out('  信令服务器未运行, 启动...')
    run(cli, f"cd {RTC_DIR}/server && sudo -b nohup node WebSocket.js > {LOG_SIG} 2>&1 & sleep 3")
    o, _ = run(cli, "pgrep -f '[W]ebSocket.js' >/dev/null && echo RUN || echo DOWN")
    out('  信令服务器: 已启动' if 'RUN' in o else '  [!] 信令启动失败')
    return 'RUN' in o

def start_push(cli):
    o, _ = run(cli, f"cd {RTC_DIR} && sudo -b nohup env "
                    f"LD_LIBRARY_PATH={RTC_DIR}/lib:$LD_LIBRARY_PATH ./bin/rv1126b_webrtc_push "
                    f"> {LOG_PUSH} 2>&1 & sleep 8; "
                    "pgrep -af '[r]v1126b_webrtc_push' | grep -v bash || echo DOWN")
    ok = 'DOWN' not in o
    out('  推流进程: 已启动' if ok else '  [!] 推流启动失败, 日志:')
    if not ok:
        lo, _ = run(cli, f"tail -10 {LOG_PUSH} | tr -cd '[:print:]\\n'")
        out(lo)
    return ok

def verify_stream(cli):
    # 版本判别: 720p 软解版有 [DEC] 解码计数; pre720p 版无, 用初始化日志验证
    o, _ = run(cli, f"grep -ac 'decoded' {LOG_PUSH} 2>/dev/null")
    first = (o.strip().splitlines() or ['0'])[0].strip()
    has_counter = first.isdigit() and int(first) > 0

    if has_counter:
        # 720p 软解版: 解码帧计数持续增长是视频流的黄金指标 (30fps -> 每 5s +150)
        n1 = int(first)
        time.sleep(6)
        o, _ = run(cli, f"grep -ac 'decoded' {LOG_PUSH} 2>/dev/null")
        first2 = (o.strip().splitlines() or ['0'])[0].strip()
        n2 = int(first2) if first2.isdigit() else 0
        o, _ = run(cli, f"grep -a 'decoded' {LOG_PUSH} | tail -1")
        out(f'  解码数据流: {o or "(无计数)"}')
        out('  => 视频流正常 (帧计数增长)' if n2 > n1 else '  => [!] 帧计数未增长, 视频流异常!')
    else:
        # pre720p 版: 用采集/编码初始化日志 + 运行时长验证
        o, _ = run(cli, f"grep -aE 'camera initialized|encoder initialized' {LOG_PUSH} | tail -2")
        out(f'  初始化日志: {o.splitlines() if o else "(无)"}')
        if 'camera initialized' in o and 'encoder initialized' in o:
            out('  => pre720p 版: 采集/编码初始化正常 (此版本无解码计数日志)')
        else:
            out('  => [!] 初始化日志缺失, 请检查推流日志!')
    o, _ = run(cli, "sudo ss -tlnp 2>/dev/null | grep -cE ':3000|:8080'")
    port = (o.strip().splitlines() or ['0'])[0].strip()
    out(f"  信令端口: {'3000/8080 正常监听' if port == '2' else '[!] 端口异常 (' + port + '/2)'}")

def show_status(cli):
    o, _ = run(cli, "pgrep -af '[r]v1126b_webrtc_push' | grep -v bash || echo '(推流未运行)'")
    out(f'推流进程: {o.splitlines()[0] if "(推流未运行)" not in o else "(推流未运行)"}')
    o, _ = run(cli, "pgrep -af '[W]ebSocket.js' | grep -v bash || echo '(信令未运行)'")
    out(f'信令进程: {o.splitlines()[0] if "(信令未运行)" not in o else "(信令未运行)"}')
    o, _ = run(cli, f"grep -a 'decoded' {LOG_PUSH} 2>/dev/null | tail -1")
    out(f'最近解码: {o or "(无记录)"}')
    o, _ = run(cli, "grep -aE 'CONNECTED' " + LOG_PUSH + " 2>/dev/null | tail -1")
    out(f'连接状态: {o or "(无 viewer 记录)"}')
    o, _ = run(cli, "sudo ss -tlnp 2>/dev/null | grep -E ':3000|:8080'")
    out(f'端口: {o or "(未监听)"}')
    out(f'浏览器观看: http://{cli.get_transport().getpeername()[0]}:3000/')

# ----------------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------------
def main():
    args = [a for a in sys.argv[1:]]
    cmd = 'restart'
    if args and args[-1] in ('restart', 'start', 'stop', 'status'):
        cmd = args[-1]
        args = args[:-1]
    ip = args[0] if args else probe_boards()
    if not ip:
        out('[!] 未探测到板卡 (试过 ' + ', '.join(PROBE_HOSTS) + ')。'
            '请用 ipconfig/arp -a 确认网段后手动指定: python rtc_push_ctl.py <板卡IP> ' + cmd)
        return 1
    out(f'== 板卡: elf@{ip}  操作: {cmd} ==')
    cli = connect(ip)
    try:
        if cmd == 'stop':
            stop_push(cli)
        elif cmd == 'status':
            show_status(cli)
        elif cmd in ('restart', 'start'):
            if cmd == 'restart':
                out('1. 停止旧推流')
                stop_push(cli)
            out('2. 摄像头检查')
            if not wait_camera(cli):
                return 1
            out('3. 信令检查')
            if not ensure_signaling(cli):
                return 1
            out('4. 启动推流')
            if not start_push(cli):
                return 1
            out('5. 验证视频数据流')
            verify_stream(cli)
            out(f'\n==> 完成。浏览器观看: http://{ip}:3000/ (硬刷新 Ctrl+Shift+R)')
    finally:
        cli.close()
    return 0

if __name__ == '__main__':
    sys.exit(main())
