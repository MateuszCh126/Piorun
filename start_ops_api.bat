@echo off
TITLE PIORUN Ops API
cd /d "%~dp0"
echo [STARTING] PIORUN Ops API...
python tools\ops_api_server.py
pause
