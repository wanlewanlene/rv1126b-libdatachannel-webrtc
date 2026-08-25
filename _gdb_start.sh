#!/bin/bash
# 用 gdb 启动推流程序以捕获 segfault 崩溃栈
echo '== stop old =='
pkill -9 -f rv1126b_webrtc_push 2>/dev/null
pkill -9 -f WebSocket.js 2>/dev/null
fuser -k /dev/video52 2>/dev/null
sleep 2
echo '== ensure route =='
echo elf | sudo -S ip route del default via 192.168.0.1 dev eth0 2>/dev/null || true
echo '== start signaling server =='
cd /userdata/rtc/server
setsid node WebSocket.js > /userdata/rtc/ws.log 2>&1 < /dev/null &
sleep 2
ps aux | grep WebSocket.js | grep -v grep
echo '== start push under gdb (background) =='
cd /userdata/rtc/bin
export LD_LIBRARY_PATH=/userdata/rtc/lib:$LD_LIBRARY_PATH
setsid gdb -batch \
  -ex 'set pagination off' \
  -ex 'handle SIGPIPE nostop noprint pass' \
  -ex run \
  -ex 'echo \n===== CRASH BACKTRACE =====\n' \
  -ex 'bt full' \
  -ex 'info threads' \
  -ex 'thread apply all bt' \
  --args ./rv1126b_webrtc_push > /userdata/rtc/gdb_run.log 2>&1 < /dev/null &
sleep 6
echo '== gdb proc =='
pgrep -af 'gdb|rv1126b' | grep -v grep | head -5
echo '== gdb log tail =='
tail -10 /userdata/rtc/gdb_run.log
echo '== ready: waiting for viewer to connect and crash ==='
