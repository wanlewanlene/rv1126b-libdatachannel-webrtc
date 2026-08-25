echo '== bundled libsrtp2 GCM symbols inside libdatachannel.so? =='
nm /userdata/rtc/lib/libdatachannel.so 2>/dev/null | grep -iE 'srtp_aes_gcm|srtp_crypto_policy_set_aes_gcm|srtp_profile_aead' | head
echo '-- if empty above => bundled libsrtp2 lacks GCM (root cause confirmed) --'
echo '== bundled libsrtp2 version string =='
strings /userdata/rtc/lib/libdatachannel.so 2>/dev/null | grep -iE 'libsrtp [0-9]|srtp_get_version' | head
echo '== board tooling: cmake / git / srtp2 headers / openssl headers =='
which cmake git make pkg-config 2>&1
ls -d /usr/include/srtp2 /usr/include/srtp 2>/dev/null
ls /usr/include/srtp2/srtp.h 2>/dev/null && echo 'srtp2 header OK' || echo 'srtp2 header MISSING'
ls /usr/include/openssl/ssl.h 2>/dev/null && echo 'openssl header OK' || echo 'openssl header MISSING'
echo '== system libsrtp2 dev symlink for linker =='
ls -l /usr/lib/aarch64-linux-gnu/libsrtp2.so 2>/dev/null
echo '== internet (github reachable) =='
getent hosts github.com 2>&1 | head -1
echo 'done'
