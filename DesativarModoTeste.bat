@echo off
:: { "version": "2.0.0", "skill": "ai-native-development-standard", "description": "Desativa o modo de teste e restaura envios oficiais." }
setlocal
chcp 65001 >nul
title Restaurar Modo Producao - Automacoes Hub

echo [1/2] Removendo travas de redirecionamento...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Tools\ConfigurarEmailTeste.ps1" -Remover

echo [2/2] Reiniciando Monitor Central em Modo Producao...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Get-Process powershell -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*MonitorAutomacoes.ps1*' } | Stop-Process -Force -ErrorAction SilentlyContinue"
start /min "" powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0MonitorAutomacoes.ps1"

echo.
echo ============================================================
echo MODO PRODUCAO RESTAURADO!
echo As automacoes voltaram a enviar para os e-mails oficiais.
echo ============================================================
echo.
pause
endlocal
