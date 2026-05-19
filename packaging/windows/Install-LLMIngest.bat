@echo off
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-LLMIngest.ps1" -DesktopShortcut %*
if errorlevel 1 (
    echo.
    echo Install failed. Review the error above.
    pause
    exit /b 1
)

echo.
echo LLM Ingest installed.
pause
