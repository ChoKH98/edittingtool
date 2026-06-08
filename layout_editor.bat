@echo off
:: IC Layout Editor — Windows launcher (runs via WSL)
:: Requires: WSL2 + Ubuntu-24.04, WSLg (Windows 11) or VcXsrv/X410
wsl -d Ubuntu-24.04 -- bash -c "cd /home/whqkrel/edittingtool && python3 main.py"
