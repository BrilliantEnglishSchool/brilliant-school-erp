@echo off
title Brilliant English School ERP
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Please install Python 3.11 or newer.
  pause
  exit /b 1
)
python -m pip install -r requirements.txt
start "Brilliant English School ERP Server" /min cmd /c "python app.py"
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:5000/login"
echo.
echo Brilliant English School ERP is running.
echo Login: admin
echo Password: admin123
echo.
pause
