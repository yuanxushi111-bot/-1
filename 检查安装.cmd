@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call tools.cmd doctor
echo.
echo 请在 DeepSeek Harness 中选择本文件夹为工作区，然后输入 /tax-exam-coach
echo 模型连接请在 Harness 中配置；本包不会替您保存或分发 API Key。
pause
