#!/bin/bash
echo '== headers check =='
ls /usr/include/rockchip/rk_mpi.h 2>/dev/null && echo 'rockchip header OK' || echo 'rockchip header MISSING'
ls /userdata/rtc/ldc_install/include/rtc/rtc.hpp 2>/dev/null && echo 'new rtc header OK' || echo 'new rtc header MISSING'
ls /usr/include/rtc/rtc.hpp 2>/dev/null && echo 'old /usr/include/rtc header exists' || echo 'no /usr/include/rtc'
echo '== mpp lib =='
ls -l /usr/lib/aarch64-linux-gnu/librockchip_mpp.so* 2>/dev/null | head -2
echo '== ldd existing binary vs new .so (check unresolved) =='
LD_LIBRARY_PATH=/userdata/rtc/lib ldd /userdata/rtc/bin/rv1126b_webrtc_push 2>&1 | grep -iE 'not found|datachannel|srtp|rockchip_mpp'
echo '== recompile main.cpp against new headers =='
cd /userdata/rtc
g++ -std=c++17 -O2 main.cpp -o bin/rv1126b_webrtc_push.new \
  -I/userdata/rtc/ldc_install/include \
  -L/userdata/rtc/lib -L/usr/local/lib \
  -ldatachannel -lrockchip_mpp -lssl -lcrypto -pthread 2>&1 | tail -25
echo '== result =='
ls -l bin/rv1126b_webrtc_push.new 2>/dev/null && echo 'COMPILE OK' || echo 'COMPILE FAILED'
