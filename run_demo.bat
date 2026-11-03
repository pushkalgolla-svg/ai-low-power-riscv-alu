@echo off
echo ========================================================================
echo   RUNNING 32-BIT RISC-V AI PPA OPTIMIZATION PIPELINE DEMO
echo ========================================================================
cd /d "%~dp0"
call .venv\Scripts\python.exe scripts/optimize_riscv.py --use-existing
pause
