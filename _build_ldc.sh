#!/bin/bash
# 重建 libdatachannel，链接系统 libsrtp2 2.5.0（带 GCM），修复 SRTP profile 协商失败
set -u
LOG=/userdata/rtc/build_ldc.log
exec > "$LOG" 2>&1
echo "=== build start $(date) ==="

cd /userdata/rtc || exit 1
mkdir -p build
cd build || exit 1

# 1) clone（优先对齐当前 0.24.2）
if [ ! -d libdatachannel/.git ]; then
  rm -rf libdatachannel
  echo "== cloning v0.24.2 =="
  if ! git clone --depth 1 --branch v0.24.2 https://github.com/paullouisageneau/libdatachannel.git; then
    echo "== v0.24.2 tag not found, cloning default branch =="
    git clone --depth 1 https://github.com/paullouisageneau/libdatachannel.git
  fi
fi
cd libdatachannel || exit 1
echo "== version in CMakeLists =="
grep -m1 -iE 'project\(|VERSION' CMakeLists.txt | head -3

echo "== submodules =="
git submodule update --init --recursive --depth 1 2>&1 | tail -5

echo "== cmake configure (USE_SYSTEM_SRTP=ON, NO_DATA_CHANNELS=ON) =="
cmake -B build -DCMAKE_BUILD_TYPE=Release \
  -DUSE_SYSTEM_SRTP=ON \
  -DNO_DATA_CHANNELS=ON \
  -DNO_EXAMPLES=ON \
  -DNO_TESTS=ON \
  -DCMAKE_INSTALL_PREFIX=/userdata/rtc/ldc_install 2>&1 | tail -20

echo "== build =="
cmake --build build -j4 2>&1 | tail -20

echo "== install =="
cmake --install build 2>&1 | tail -10

echo "== result .so =="
find /userdata/rtc/ldc_install -name 'libdatachannel.so*' -exec ls -l {} \; 2>/dev/null
echo "=== build done $(date) ==="
