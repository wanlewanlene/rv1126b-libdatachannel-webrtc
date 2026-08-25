#!/bin/bash
# 用本地已打包的 libdatachannel v0.24.2 源码，链接系统 libsrtp2 2.5.0（带 GCM）重建
set -e
LOG=/userdata/rtc/build_ldc.log
exec > "$LOG" 2>&1
echo "=== build2 start $(date) ==="

cd /userdata/rtc || exit 1
mkdir -p build
cd build || exit 1

echo "== extract tarball =="
rm -rf libdatachannel
tar xzf /tmp/libdatachannel_src.tar.gz 2>&1 | tail -3
ls -d libdatachannel/deps/*/ 2>/dev/null

cd libdatachannel || exit 1
echo "== version =="
grep -m1 -iE 'VERSION' CMakeLists.txt | head -2

echo "== cmake configure (USE_SYSTEM_SRTP=ON) =="
cmake -B build -DCMAKE_BUILD_TYPE=Release \
  -DUSE_SYSTEM_SRTP=ON \
  -DNO_EXAMPLES=ON \
  -DNO_TESTS=ON \
  -DCMAKE_INSTALL_PREFIX=/userdata/rtc/ldc_install 2>&1 | tail -25

echo "== build =="
cmake --build build -j4 2>&1 | tail -25

echo "== install =="
cmake --install build 2>&1 | tail -10

echo "== result .so =="
find /userdata/rtc/ldc_install -name 'libdatachannel.so*' -exec ls -l {} \; 2>/dev/null
echo "=== build2 done $(date) ==="
