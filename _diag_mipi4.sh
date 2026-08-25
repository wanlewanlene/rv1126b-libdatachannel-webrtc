echo '== /home =='; ls -la /home 2>&1; echo '--- /userdata home? ---'; ls -la /userdata 2>&1 | head
echo '== full lightdm.log =='; echo elf | sudo -S cat /var/log/lightdm/lightdm.log 2>&1 | head -80
echo '== ls /var/log/lightdm =='; echo elf | sudo -S ls -la /var/log/lightdm/ 2>&1
echo '== any Xorg log in /var/log/lightdm =='; echo elf | sudo -S ls -la /var/log/lightdm/ 2>&1 | grep -i xorg
echo '== lightdm.conf autologin lines =='; grep -nE "autologin|user-session|greeter-session" /etc/lightdm/lightdm.conf
echo '== users.conf =='; cat /etc/lightdm/users.conf 2>&1
