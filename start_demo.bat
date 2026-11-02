@echo off
rem Double-click this file to reset the demo data, start VendorSetu and open it in the browser.
rem Close this window (or press Ctrl+C) to stop the app.
cd /d "%~dp0app"

echo Resetting demo data...
python seed_demo.py
if errorlevel 1 goto failed

echo.
echo Starting VendorSetu at http://127.0.0.1:5000  (keep this window open during the demo)
start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:5000"
python app.py

:failed
echo.
echo Something went wrong - read the message above. If it says "No module named flask", run:
echo     pip install flask
pause
