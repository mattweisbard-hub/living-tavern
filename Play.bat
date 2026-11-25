@echo off
cd /d "%~dp0"
set MODE=local
set MODEL=qwen2.5:1.5b
if exist model.txt set /p MODEL=<model.txt
set LLM_URL=http://127.0.0.1:11434/v1
set MAX_DAILY_CALLS=10000
ollama list || (echo Start Ollama first. & pause & exit /b 1)
echo Open http://127.0.0.1:8000
.venv\Scripts\python.exe app.py
pause
