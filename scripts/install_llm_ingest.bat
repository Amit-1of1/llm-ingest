@echo off
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_llm_ingest.ps1" %*
if errorlevel 1 (
    echo.
    echo Installer failed. Review the error above.
    pause
    exit /b 1
)

echo.
echo Installer finished.
pause
