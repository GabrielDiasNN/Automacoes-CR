@echo off
:: Central de Automações v5.2.1 - Instant Access Button
:: Foco: Velocidade e Acesso Direto

SET URL=http://127.0.0.1:8000/dashboard/
SET API_PORT=8000
SET INFRA_DIR=%~dp0Infrastructure

:: 1. Verificacao ultra-rapida de porta (LISTENING)
netstat -ano | findstr "127.0.0.1:%API_PORT% " | findstr "LISTENING" > nul
if %errorlevel% == 0 (
    :: Servidor online: abre instantaneamente
    start "" "%URL%"
    exit
)

:: 2. Se chegou aqui, o servidor esta offline.
echo [!] Central em Standby. Acionando motores...
powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File "%INFRA_DIR%\Start-Orchestrator.ps1"

:: 3. Abre o navegador e o proprio dashboard tentara reconectar automaticamente
:: gracas ao nosso interceptor de resiliencia no JS.
start "" "%URL%"

exit
