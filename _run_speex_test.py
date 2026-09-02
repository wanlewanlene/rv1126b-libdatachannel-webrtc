import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BOARD_IP = '192.168.137.184'

board = paramiko.SSHClient()
board.set_missing_host_key_policy(paramiko.AutoAddPolicy())
board.connect(BOARD_IP, port=22, username='elf', password='elf', timeout=15)

def brun(cmd, title, timeout=120):
    print(f"\n########## {title} ##########")
    stdin, stdout, stderr = board.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors='replace'); err = stderr.read().decode(errors='replace')
    if out: print(out.rstrip())
    if err: print("[STDERR]", err.rstrip())
    return out

sftp = board.open_sftp()
sftp.put(r'c:\Users\zyp\Desktop\3\rv1106\_speex_test.c', '/tmp/speex_test.c')
sftp.close()
out = brun("g++ -O2 /tmp/speex_test.c -o /tmp/speex_test -lspeexdsp -lm 2>&1; echo EXIT=$?", "编译测试", 60)
if 'EXIT=0' not in out:
    board.close(); sys.exit(1)

brun("/tmp/speex_test 2>&1", "Speex 配置矩阵", 30)

board.close()
print("\n===== 完成 =====")
