@echo off
title MCGG Autonomous Agent (Administrator Mode)
color 0A

:: Meminta hak Administrator otomatis jika belum admin
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [UAC] Meminta izin Administrator agar input mouse/keyboard tembus ke game...
    powershell -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

cd /d "C:\Projects\mcgg"
echo =======================================================
echo    MCGG AUTONOMOUS AGENT - ADMIN CONTROLLER AKTIF
echo =======================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment belum dibuat!
    pause
    exit /b 1
)

.venv\Scripts\python.exe live_bot.py
pause
