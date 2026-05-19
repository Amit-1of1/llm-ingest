@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_llm_ingest.ps1" %*
