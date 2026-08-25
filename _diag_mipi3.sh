echo '== whoami =='; whoami
echo '== lightdm.log (sudo) =='; echo elf | sudo -S tail -60 /var/log/lightdm/lightdm.log 2>&1
echo '== Xorg.0.log (sudo) =='; echo elf | sudo -S tail -50 /var/log/Xorg.0.log 2>&1
echo '== linaro user exists? =='; id linaro 2>&1
echo '== accounts-daemon service file =='; echo elf | sudo -S systemctl status accounts-daemon --no-pager 2>&1 | head -6
echo '== ls /usr/share/dbus-1/services org.freedesktop.Accounts =='; ls /usr/share/dbus-1/services/ 2>&1 | grep -i account
echo '== which X / Xorg =='; which Xorg X 2>&1
