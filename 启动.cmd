@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "NODE=C:\Users\mushr\.workbuddy\binaries\node\versions\22.22.2\node.exe"
if not exist "%NODE%" (
  echo 找不到 node: %NODE%
  pause
  exit /b 1
)
echo 启动法考学习站...
echo 浏览器打开 http://localhost:8080  密码 2026
echo.
"%NODE%" "%~dp0scripts\dev-server.js"
pause
