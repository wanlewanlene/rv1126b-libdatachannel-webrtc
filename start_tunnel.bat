@echo off
REM ============================================================
REM  启动 Cloudflare 公网隧道（无需账号）
REM  将板卡 3000 端口（网页 + 同源信令 /ws + 电机接口 /motor）映射到公网 HTTPS 域名，
REM  使外网可直接打开双端音视频页面并控制电机。
REM
REM  用法：
REM    start_tunnel.bat                     （默认板卡 192.168.137.184）
REM    start_tunnel.bat 192.168.2.14
REM
REM  运行后终端会输出形如 https://xxxx.trycloudflare.com 的公网地址，
REM  用浏览器打开 https://<该域名>/Browser_client.html 或 /Dual_webrtc.html 即可。
REM  注意：免费隧道地址每次启动会变化，且本窗口需保持运行。
REM ============================================================
set BOARD_IP=%1
if "%BOARD_IP%"=="" set BOARD_IP=192.168.137.184

where cloudflared.exe >nul 2>nul
if errorlevel 1 (
    echo 未找到 cloudflared.exe，请先下载放到本目录：
    echo   https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe
    pause
    exit /b 1
)

echo 正在建立隧道：http://%BOARD_IP%:3000 -^> 公网 HTTPS ...
cloudflared.exe tunnel --url http://%BOARD_IP%:3000 --no-autoupdate --protocol http2
