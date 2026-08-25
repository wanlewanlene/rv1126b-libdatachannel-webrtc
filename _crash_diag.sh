echo '== core dump settings =='
ulimit -c
cat /proc/sys/kernel/core_pattern
echo '== core files? =='
ls -la /userdata/rtc/core* /core* /tmp/core* 2>/dev/null | head
echo '== gdb available? =='
which gdb || echo 'no gdb'
echo '== dmesg segfault details (fault addr) =='
sudo dmesg 2>/dev/null | grep -iE 'segfault|rv1126b' | tail -5
echo '== journal crash info =='
sudo journalctl -k --no-pager 2>/dev/null | grep -iE 'segfault|rv1126b' | tail -5
