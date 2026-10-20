@echo off
title Public HTTPS Live Tunnel for Mobile Barcode Camera
cd /d "%~dp0"
echo ======================================================================
echo  Public HTTPS Tunnel for Mobile Phone Camera Demo
echo ======================================================================
echo.
echo  * Ensure START_SYSTEM.bat is already running in another window.
echo  * This generates an encrypted HTTPS link for mobile browsers.
echo  * Mobile cameras require HTTPS to scan barcodes smoothly.
echo.
echo Connecting tunnel on Port 5000...
echo.
cmd /c npx localtunnel --port 5000
pause
