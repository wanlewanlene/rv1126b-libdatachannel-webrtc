import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BOARD_IP = '192.168.137.184'

board = paramiko.SSHClient()
board.set_missing_host_key_policy(paramiko.AutoAddPolicy())
board.connect(BOARD_IP, port=22, username='elf', password='elf', timeout=15)

def brun(cmd, title, timeout=60):
    print(f"\n########## {title} ##########")
    stdin, stdout, stderr = board.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors='replace'); err = stderr.read().decode(errors='replace')
    if out: print(out.rstrip())
    if err: print("[STDERR]", err.rstrip())
    return out

# 1) TURN: 未运行则启动
o = brun("pgrep -f '[t]urnserver' >/dev/null && echo RUN || echo DOWN", "TURN 检查", 20)
if 'RUN' not in o:
    brun("sudo nohup turnserver -c /etc/turnserver.conf > /tmp/turn.log 2>&1 & sleep 2; pgrep -af '[t]urnserver' | head -1 || echo '(启动失败)'", "启动 TURN", 30)
else:
    print("  TURN 已在运行")

# 2) 音频增益应用 (run.sh 固化值)
brun("amixer -c 0 sset 'ACodec_LP Digital Gain' 95 >/dev/null 2>&1; amixer -c 0 sset 'ACodec_LP PGA Gain' 85% >/dev/null 2>&1; amixer -c 0 sset 'ACodec_LP HPF' on >/dev/null 2>&1; echo '== 增益确认 =='; amixer -c 0 sget 'ACodec_LP Digital Gain' 2>&1 | grep 'Mono:' | tail -1; amixer -c 0 sget 'ACodec_LP PGA Gain' 2>&1 | grep 'Mono:' | tail -1; amixer -c 0 sget 'ACodec_LP HPF' 2>&1 | grep 'Mono:' | tail -1", "应用音频增益", 20)

# 3) 最终状态
brun("echo '== 全部服务 =='; pgrep -af '[r]v1126b_webrtc_push|[W]ebSocket.js|[t]urnserver' | grep -v bash; echo '== 端口 =='; sudo ss -tlnp | grep -cE ':3000|:8080|:3478' | xargs echo '监听端口数:'", "最终状态", 20)

board.close()
print("\n===== 完成 =====")
