@echo off
echo ===================================================
echo Starting LibertyPlus Local Development Server
echo ===================================================
echo.
echo Make sure you have python installed on your system.
echo Press CTRL+C to stop the server at any time.
echo.
echo URL: http://localhost:8000
echo.
start http://localhost:8000
python -m http.server 8000
pause
