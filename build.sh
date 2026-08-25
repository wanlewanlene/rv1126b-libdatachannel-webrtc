#!/bin/bash
# ============================================================================
# RV1126B (ELF 板) WebRTC 推流程序编译脚本
# 运行环境: 板端 rootfs (chroot 内) 或板卡本机, 已安装 libdatachannel + librockchip_mpp
#
# 用法:
#   bash build.sh          # 本机/板端编译
#   CXX=... bash build.sh  # 指定编译器
# ============================================================================
set -e

CXX="${CXX:-g++}"
TARGET="rv1126b_webrtc_push"
SRC="main.cpp"

CXXFLAGS="-std=c++17 -O2 -Wall"
LIBS="-ldatachannel -lrockchip_mpp -lssl -lcrypto -pthread"

echo "==> 编译器: $($CXX --version | head -1)"
echo "==> 编译 $SRC -> $TARGET"
$CXX $CXXFLAGS "$SRC" -o "$TARGET" $LIBS

echo "==> 编译完成: $TARGET"
if command -v file >/dev/null 2>&1; then
    file "$TARGET"
fi
