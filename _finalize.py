# -*- coding: utf-8 -*-
import paramiko, subprocess, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 1) 上传 run.sh 到板卡
board = paramiko.SSHClient()
board.set_missing_host_key_policy(paramiko.AutoAddPolicy())
board.connect('192.168.137.184', port=22, username='elf', password='elf', timeout=15)
sftp = board.open_sftp()
sftp.put(r'c:\Users\zyp\Desktop\3\rv1106\run.sh', '/userdata/rtc/run.sh')
sftp.close()
_, out, _ = board.exec_command("chmod +x /userdata/rtc/run.sh && md5sum /userdata/rtc/run.sh", timeout=20)
print('板卡 run.sh:', out.read().decode(errors='replace').strip())
board.close()

# 2) git 提交 run.sh 更新 (消息放 UTF-8 脚本文件)
R = r'c:\Users\zyp\Desktop\3\rv1106'
subprocess.run(['git', '-C', R, 'add', '-A'], capture_output=True)
r = subprocess.run(['git', '-C', R, '-c', 'user.name=elf', '-c', 'user.email=elf@rv1126b.local',
                    'commit', '-q', '-m', 'run.sh 音频参数: PGA 85%+Digital 75%+HPF 60Hz 消除杂音'],
                   capture_output=True)
print('commit rc=', r.returncode)
log = subprocess.run(['git', '-C', R, 'log', '--pretty=format:%h %s', '-3'], capture_output=True)
print(log.stdout.decode('utf-8'))
