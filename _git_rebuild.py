# -*- coding: utf-8 -*-
import subprocess, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
R = r'c:\Users\zyp\Desktop\3\rv1106'

subprocess.run(['git', '-C', R, 'add', '-A'], capture_output=True)
r = subprocess.run(['git', '-C', R, '-c', 'user.name=elf', '-c', 'user.email=elf@rv1126b.local',
                    'commit', '-q', '-m',
                    '修复刷新页面后无法重连: 板卡端 viewer 重连时重建全新 PeerConnection(新ICE凭据), 替代重发缓存SDP(stable状态下answer被拒); offer 改单次发送'],
                   capture_output=True)
print('commit rc=', r.returncode, (r.stderr or b'').decode('utf-8', 'replace') if r.returncode else '')
s = subprocess.run(['git', '-C', R, 'status', '-s'], capture_output=True)
print('工作区:', s.stdout.decode('utf-8').strip() or '干净')
