@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title [HUB v5.2.0] Desativar Modo Teste

echo Carregando configuracoes do ecossistema...

:: Carregar configuracoes via Lib-Config (PowerShell)
for /f "usebackq tokens=*" %%a in (`powershell -NoProfile -Command "Import-Module '..\lib\Lib-Config.psm1'; Get-HubConfig -Key 'ORCHESTRATOR_API_KEY'"`) do set "API_KEY=%%a"
for /f "usebackq tokens=*" %%a in (`powershell -NoProfile -Command "Import-Module '..\lib\Lib-Config.psm1'; Get-HubConfig -Key 'HUB_API_PORT' -Default '8000'"`) do set "API_PORT=%%a"

set "BASE_URL=http://127.0.0.1:!API_PORT!/api/automations"

if "!API_KEY!"=="" (
    echo [ERRO] Nao foi possivel carregar a ORCHESTRATOR_API_KEY do arquivo .env.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo     RETORNANDO PARA MODO PRODUCAO (OFFICIAL) v5.2.0
echo ============================================================
echo.
echo [1] Desativar para TODAS as automacoes
echo [2] Desativar para uma automacao especifica
echo.

set /p choice="Escolha uma opcao: "

if "%choice%"=="1" (
    echo.
    echo Desativando Modo Teste GLOBAL (Retornando a Producao)...
    curl.exe -s -X POST "!BASE_URL!/test-mode/global?enabled=false" ^
         -H "X-API-Key: !API_KEY!" ^
         -H "accept: application/json"
    goto end
)

if "%choice%"=="2" (
    set /p auto_id="Digite o ID da automacao: "
    echo.
    echo Desativando Modo Teste para ID %auto_id%...
    curl.exe -s -X POST "!BASE_URL!/%auto_id%/test-mode?enabled=false" ^
         -H "X-API-Key: !API_KEY!" ^
         -H "accept: application/json"
    goto end
)

:end
echo.
echo.
echo Procedimento finalizado. Verifique o Dashboard.
echo ============================================================
pause
endlocal
