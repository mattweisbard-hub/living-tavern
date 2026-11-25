@echo off
cd /d "%~dp0"
python launcher.py --offline
if errorlevel 1 pause
