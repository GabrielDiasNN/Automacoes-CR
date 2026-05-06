@echo off
REM { "version": "1.1.0", "description": "Shim dinâmico para disparo do WhatsApp via PowerShell" }
SetLocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "..\lib\Send-WhatsApp.ps1" -ExecId "MANUAL_BAT" -Mode AUTO
pause
