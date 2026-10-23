@echo off
cd /d "%~dp0"
echo Using venv Python (no Activate needed)...
".venv\Scripts\python.exe" generate_invoice.py --seed 42 --count 3
if errorlevel 1 (
  echo.
  echo If it failed, install deps into venv:
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  exit /b 1
)
echo.
echo Done. Open folder: output\
explorer "output"
pause
