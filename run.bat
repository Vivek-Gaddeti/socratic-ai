@echo off
title SocraticAI Platform
echo ===================================================
echo   Starting SocraticAI Learning Platform...
echo ===================================================
set PYTHONUTF8=1
cd /d "%~dp0backend"
python main.py
pause
