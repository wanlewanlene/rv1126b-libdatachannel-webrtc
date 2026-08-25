echo '== run.sh content =='; cat /userdata/rtc/run.sh 2>&1
echo '== /userdata/rtc tree (depth2) =='; ls -la /userdata/rtc 2>&1; echo '--- bin ---'; ls -la /userdata/rtc/bin 2>&1; echo '--- lib ---'; ls -la /userdata/rtc/lib 2>&1; echo '--- server ---'; ls -la /userdata/rtc/server 2>&1; echo '--- server/node_modules? ---'; ls /userdata/rtc/server/node_modules 2>&1 | head
echo '== binary exists? =='; file /userdata/rtc/bin/rv1126b_webrtc_push 2>&1
echo '== ldd of binary: missing libs =='; ldd /userdata/rtc/bin/rv1126b_webrtc_push 2>&1 | grep -iE "not found|=>" 
echo '== libdatachannel.so on system =='; ldconfig -p 2>/dev/null | grep -i datachannel; ls -l /usr/lib/aarch64-linux-gnu/libdatachannel.so* 2>&1
echo '== node exists? =='; which node; node --version 2>&1
echo '== coturn? =='; ls -l /userdata/coturn 2>&1 | head; which turnserver 2>&1
