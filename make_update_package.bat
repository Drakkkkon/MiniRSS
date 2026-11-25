@echo off
chcp 65001 >nul
cd /d "%~dp0"
py create_update_package.py
if errorlevel 1 pause
