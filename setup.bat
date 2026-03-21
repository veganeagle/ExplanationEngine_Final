@echo off
echo Installing Dependencies via Pip

python -m venv .venv
pip install -r application/engine/requirements.txt

echo.
echo Setup complete.
echo.
echo REQUIRED:
echo 1) Install Ollama
echo 2) Run: ollama pull llama3.2:3b
echo 3) Ensure Ollama is running
echo.
echo then execute run.bat
pause