@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
if exist "%~dp0runtime\python.exe" (
  "%~dp0runtime\python.exe" "%~dp0tax_exam.py" %*
) else (
  python "%~dp0tax_exam.py" %*
)
exit /b %errorlevel%
