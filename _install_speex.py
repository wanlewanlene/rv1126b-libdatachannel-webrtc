import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BOARD_IP = '192.168.137.184'

board = paramiko.SSHClient()
board.set_missing_host_key_policy(paramiko.AutoAddPolicy())
board.connect(BOARD_IP, port=22, username='elf', password='elf', timeout=15)

def brun(cmd, title, timeout=300):
    print(f"\n########## {title} ##########")
    stdin, stdout, stderr = board.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors='replace'); err = stderr.read().decode(errors='replace')
    if out: print(out.rstrip())
    if err: print("[STDERR]", err.rstrip())
    return out

# 安装 libspeexdsp-dev (小包, 需联网但依赖少)
brun("sudo nohup apt-get install -y libspeexdsp-dev > /tmp/apt_speex.log 2>&1 & sleep 5; echo 安装中...", "后台安装 speexdsp-dev", 30)
import time
for i in range(24):
    time.sleep(5)
    _, out, _ = board.exec_command("ls /usr/include/speex/speex_preprocess.h 2>/dev/null && echo DONE || echo WAIT", timeout=15)
    r = out.read().decode(errors='replace').strip()
    if 'DONE' in r:
        print(f"==> 第{i+1}轮: speexdsp-dev 就绪")
        break
else:
    print("[!] 安装超时, 日志尾:")
    _, o, _ = board.exec_command("tail -5 /tmp/apt_speex.log", timeout=15)
    print(o.read().decode(errors='replace'))

board.close()
print("\n===== 完成 =====")
