@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo No .venv found. Run: uv venv --python 3.11
  echo Then run: uv pip install --python .venv\Scripts\python.exe -r requirements.txt
  exit /b 1
)

".venv\Scripts\python.exe" -m scripts.dev_server
