@echo off
REM MetricMind local launcher (Windows). Equivalent to:
REM   powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev.ps1"
REM This wrapper still works when script execution is restricted.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev.ps1" %*
endlocal
