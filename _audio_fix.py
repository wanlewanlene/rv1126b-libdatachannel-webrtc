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

# 1) 调低增益 + 开 HPF
brun("amixer -c 0 sset 'ACodec_LP PGA Gain' 85% 2>&1 | tail -2; "
     "amixer -c 0 sset 'ACodec_LP Digital Gain' 95 2>&1 | tail -2; "
     "amixer -c 0 sset 'ACodec_LP HPF' on 2>&1 | tail -2; "
     "amixer -c 0 sset 'ACodec_LP HPF Cutoff' '60Hz' 2>&1 | tail -2",
     "调低增益并开 HPF", 20)

# 2) 确认最终值
brun("echo '== 调整后 =='; amixer -c 0 sget 'ACodec_LP Digital Gain' 2>&1 | grep 'Mono:' | tail -1; "
     "amixer -c 0 sget 'ACodec_LP PGA Gain' 2>&1 | grep 'Mono:' | tail -1; "
     "amixer -c 0 sget 'ACodec_LP HPF' 2>&1 | grep 'Mono:' | tail -1", "确认", 20)

board.close()
print("\n===== 完成 =====")
