import paramiko
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

board = paramiko.SSHClient()
board.set_missing_host_key_policy(paramiko.AutoAddPolicy())
board.connect('192.168.137.184', port=22, username='elf', password='elf', timeout=15)

def brun(cmd, title, timeout=120):
    print(f"\n########## [BOARD] {title} ##########")
    stdin, stdout, stderr = board.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors='replace'); err = stderr.read().decode(errors='replace')
    if out: print(out)
    if err: print("[STDERR]", err)

filter_re = "grep -vE 'mpp_|dumping|buffer 0x|ref_count|mpp_mem|mpp_group|h264e|mpp_cfg|mpp_enc|h264'"

# 显示最近 60 行日志 (过滤掉 MPP 噪声)
brun(f"tail -n 60 /userdata/rtc/run.log 2>&1 | {filter_re}", "最新日志(过滤MPP噪声)", timeout=30)
# 是否有 viewer 握手
brun("grep -cE 'viewer|answer|ICE' /userdata/rtc/run.log 2>&1", "viewer/answer 相关行数", timeout=30)

board.close()
print("\n===== 完成 =====")
