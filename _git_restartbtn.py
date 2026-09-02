# -*- coding: utf-8 -*-
import subprocess, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
R = r'c:\Users\zyp\Desktop\3\rv1106'

subprocess.run(['git', '-C', R, 'add', '-A'], capture_output=True)
r = subprocess.run(['git', '-C', R, '-c', 'user.name=elf', '-c', 'user.email=elf@rv1126b.local',
                    'commit', '-q', '-m', '浏览器端新增"重启推流"按钮: 彻底重置并重建 WebRTC 连接, 刷新页面后可手动恢复推流'],
                   capture_output=True)
print('commit rc=', r.returncode, (r.stderr or b'').decode('utf-8', 'replace') if r.returncode else '')
s = subprocess.run(['git', '-C', R, 'status', '-s'], capture_output=True)
print('工作区:', s.stdout.decode('utf-8').strip() or '干净')
