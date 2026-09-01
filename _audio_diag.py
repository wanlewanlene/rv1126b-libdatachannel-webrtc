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

# 完整 ADC 相关控件 (PGA/数字增益/HPF)
brun("amixer -c 0 scontrols 2>&1 | grep -i 'ACodec_LP' ; echo '== HPF 选项 =='; amixer -c 0 sget 'ACodec_LP HPF' 2>&1 | tail -4; amixer -c 0 sget 'ACodec_LP HPF Cutoff' 2>&1 | tail -4; echo '== 当前增益 =='; amixer -c 0 sget 'ACodec_LP Digital Gain' 2>&1 | grep Mono; amixer -c 0 sget 'ACodec_LP PGA Gain' 2>&1 | grep Mono", "音频控件详情", 20)

board.close()
print("\n===== 完成 =====")
