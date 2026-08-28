@echo off
chcp 65001 >nul
cd /d "%~dp0"
python 启动检查.py
pause
