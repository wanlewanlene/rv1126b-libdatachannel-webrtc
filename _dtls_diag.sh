echo '== openssl version =='
openssl version 2>&1
echo '== libdatachannel .so =='
ls -l /userdata/rtc/lib/libdatachannel.so* 2>&1 | head
echo '== find dtls/srtp source on board =='
find / -name 'dtls_transport.cpp' -o -name 'dtlstransport.cpp' 2>/dev/null | head
find / -path '*rtc*' -name '*.cpp' 2>/dev/null | grep -iE 'dtls|srtp' | head
echo '== grep error string in any source =='
grep -rIl 'SRTP profile is not supported' / 2>/dev/null | head
echo '== ldd libdatachannel (ssl/crypto) =='
ldd /userdata/rtc/lib/libdatachannel.so 2>&1 | grep -iE 'ssl|crypto'
echo '== selected srtp support in openssl (aead) =='
openssl ciphers -v 'ALL' 2>/dev/null | grep -i gcm | head -3 || echo 'no gcm ciphers listed'
echo 'done'
