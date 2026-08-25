import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BOARD_IP = '192.168.137.184'
LOCAL_HTML = r'c:\Users\zyp\Desktop\3\rv1106\Browser_client.html'

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

# 1) 停止当前推流
brun("sudo pkill -TERM -f '[r]v1126b_webrtc_push'; sleep 3; sudo pkill -9 -f '[r]v1126b_webrtc_push' 2>/dev/null; sudo fuser -k /dev/video52 2>/dev/null; sleep 1; pgrep -af '[r]v1126b_webrtc_push' | grep -v bash || echo '(已停止)'", "1. 停止推流", 30)

# 2) 备份当前 720p 软解版 (以后可切回)
brun("cd /userdata/rtc && cp -f main.cpp main.cpp.softdec720p && cp -f bin/rv1126b_webrtc_push bin/rv1126b_webrtc_push.softdec720p && cp -f server/Browser_client.html server/Browser_client.html.softdec720p && echo 当前版已备份为 *.softdec720p", "2. 备份当前 720p 软解版", 20)

# 3) 恢复 pre720p 版 (640x480+音频)
brun("cd /userdata/rtc && cp -f main.cpp.pre720p main.cpp && cp -f bin/rv1126b_webrtc_push.pre720p bin/rv1126b_webrtc_push && chmod +x bin/rv1126b_webrtc_push && md5sum main.cpp main.cpp.pre720p", "3. 恢复 pre720p 版", 20)

# 4) 上传 BITRATE 恢复后的页面
sftp = board.open_sftp()
sftp.put(LOCAL_HTML, '/userdata/rtc/server/Browser_client.html')
sftp.close()
brun("ls -l /userdata/rtc/server/Browser_client.html && echo 页面已更新", "4. 更新浏览器页面", 20)

# 5) 启动 pre720p 版推流
brun("ls -l /dev/video52 2>&1; cd /userdata/rtc && sudo -b nohup env LD_LIBRARY_PATH=/userdata/rtc/lib:$LD_LIBRARY_PATH ./bin/rv1126b_webrtc_push > /tmp/rtc_run.log 2>&1 & sleep 10; pgrep -af '[r]v1126b_webrtc_push' | grep -v bash || echo '(启动失败!)'", "5. 启动推流", 50)
brun("grep -aE 'V4L2|MPP|SIG|streaming' /tmp/rtc_run.log | head -15", "6. 验证启动日志", 30)
brun("echo '== 端口 =='; sudo ss -tlnp | grep -E ':3000|:8080' | head -2", "7. 端口确认", 20)

board.close()
print("\n===== 完成 =====")
