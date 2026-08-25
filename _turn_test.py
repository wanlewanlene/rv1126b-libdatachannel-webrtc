import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

board = paramiko.SSHClient()
board.set_missing_host_key_policy(paramiko.AutoAddPolicy())
board.connect('192.168.2.14', port=22, username='elf', password='elf', timeout=15)

def brun(cmd, title, timeout=120):
    print(f"\n########## [BOARD] {title} ##########")
    stdin, stdout, stderr = board.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors='replace'); err = stderr.read().decode(errors='replace')
    if out: print(out)
    if err: print("[STDERR]", err)

LIBDIR="/userdata/coturn/usr/lib/aarch64-linux-gnu:/userdata/coturn/usr/lib"
brun(f"LD_LIBRARY_PATH={LIBDIR} /userdata/coturn/usr/bin/turnutils_uclient -u webrtc -w webrtc123 -p 3478 -y 192.168.2.14 2>&1 | tail -25", "TURN 中继自测 (分配 relay 地址)", 40)

board.close()
print("\n===== 完成 =====")
