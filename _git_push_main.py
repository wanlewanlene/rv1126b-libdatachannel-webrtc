# -*- coding: utf-8 -*-
import subprocess, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
R = r'c:\Users\zyp\Desktop\3\rv1106'

subprocess.run(['git', '-C', R, 'add', '-A'], capture_output=True)
r = subprocess.run(['git', '-C', R, '-c', 'user.name=elf', '-c', 'user.email=elf@rv1126b.local',
                    'commit', '-q', '-m', '清理临时脚本, 保持 main 分支整洁'],
                   capture_output=True)
print('commit rc=', r.returncode)
log = subprocess.run(['git', '-C', R, 'log', '--pretty=format:%h %s', '-3'], capture_output=True)
print(log.stdout.decode('utf-8'))
