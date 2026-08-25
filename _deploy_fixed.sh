#!/bin/bash
set -e
echo '== backup old main.cpp =='
cp -a /userdata/rtc/main.cpp /userdata/rtc/main.cpp.bak 2>/dev/null || true
echo '== compile fixed main.cpp =='
cd /userdata/rtc
g++ -std=c++17 -O2 main.cpp -o bin/rv1126b_webrtc_push.new2 \
  -I/userdata/rtc/ldc_install/include \
  -L/userdata/rtc/lib -L/usr/local/lib \
  -ldatachannel -lrockchip_mpp -lssl -lcrypto -pthread 2>&1 | tail -30
ls -l bin/rv1126b_webrtc_push.new2 && echo 'COMPILE OK'
echo '== stop old procs =='
pkill -9 -f rv1126b_webrtc_push 2>/dev/null || true
pkill -9 -f WebSocket.js 2>/dev/null || true
fuser -k /dev/video52 2>/dev/null || true
sleep 2
echo '== swap binary =='
mv bin/rv1126b_webrtc_push.new2 bin/rv1126b_webrtc_push
echo '== ensure internet route =='
echo elf | sudo -S ip route del default via 192.168.0.1 dev eth0 2>/dev/null || true
echo '== start run.sh =='
cd /userdata/rtc
setsid bash /userdata/rtc/run.sh > /userdata/rtc/run.log 2>&1 < /dev/null &
disown 2>/dev/null || true
sleep 7
echo '== procs =='
ps aux | grep -E 'rv1126b_webrtc_push|WebSocket.js' | grep -v grep
echo '== log tail =='
tail -14 /userdata/rtc/run.log
