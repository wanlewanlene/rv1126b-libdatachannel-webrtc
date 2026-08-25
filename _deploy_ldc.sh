#!/bin/bash
echo "== new .so ldd (expect libsrtp2.so.1, no 'not found') =="
ldd /userdata/rtc/ldc_install/lib/libdatachannel.so.0.24.2 2>&1 | grep -iE 'srtp|ssl|crypto|not found'
echo "== GCM cipher in system libsrtp2 (confirm present) =="
nm -D /lib/aarch64-linux-gnu/libsrtp2.so.1 2>/dev/null | grep -E 'srtp_aes_gcm_(128|256)$' | head
echo "== backup old .so =="
mkdir -p /userdata/rtc/lib/backup_old
cp -a /userdata/rtc/lib/libdatachannel.so* /userdata/rtc/lib/backup_old/ 2>/dev/null
echo "== replace with new .so =="
cp -f /userdata/rtc/ldc_install/lib/libdatachannel.so.0.24.2 /userdata/rtc/lib/
cp -f /userdata/rtc/ldc_install/lib/libdatachannel.so.0.24 /userdata/rtc/lib/
cp -f /userdata/rtc/ldc_install/lib/libdatachannel.so /userdata/rtc/lib/
echo "== final /userdata/rtc/lib =="
ls -l /userdata/rtc/lib/libdatachannel.so*
echo "done"
