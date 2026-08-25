echo '== journalctl lightdm tail =='; journalctl -u lightdm --no-pager 2>&1 | tail -40
echo '== accounts-daemon status =='; systemctl is-active accounts-daemon 2>&1; systemctl status accounts-daemon --no-pager 2>&1 | head -8
echo '== dbus status =='; systemctl is-active dbus 2>&1
echo '== lightdm conf =='; cat /etc/lightdm/lightdm.conf 2>/dev/null; ls /etc/lightdm/ 2>&1
echo '== Xorg log tail =='; tail -40 /var/log/Xorg.0.log 2>&1
echo '== lightdm log tail =='; tail -40 /var/log/lightdm/lightdm.log 2>&1
echo '== greeter sessions =='; ls /usr/share/xsessions/ 2>&1; cat /var/lib/lightdm/.Xauthority 2>&1 | head -c 50; echo
echo '== who in video/render groups (elf) =='; groups elf 2>&1
