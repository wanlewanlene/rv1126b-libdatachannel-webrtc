# -*- coding: utf-8 -*-
import subprocess, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
R = r'c:\Users\zyp\Desktop\3\rv1106'

subprocess.run(['git', '-C', R, 'add', '-A'], capture_output=True)
r = subprocess.run(['git', '-C', R, '-c', 'user.name=elf', '-c', 'user.email=elf@rv1126b.local',
                    'commit', '-q', '-m',
                    '修复音频静音: 禁用 Speex AGC(48kHz 库缺陷输出全静音), 仅保留 NS 降噪'],
                   capture_output=True)
print('commit rc=', r.returncode, (r.stderr or b'').decode('utf-8', 'replace') if r.returncode else '')
log = subprocess.run(['git', '-C', R, 'log', '--pretty=format:%h %s', '-4'], capture_output=True)
print(log.stdout.decode('utf-8'))
