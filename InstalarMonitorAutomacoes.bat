@echo off
chcp 65001 >nul
TITLE Instalador do Monitor Central v3.2
COLOR 1F
CLS

ECHO ========================================================
ECHO INSTALADOR: MONITOR DE AUTOMACOES
ECHO ========================================================
ECHO.
ECHO Passo 1: Verificando arquivos necessarios...

IF NOT EXIST "C:\Automacoes\MonitorAutomacoes.ps1" (
ECHO [FALTA] MonitorAutomacoes.ps1 nao encontrado.
GOTO :ARQUIVO_FALTANDO
)

IF NOT EXIST "C:\Automacoes\SetupMonitor.ps1" (
ECHO [FALTA] SetupMonitor.ps1 nao encontrado.
GOTO :ARQUIVO_FALTANDO
)

IF NOT EXIST "C:\Automacoes\config.json" (
ECHO [FALTA] config.json nao encontrado.
GOTO :ARQUIVO_FALTANDO
)

ECHO [OK] Todos os arquivos encontrados.
ECHO.
ECHO Passo 2: Configurando inicializacao automatica...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Automacoes\SetupMonitor.ps1"

IF %ERRORLEVEL% EQU 0 (
COLOR 2F
ECHO.
ECHO ========================================================
ECHO SUCESSO TOTAL
ECHO ========================================================
ECHO.
ECHO 1. O Monitor foi configurado para iniciar com o Windows.
ECHO 2. Uma instancia de teste ja foi iniciada.
ECHO.
ECHO Verifique a pasta C:\Automacoes\Logs para confirmar.
ECHO.
PAUSE
EXIT
) ELSE (
COLOR 4F
ECHO.
ECHO [ERRO] O script de instalacao falhou.
ECHO Verifique se rodou como ADMINISTRADOR.
ECHO.
PAUSE
EXIT
)

:ARQUIVO_FALTANDO
COLOR 4F
ECHO.
ECHO [ERRO CRITICO] Arquivos obrigatorios nao encontrados em C:\Automacoes\
ECHO.
PAUSE