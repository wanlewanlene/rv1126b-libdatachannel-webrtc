#!/bin/bash
echo '== backup & swap binary =='
cp -a /userdata/rtc/bin/rv1126b_webrtc_push /userdata/rtc/bin/rv1126b_webrtc_push.bak2 2>/dev/null
mv /userdata/rtc/bin/rv1126b_webrtc_push.new /userdata/rtc/bin/rv1126b_webrtc_push
chmod +x /userdata/rtc/bin/rv1126b_webrtc_push
ls -l /userdata/rtc/bin/rv1126b_webrtc_push*

echo '== stop old =='
pkill -9 -f rv1126b_webrtc_push 2>/dev/null
pkill -9 -f WebSocket.js 2>/dev/null
fuser -k /dev/video52 2>/dev/null
sleep 2

echo '== ensure route =='
echo elf | sudo -S ip route del default via 192.168.0.1 dev eth0 2>/dev/null || true

echo '== start =='
cd /userdata/rtc
setsid bash /userdata/rtc/run.sh > /userdata/rtc/run.log 2>&1 < /dev/null &
disown 2>/dev/null || true
sleep 6

echo '== procs =='
ps aux | grep -E 'rv1126b_webrtc_push|WebSocket.js' | grep -v grep
echo '== log tail =='
tail -16 /userdata/rtc/run.log
