import paramiko, sys, os, wave, struct, math
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BOARD_IP = '192.168.137.184'
LOCAL_WAV = r'c:\Users\zyp\Desktop\3\rv1106\_mic_test.wav'

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

# 1) 推流日志: 音频线程状态
brun("grep -aE 'ALSA|AUDIO|denoise|opus|audio init' /tmp/rtc_run.log | head -8", "推流日志音频状态", 20)

# 2) 全部 ACodec mixer 状态 (含 ADC 开关)
brun("amixer -c 0 sget 'ACodec_LP ADC' 2>&1 | tail -3; amixer -c 0 sget 'ACodec_LP PGA Gain' 2>&1 | grep 'Mono:' | tail -1; amixer -c 0 sget 'ACodec_LP Digital Gain' 2>&1 | grep 'Mono:' | tail -1; amixer -c 0 sget 'ACodec_LP HPF' 2>&1 | grep 'Mono:' | tail -1", "mixer 状态", 20)

# 3) 板卡直接采集 3 秒 (绕过推流程序, 验证采集通路)
brun("sudo arecord -D default -f S16_LE -r 48000 -c 2 -d 3 /tmp/mic_test.wav 2>&1 | tail -2; ls -l /tmp/mic_test.wav", "板卡直采 3 秒", 30)

# 4) 下载 wav 回本地分析电平
try:
    sftp = board.open_sftp()
    sftp.get('/tmp/mic_test.wav', LOCAL_WAV)
    sftp.close()
    wf = wave.open(LOCAL_WAV, 'rb')
    n = wf.getnframes(); ch = wf.getnchannels(); sw = wf.getsampwidth()
    data = wf.readframes(min(n, 48000*3))
    wf.close()
    samples = struct.unpack(f'<{len(data)//2}h', data)
    peak = max(abs(s) for s in samples)
    rms = math.sqrt(sum(s*s for s in samples)/len(samples))
    print(f"########## 直采分析 (ch={ch}, {len(samples)//ch} 帧) ##########")
    print(f"  峰值(peak)={peak} / 32767, RMS 电平={20*math.log10(rms/32767+1e-9):.1f} dBFS")
    print("  => 采集通路" + ("有声音" if rms > 1000 else ("很弱" if rms > 100 else "静音(无信号)")))
except Exception as e:
    print("WAV 分析失败:", e)

board.close()
print("\n===== 完成 =====")
