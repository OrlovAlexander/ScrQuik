@echo off
setlocal
cd /d "%~dp0\.."
python -u -m analyzer --watch-net-pool %*
