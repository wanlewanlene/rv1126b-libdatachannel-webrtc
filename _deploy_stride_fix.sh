#!/bin/bash
set -e
echo '== backup main.cpp =='
cp -a /userdata/rtc/main.cpp /userdata/rtc/main.cpp.bak2 2>/dev/null || true
echo '== compile (hor_stride fix) =='
cd /userdata/rtc
g++ -std=c++17 -O2 main.cpp -o bin/rv1126b_webrtc_push.new3 \
  -I/userdata/rtc/ldc_install/include \
  -L/userdata/rtc/lib -L/usr/local/lib \
  -ldatachannel -lrockchip_mpp -lssl -lcrypto -pthread 2>&1 | tail -10
ls -l bin/rv1126b_webrtc_push.new3 && echo COMPILE_OK
echo '== stop old =='
pkill -9 -f rv1126b_webrtc_push 2>/dev/null || true
pkill -9 -f WebSocket.js 2>/dev/null || true
fuser -k /dev/video52 2>/dev/null || true
sleep 2
mv bin/rv1126b_webrtc_push.new3 bin/rv1126b_webrtc_push
echo '== ensure route =='
echo elf | sudo -S ip route del default via 192.168.0.1 dev eth0 2>/dev/null || true
echo '== start =='
cd /userdata/rtc
setsid bash /userdata/rtc/run.sh > /userdata/rtc/run.log 2>&1 < /dev/null &
disown 2>/dev/null || true
sleep 6
ps aux | grep -E 'rv1126b|WebSocket' | grep -v grep
tail -12 /userdata/rtc/run.log