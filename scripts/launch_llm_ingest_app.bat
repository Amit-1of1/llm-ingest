@echo off
setlocal
set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%"

if exist "%PROJECT_ROOT%\.venv\Scripts\pythonw.exe" (
    "%PROJECT_ROOT%\.venv\Scripts\pythonw.exe" "%PROJECT_ROOT%\llm_ingest_app.pyw"
    goto :eof
)

if exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" (
    "%PROJECT_ROOT%\.venv\Scripts\python.exe" "%PROJECT_ROOT%\llm_ingest_app.pyw"
    goto :eof
)

where pyw >nul 2>nul
if %errorlevel%==0 (
    pyw -3 "%PROJECT_ROOT%\llm_ingest_app.pyw"
    goto :eof
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
    pythonw "%PROJECT_ROOT%\llm_ingest_app.pyw"
    goto :eof
)

where python >nul 2>nul
if %errorlevel%==0 (
    python "%PROJECT_ROOT%\llm_ingest_app.pyw"
    goto :eof
)

echo Python was not found on PATH.
pause
