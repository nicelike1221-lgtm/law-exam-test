@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "NODE=C:\Users\mushr\.workbuddy\binaries\node\versions\22.22.2\node.exe"
if not exist "%NODE%" (
  echo 找不到 node: %NODE%
  echo 请先安装 Node.js，或把 node 加入 PATH
  pause
  exit /b 1
)
"%NODE%" "%~dp0scripts\check-feishu.js"
echo.
pause
