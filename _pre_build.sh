echo '== does main.cpp use DataChannel? =='
grep -niE 'createDataChannel|DataChannel|createDataChannel' /userdata/rtc/main.cpp 2>/dev/null | head
echo '== pkg-config libsrtp2 =='
pkg-config --exists libsrtp2 && pkg-config --modversion libsrtp2 && echo 'pkgconfig OK' || echo 'pkgconfig MISSING'
ls /usr/lib/aarch64-linux-gnu/pkgconfig/libsrtp2.pc 2>/dev/null
echo '== pkg-config openssl =='
pkg-config --exists openssl && pkg-config --modversion openssl
echo '== disk space /userdata =='
df -h /userdata 2>/dev/null | tail -1
echo '== disk space / (root) =='
df -h / 2>/dev/null | tail -1
echo '== nproc =='
nproc
echo '== main.cpp location & size =='
ls -l /userdata/rtc/main.cpp 2>/dev/null
echo 'done'
