@echo off
title Computer-Auto Voice Assistant
cd /d "%~dp0"
echo ============================================================
echo  Starting Computer-Auto Voice Automation
echo ============================================================
echo.
echo Look for the Computer-Auto Control Center window on your screen!
echo (You can also switch to Mini HUD mode anytime via the button in the app)
echo.
echo Controls:
echo   - Rapidly Double-Tap Left Ctrl OR Click the Mic Button to Speak.
echo   - Type commands directly into the Control Center to test without speaking.
echo   - Speak your command (e.g. "open notepad", "volume up").
echo   - Double-Tap Left Ctrl again OR Click Stop to execute.
echo   - Press Escape at any time to abort.
echo.
python -u main.py
pause
