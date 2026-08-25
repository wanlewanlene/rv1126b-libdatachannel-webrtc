$ErrorActionPreference = "Continue"
Set-Location "c:/Users/zyp/Desktop/3/rv1106"

# 让所有 github 链接都走 gh-proxy 镜像（含子模块）
git config --global url."https://gh-proxy.com/https://github.com/".insteadOf "https://github.com/"

Write-Output "=== tags (v0.2x) ==="
git ls-remote --tags https://github.com/paullouisageneau/libdatachannel.git 2>&1 | Select-Object -Last 20

Write-Output "=== clone ==="
Remove-Item -Recurse -Force _ldc_src -ErrorAction SilentlyContinue
git clone --recursive --branch v0.24.2 https://github.com/paullouisageneau/libdatachannel.git _ldc_src/libdatachannel 2>&1 | Select-Object -Last 30

Write-Output "=== result ==="
if (Test-Path _ldc_src/libdatachannel/CMakeLists.txt) {
  Write-Output "CLONE OK"
  Get-ChildItem _ldc_src/libdatachannel/deps -Directory | Select-Object Name
} else {
  Write-Output "CLONE FAILED"
}
