@echo off
title Computer-Auto Voice Assistant
cd /d "%~dp0"
echo ============================================================
echo  Starting Computer-Auto Voice Automation
echo ============================================================
echo.
echo Look for the sleek floating HUD pill at the top of your screen!
echo.
echo Controls:
echo   - Rapidly Double-Tap Left Ctrl OR Click the HUD Mic Button to Speak.
echo   - Speak your command (e.g. "open notepad", "volume up").
echo   - Double-Tap Left Ctrl again OR Click Stop to execute.
echo   - Press Escape at any time to abort.
echo.
python -u main.py
pause
