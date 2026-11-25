@echo off
cd /d "%~dp0"
git pull --ff-only || goto fail
if not exist .venv\Scripts\python.exe python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt || goto fail
echo Update successful. Run Play.bat.
pause
exit /b 0
:fail
echo Update failed. See error above.
pause
exit /b 1
