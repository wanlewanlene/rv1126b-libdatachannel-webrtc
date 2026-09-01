# -*- coding: utf-8 -*-
import subprocess, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
R = r'c:\Users\zyp\Desktop\3\rv1106'

subprocess.run(['git', '-C', R, 'add', '-A'], capture_output=True)
r = subprocess.run(['git', '-C', R, '-c', 'user.name=elf', '-c', 'user.email=elf@rv1126b.local',
                    'commit', '-q', '-m',
                    '音频集成 SpeexDSP 实时降噪(NS18dB+AGC), 消除板载MIC底噪'],
                   capture_output=True)
print('commit rc=', r.returncode, (r.stderr or b'').decode('utf-8', 'replace') if r.returncode else '')
log = subprocess.run(['git', '-C', R, 'log', '--pretty=format:%h %s', '-3'], capture_output=True)
print(log.stdout.decode('utf-8'))
