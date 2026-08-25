echo '== exact GCM cipher/profile symbols in bundled libsrtp2 =='
nm /userdata/rtc/lib/libdatachannel.so 2>/dev/null | grep -E 'srtp_aes_gcm_(128|256)$|srtp_crypto_policy_set_aes_gcm_128_16_auth|srtp_profile_aead_aes_256_gcm' | head
echo '== bundled libsrtp2 version string (broad) =='
strings /userdata/rtc/lib/libdatachannel.so 2>/dev/null | grep -oE 'libsrtp2? [0-9.]+' | head
strings /userdata/rtc/lib/libdatachannel.so 2>/dev/null | grep -E 'GCM.*(not )?supported|aes_gcm' | head
echo '== libdatachannel available tags (github) =='
git ls-remote --tags https://github.com/paullouisageneau/libdatachannel.git 2>/dev/null | grep -oE 'refs/tags/v[0-9.]+$' | sed 's#refs/tags/##' | sort -V | tail -8
echo 'done'
