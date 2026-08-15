@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "logs" mkdir logs

for /f "tokens=1-3 delims=/ " %%a in ('date /t') do set TDATE=%%c%%a%%b
for /f "tokens=1-2 delims=:." %%a in ("%time: =0%") do set TTIME=%%a%%b
set STAMP=%TDATE%_%TTIME%

set OUT_LOG=logs\backend_%STAMP%.out
set ERR_LOG=logs\backend_%STAMP%.err

echo [%STAMP%] Starting backend...
echo   stdout: %OUT_LOG%
echo   stderr: %ERR_LOG%

start "DocumentAgent-Backend" cmd /c "python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload >> %OUT_LOG% 2>> %ERR_LOG%"

echo Backend started in background.
pause
