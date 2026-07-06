@echo off
REM Single-instance scheduler launcher
REM Kill any existing schedulers first
taskkill //F //FI "IMAGENAME eq python.exe" //FI "WINDOWTITLE eq *cycle_scheduler*" >nul 2>&1
REM Wait for cleanup
timeout /t 2 /nobreak >nul
REM Start ONE instance using hermes venv Python
C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe C:\Users\Administrator\AppData\Local\hermes\cycle_scheduler.py --interval-minutes 60
