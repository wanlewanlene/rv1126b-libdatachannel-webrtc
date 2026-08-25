cd /userdata/rtc
echo '== gcc version =='; gcc --version | head -1
echo '== start compile (output .new) =='
g++ -std=c++17 -O2 main.cpp -o /userdata/rtc/bin/rv1126b_webrtc_push.new \
  -L/userdata/rtc/lib -L/usr/local/lib \
  -ldatachannel -lrockchip_mpp -lssl -lcrypto -pthread 2>&1 | tail -40
echo "compile exit: $?"
echo '== binary? =='; ls -l /userdata/rtc/bin/rv1126b_webrtc_push.new 2>&1
echo '== ldd missing? =='; LD_LIBRARY_PATH=/userdata/rtc/lib ldd /userdata/rtc/bin/rv1126b_webrtc_push.new 2>&1 | grep -i "not found" || echo "NO missing libs"
