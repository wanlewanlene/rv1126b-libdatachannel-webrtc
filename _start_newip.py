import paramiko, time

HOST = "192.168.137.184"   # 新 IP (板卡连 Windows 热点)
USER = "elf"
PWD = "elf"

def run(cli, cmd, timeout=40):
    stdin, stdout, stderr = cli.exec_command(cmd, timeout=timeout)
    return stdout.read().decode(errors="replace"), stderr.read().decode(errors="replace")

cli = paramiko.SSHClient()
cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
cli.connect(HOST, username=USER, password=PWD, timeout=10)
cli.get_transport().set_keepalive(30)
print("### CONNECTED", HOST)

# 1. 检查外网路由 (run.sh 需要删除 eth0 坏路由; 这里 eth0 已 DOWN, 检查默认路由)
out, _ = run(cli, "echo '== route =='; ip route | grep default; echo '== resolv =='; cat /etc/resolv.conf 2>/dev/null | head -3")
print(out.rstrip())

# 2. 上传 HTML (浏览器端更新默认 IP)
sftp = cli.open_sftp()
sftp.put(r"c:/Users/zyp/Desktop/3/rv1106/Browser_client.html", "/userdata/rtc/server/Browser_client.html")
sftp.close()
print("uploaded Browser_client.html")

# 3. 确认代码/二进制是否最新 (含 setBitrate/监测面板)
out, _ = run(cli, "grep -c 'setBitrate' /userdata/rtc/main.cpp; ls -l /userdata/rtc/bin/rv1126b_webrtc_push")
print("setBitrate refs:", out.rstrip())

# 4. 启动推流
cli.exec_command("pkill -9 -f '[r]v1126b_webrtc_push' 2>/dev/null; pkill -9 -f '[W]ebSocket.js' 2>/dev/null; fuser -k /dev/video52 2>/dev/null; sleep 2")
time.sleep(3)
cli.exec_command("cd /userdata/rtc && nohup bash run.sh > run.log 2>&1 </dev/null &")
print("restarted, waiting 15s ...")
time.sleep(15)

# 5. 验证
checks = [
    "echo '== 进程 =='; pgrep -af '[r]v1126b_webrtc_push' || echo 'no push'; pgrep -af '[W]ebSocket.js' || echo 'no node'",
    "echo '== 端口/HTTP =='; ss -ltnp 2>/dev/null | grep -E ':3000|:8080' | awk '{print $4}'; curl -s -o /dev/null -w 'HTTP %{http_code}\\n' http://127.0.0.1:3000/",
    "echo '== 推流参数 =='; grep -aE 'MPP_ENC_SET_RC_CFG|encoder initialized|ALSA|audio capture' /userdata/rtc/run.log | tail -4",
    "echo '== 外网/STUN =='; grep -aE 'srflx' /userdata/rtc/run.log | tail -2",
]
for c in checks:
    out, err = run(cli, c)
    print(out.rstrip())
    if err.strip(): print("[stderr]", err.rstrip())

cli.close()
