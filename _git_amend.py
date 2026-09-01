# -*- coding: utf-8 -*-
# 修正上一条 commit 消息的乱码 (消息放 UTF-8 脚本文件, subprocess 传参)
import subprocess, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
R = r'c:\Users\zyp\Desktop\3\rv1106'

r = subprocess.run(['git', '-C', R, '-c', 'user.name=elf', '-c', 'user.email=elf@rv1126b.local',
                    'commit', '--amend', '-q', '-m',
                    'run.sh 固化 TURN 服务器与音频增益; 清理临时脚本'],
                   capture_output=True)
print('amend rc=', r.returncode, (r.stderr or b'').decode('utf-8', 'replace'))
log = subprocess.run(['git', '-C', R, 'log', '--pretty=format:%h %s'], capture_output=True)
print(log.stdout.decode('utf-8'))
