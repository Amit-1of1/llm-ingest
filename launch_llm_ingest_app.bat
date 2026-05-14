@echo off
setlocal
cd /d "%~dp0"

where pyw >nul 2>nul
if %errorlevel%==0 (
    pyw -3 "%~dp0llm_ingest_app.pyw"
    goto :eof
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
    pythonw "%~dp0llm_ingest_app.pyw"
    goto :eof
)

where python >nul 2>nul
if %errorlevel%==0 (
    python "%~dp0llm_ingest_app.pyw"
    goto :eof
)

echo Python was not found on PATH.
pause
