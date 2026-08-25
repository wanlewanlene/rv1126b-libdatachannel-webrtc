# -*- coding: utf-8 -*-
# 重建 git 版本历史 v2: python UTF-8 修复提交信息乱码
import shutil, subprocess, os, sys

R = r'c:\Users\zyp\Desktop\3\rv1106'
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def git(*args, **kw):
    return subprocess.run(['git', '-C', R] + list(args), capture_output=True, **kw)

def commit(msg, date):
    env = dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    git('add', '-A')
    r = git('-c', 'user.name=elf', '-c', 'user.email=elf@rv1126b.local',
            'commit', '-q', '-m', msg, env=env)
    if r.returncode != 0:
        print('COMMIT FAIL:', r.stderr.decode('utf-8', 'replace'))
        sys.exit(1)

# 0) 备份当前 1M 版页面
shutil.copy(f'{R}/Browser_client.html', os.path.join(os.environ['TEMP'], 'Browser_client_1M.html'))

# 1) 清除现有 main 分支引用与 index (工作区文件不动)
git('update-ref', '-d', 'refs/heads/main')
git('rm', '-r', '--cached', '.')

# v1: 08-26 无音频版
shutil.copy(f'{R}/_board_main.cpp.v4.nv12', f'{R}/_board_main.cpp')
commit('v1: 640x480 YUYV+NV12 软转, 无音频稳定版', '2026-08-26T05:02:00')

# v2: 08-31 21:07 音频版
shutil.copy(f'{R}/_backup_20260831_720p/main.cpp.pre720p', f'{R}/_board_main.cpp')
commit('v2: 640x480+板载MIC音频, 720p升级前最后稳定版', '2026-08-31T21:07:00')

# v3: 08-31 22:45 720p 软解版
shutil.copy(f'{R}/_board_main.cpp.softdec720p', f'{R}/_board_main.cpp')
shutil.copy(f'{R}/_backup_20260831_720p/Browser_client.html.softdec720p', f'{R}/Browser_client.html')
commit('v3: 720p MJPG采集+libjpeg-turbo软解, 4Mbps, 页面BITRATE 4M', '2026-08-31T22:45:00')

# v4: 09-01 回滚当前状态
shutil.copy(f'{R}/_backup_20260831_720p/main.cpp.pre720p', f'{R}/_board_main.cpp')
shutil.copy(os.path.join(os.environ['TEMP'], 'Browser_client_1M.html'), f'{R}/Browser_client.html')
commit('v4: 回滚到 640x480+音频稳定版, 页面码率恢复 1M', '2026-09-01T21:35:00')

# 验证
log = git('log', '--pretty=format:%h %ad %s', '--date=format:%m-%d %H:%M').stdout.decode('utf-8')
print(log)
st = git('status', '-s').stdout.decode('utf-8', 'replace').strip()
print('工作区:', '干净' if not st else st)
import hashlib
h = hashlib.md5(open(f'{R}/_board_main.cpp','rb').read()).hexdigest()
print('_board_main.cpp md5 =', h, '(应为 e31f63... = pre720p)')
