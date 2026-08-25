echo '== full ldd of libdatachannel =='
ldd /userdata/rtc/lib/libdatachannel.so 2>&1 | grep -iE 'srtp|ssl|crypto|gnutls|mbed'
echo '== libsrtp2 on system =='
ls -l /usr/lib/aarch64-linux-gnu/libsrtp* /lib/aarch64-linux-gnu/libsrtp* /userdata/rtc/lib/libsrtp* 2>/dev/null
echo '== libsrtp2 version string =='
strings /usr/lib/aarch64-linux-gnu/libsrtp2.so* 2>/dev/null | grep -iE 'libsrtp|version' | head -5
echo '== GCM symbols in libsrtp2 (aead profile) =='
for f in /usr/lib/aarch64-linux-gnu/libsrtp2.so* /userdata/rtc/lib/libsrtp2.so*; do
  [ -f "$f" ] && echo "--- $f ---" && nm -D "$f" 2>/dev/null | grep -iE 'aead|gcm' | head
done
echo '== libdatachannel source locations (targeted) =='
ls -d /home/elf/libdatachannel /root/libdatachannel /userdata/rtc/libdatachannel /usr/local/src/libdatachannel /opt/libdatachannel 2>/dev/null
echo '== search dtlstransport.cpp in likely dirs =='
find /home /root /userdata /opt /usr/local/src -name 'dtlstransport.cpp' 2>/dev/null | head
find /home /root /userdata /opt /usr/local/src -name 'srtp.c' -path '*srtp*' 2>/dev/null | head
echo '== gcc/g++ version =='
g++ --version 2>/dev/null | head -1
echo 'done'
