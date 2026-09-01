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

# 降噪库可用性: speexdsp / rnnoise / webrtc-audio?
brun("dpkg -l 2>/dev/null | grep -iE 'speex|rnnoise|webrtc-audio' | head -6; echo '--- 库文件 ---'; ls /usr/lib/aarch64-linux-gnu/libspeex* /usr/lib/aarch64-linux-gnu/librnnoise* 2>/dev/null; echo '--- 头文件 ---'; ls /usr/include/speex/ /usr/include/rnnoise.h 2>/dev/null; echo '--- apt 候选 ---'; apt-cache policy libspeexdsp-dev rnnoise 2>/dev/null | grep -A2 '^libspeexdsp-dev\\|^rnnoise' | head -12", "降噪库探测", 30)

board.close()
print("\n===== 完成 =====")
