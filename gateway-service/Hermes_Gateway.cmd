@echo off
rem Hermes Agent Gateway - Messaging Platform Integration
cd /d C:\Users\Administrator\AppData\Local\hermes
set "HERMES_HOME=C:\Users\Administrator\AppData\Local\hermes"
set "PYTHONIOENCODING=utf-8"
set "HERMES_GATEWAY_DETACHED=1"
set "VIRTUAL_ENV=C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv"
C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\pythonw.exe -m hermes_cli.main gateway run
exit /b 0
