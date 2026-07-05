@echo off
TITLE PIORUN Autonomy Ops
cd /d "%~dp0"
echo [STARTING] PIORUN Autonomy Ops Panel...
python scripts\autonomy_ops.py panel
pause
