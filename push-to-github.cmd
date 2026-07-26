@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo === 推送法考学习站到 GitHub ===
echo 提示：先在 https://github.com/new 创建空仓库，不要初始化 README
echo.

set /p USERNAME=请输入 GitHub 用户名:
set /p REPO=请输入仓库名（直接回车默认 law-exam-test）:
if "%REPO%"=="" set REPO=law-exam-test

git remote remove origin 2>nul
git remote add origin https://github.com/%USERNAME%/%REPO%.git
git branch -M main

echo.
echo 正在推送到 https://github.com/%USERNAME%/%REPO%.git ...
git push -u origin main

echo.
if %errorlevel%==0 (
  echo 推送成功。下一步：打开 Cloudflare Pages 连 GitHub 部署。
) else (
  echo 推送失败。请检查用户名/仓库名/网络，以及是否已完成 GitHub 登录。
)
pause
