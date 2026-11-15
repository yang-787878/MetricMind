@echo off
REM MetricMind run diagnosis (Windows). Equivalent to:
REM   powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_diag.ps1"
REM Use this wrapper when script execution is restricted (unsigned .ps1).
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_diag.ps1" %*
endlocal
