import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BOARD_IP = '192.168.137.184'

board = paramiko.SSHClient()
board.set_missing_host_key_policy(paramiko.AutoAddPolicy())
board.connect(BOARD_IP, port=22, username='elf', password='elf', timeout=15)

def brun(cmd, title, timeout=180):
    print(f"\n########## {title} ##########")
    stdin, stdout, stderr = board.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors='replace'); err = stderr.read().decode(errors='replace')
    if out: print(out.rstrip())
    if err: print("[STDERR]", err.rstrip())
    return out

# 1) 板卡二进制是否含 meta 相关符号
brun("nm -D /usr/lib/aarch64-linux-gnu/librockchip_mpp.so | grep -iE 'meta_set_frame|packet_get_meta' | head -5", "meta 符号", 20)

# 2) gdb 断 meta 调用 + KEY_OUTPUT_FRAME, 验证板卡 mpi_dec_test 是否走 meta 输出帧模式
gdb_script = (
    "set pagination off\n"
    "set confirm off\n"
    "set breakpoint pending on\n"
    "break mpp_packet_get_meta\n"
    "commands\n"
    "silent\n"
    "printf \"[GDB] packet_get_meta\\n\"\n"
    "continue\n"
    "end\n"
    "break mpp_meta_set_frame\n"
    "commands\n"
    "silent\n"
    "printf \"[GDB] meta_set_frame(KEY_OUTPUT_FRAME)\\n\"\n"
    "continue\n"
    "end\n"
    "run\n"
)
sftp = board.open_sftp()
with sftp.open('/tmp/gdb5.cmd', 'w') as f:
    f.write(gdb_script)
sftp.close()

brun("timeout 90 gdb -batch -x /tmp/gdb5.cmd --args /usr/bin/mpi_dec_test -i /tmp/frame720.jpg -o /tmp/dec720.out -t 8 -w 1280 -h 720 -n 1 2>&1 | grep -E '\\[GDB\\]|test success' | head -15", "验证板卡 meta 输出帧模式", 150)

board.close()
print("\n===== 完成 =====")
