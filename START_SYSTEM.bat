@echo off
title Digital Examination Attendance System
cd /d "%~dp0"
echo ======================================================================
echo  Starting Digital Examination Attendance and Verification System
echo ======================================================================
echo.
echo  * Laptop Access : http://127.0.0.1:5000
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4 Address"') do (
    echo  * Phone Access  : http:%%a:5000
)
echo.
echo  (Keep this console window OPEN while running your demonstration)
echo ======================================================================
echo.
python run.py
pause
