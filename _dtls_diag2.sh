echo '== openssl version =='
openssl version 2>&1
echo '== libdatachannel .so =='
ls -l /userdata/rtc/lib/libdatachannel.so* 2>&1 | head
echo '== ldd ssl/crypto =='
ldd /userdata/rtc/lib/libdatachannel.so 2>&1 | grep -iE 'ssl|crypto'
echo '== libdatachannel src locations =='
ls -d /home/elf/libdatachannel /root/libdatachannel /userdata/rtc/libdatachannel /usr/src/* 2>/dev/null
echo '== headers =='
ls /usr/include/rtc/ 2>/dev/null | head
echo '== version macro =='
grep -rEh 'DATACHANNEL_VERSION|RTC_VERSION' /usr/include/rtc/*.hpp 2>/dev/null | head
echo 'done'
