@echo off
:: { "version": "2.0.0", "skill": "ai-native-development-standard", "description": "Ativa o redirecionamento global de e-mails para modo de teste." }
setlocal
chcp 65001 >nul
title Ativar Modo de Teste - Automacoes Hub

echo [1/2] Configurando redirecionamento de e-mail...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Tools\ConfigurarEmailTeste.ps1"

echo [2/2] Reiniciando Monitor Central...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Get-Process powershell -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*MonitorAutomacoes.ps1*' } | Stop-Process -Force -ErrorAction SilentlyContinue"
start /min "" powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0MonitorAutomacoes.ps1"

echo.
echo ============================================================
echo MODO DE TESTE ATIVADO COM SUCESSO!
echo O Monitor foi reiniciado com as novas travas.
echo ============================================================
echo.
pause
endlocal
