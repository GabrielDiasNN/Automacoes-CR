@echo off
setlocal
chcp 65001 >nul
title [HUB v5.0] Ativar Modo Teste

set "BASE_URL=http://127.0.0.1:8000/api/automations"
set "API_KEY=hub-secret-token"

echo.
echo ============================================================
echo      CONFIGURACAO DE MODO TESTE (SANDBOX) v5.0
echo ============================================================
echo.
echo [1] Ativar para TODAS as automacoes
echo [2] Ativar para uma automacao especifica
echo.

set /p choice="Escolha uma opcao: "

if "%choice%"=="1" (
    echo.
    echo Ativando Modo Teste GLOBAL...
    curl -X POST "%BASE_URL%/test-mode/global?enabled=true" ^
         -H "X-API-Key: %API_KEY%" ^
         -H "accept: application/json"
    goto end
)

if "%choice%"=="2" (
    set /p auto_id="Digite o ID da automacao: "
    echo.
    echo Ativando Modo Teste para ID %auto_id%...
    curl -X POST "%BASE_URL%/%auto_id%/test-mode?enabled=true" ^
         -H "X-API-Key: %API_KEY%" ^
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
