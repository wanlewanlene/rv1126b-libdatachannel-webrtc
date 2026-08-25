import paramiko, time, sys
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
brun("ls /userdata/coturn/usr/lib/aarch64-linux-gnu/ 2>&1 | grep -E 'hiredis|libevent'", "检查解包库文件", 20)
brun(f"LD_LIBRARY_PATH={LIBDIR} ldd /userdata/coturn/usr/bin/turnserver 2>&1 | grep -iE 'not found|libevent|hiredis'", "带 LD_LIBRARY_PATH 的 ldd", 20)
brun(f"pkill -f turnserver; sleep 1; LD_LIBRARY_PATH={LIBDIR} timeout 5 /userdata/coturn/usr/bin/turnserver -c /etc/turnserver.conf 2>&1 | head -40; echo '--- timeout exit ---'", "前台运行看报错", 30)

board.close()
print("\n===== 完成 =====")
