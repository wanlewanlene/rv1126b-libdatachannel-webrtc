echo '== exact GCM cipher/profile symbols in bundled libsrtp2 =='
nm /userdata/rtc/lib/libdatachannel.so 2>/dev/null | grep -E 'srtp_aes_gcm_(128|256)$' 
nm /userdata/rtc/lib/libdatachannel.so 2>/dev/null | grep -E 'srtp_crypto_policy_set_aes_gcm_128_16_auth'
nm /userdata/rtc/lib/libdatachannel.so 2>/dev/null | grep -E 'srtp_profile_aead_aes_256_gcm'
echo '== bundled libsrtp2 version string =='
strings /userdata/rtc/lib/libdatachannel.so 2>/dev/null | grep -oE 'libsrtp2? [0-9.]+' | head
echo '== datachannel cmake build info string =='
strings /userdata/rtc/lib/libdatachannel.so 2>/dev/null | grep -iE 'system.srtp|use.system|srtp.*system' | head
echo 'done'
