echo '== ldd WITH run.sh LD_LIBRARY_PATH =='
LD_LIBRARY_PATH=/userdata/rtc/lib ldd /userdata/rtc/bin/rv1126b_webrtc_push 2>&1
echo '== any "not found"? =='
LD_LIBRARY_PATH=/userdata/rtc/lib ldd /userdata/rtc/bin/rv1126b_webrtc_push 2>&1 | grep -i "not found" || echo "NONE missing"
echo '== local libdatachannel validity (ELF header) =='
LD_LIBRARY_PATH=/userdata/rtc/lib ldd /userdata/rtc/bin/rv1126b_webrtc_push 2>&1 | grep datachannel
echo '== file type of local .so =='
head -c 4 /userdata/rtc/lib/libdatachannel.so.0.24.2 | xxd 2>/dev/null || head -c 4 /userdata/rtc/lib/libdatachannel.so.0.24.2 | od -c
echo '== readelf? =='
readelf -h /userdata/rtc/lib/libdatachannel.so.0.24.2 2>&1 | head -5
echo '== node can require ws/express? (server deps) =='
cd /userdata/rtc/server && node -e "try{require('ws');require('express');console.log('ws+express OK')}catch(e){console.log('DEP ERR',e.message)}" 2>&1
