@echo off
setlocal
echo ========================================================================
echo   RUNNING 32-BIT RISC-V ALU PPA & SWITCHING ACTIVITY PIPELINE DEMO
echo ========================================================================
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" scripts/optimize_riscv.py
pause
