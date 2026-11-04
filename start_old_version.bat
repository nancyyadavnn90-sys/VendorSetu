@echo off
rem Double-click to run the FIRST version of VendorSetu (git commit 0ce1911, before testing found the defects)
rem at http://127.0.0.1:5001, so the failed test cases (Test Case Document, Section 7) can be shown in the browser.
rem The current, fixed version (start_demo.bat) runs at http://127.0.0.1:5000 - both can run at the same time.
rem Your project files are not changed: the old version is copied to a temporary folder.
cd /d "%~dp0"
set V1=%TEMP%\vendorsetu_v1
if exist "%V1%" rmdir /s /q "%V1%"
mkdir "%V1%"

echo Copying the first version (commit 0ce1911) from git...
git archive --format=tar 0ce1911 app | "%SystemRoot%\System32\tar.exe" -x -C "%V1%"
if not exist "%V1%\app\app.py" goto failed

cd /d "%V1%\app"
echo Resetting its demo data...
python seed_demo.py
if errorlevel 1 goto failed

echo.
echo OLD VERSION (with the defects) running at http://127.0.0.1:5001  (keep this window open)
start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:5001"
python -c "import app; app.app.run(port=5001)"

:failed
echo.
echo Something went wrong - read the message above. Git and Python must be installed.
pause
