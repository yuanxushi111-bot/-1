@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo 此操作会联网准备独立 MinerU 依赖，不上传您的文档。
echo 如需本地OCR，还需要根据设备准备解析模型，详见 docs\mineru.md。
if exist "runtime\python.exe" (
  "runtime\python.exe" "scripts\prepare_mineru.py" --install
) else (
  python "scripts\prepare_mineru.py" --install
)
pause
