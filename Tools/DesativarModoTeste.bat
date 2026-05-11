@echo off
setlocal
chcp 65001 >nul
title [HUB v5.0] Desativar Modo Teste

set "BASE_URL=http://127.0.0.1:8000/api/automations"
set "API_KEY=hub-secret-token"

echo.
echo ============================================================
echo     RETORNANDO PARA MODO PRODUCAO (OFFICIAL) v5.0
echo ============================================================
echo.
echo [1] Desativar para TODAS as automacoes
echo [2] Desativar para uma automacao especifica
echo.

set /p choice="Escolha uma opcao: "

if "%choice%"=="1" (
    echo.
    echo Desativando Modo Teste GLOBAL (Retornando a Producao)...
    curl -X POST "%BASE_URL%/test-mode/global?enabled=false" ^
         -H "X-API-Key: %API_KEY%" ^
         -H "accept: application/json"
    goto end
)

if "%choice%"=="2" (
    set /p auto_id="Digite o ID da automacao: "
    echo.
    echo Desativando Modo Teste para ID %auto_id%...
    curl -X POST "%BASE_URL%/%auto_id%/test-mode?enabled=false" ^
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
