@echo off
setlocal EnableExtensions EnableDelayedExpansion

:: =============================================================================
:: RunWhatsApp.bat — Versão corrigida
:: Correções:
::   1. Bootstrap log ANTES de qualquer lógica (garante rastreabilidade)
::   2. MODE passado ao Node como argv[3] (estava faltando em :run_node_silent)
::   3. Captura de ERRORLEVEL com EnableDelayedExpansion (evita perda em if blocks)
::   4. Timestamp via wmic (sem depender do PowerShell no :log)
::   5. Limpeza de sessão corrompida ao detectar reauth request (ExitCode=21)
::   6. Lock de execução para evitar concorrência entre instâncias (ExitCode=40)
:: =============================================================================

set "EXEC_ID=%~1"
set "MODE=%~2"

set "BASE_DIR=C:\Automacoes\Receitas Bloqueadas"
set "LOG_FILE=%BASE_DIR%\ReceitasBloqueadas.txt"
set "NODE_EXE=C:\Program Files\nodejs\node.exe"
set "NODE_SCRIPT=%BASE_DIR%\sendWhatsApp.js"
set "CONFIG_FILE=%BASE_DIR%\whatsapp-config.json"
set "AUTH_DIR=%BASE_DIR%\.wwebjs_auth"
set "CLIENT_ID=receitas-bloqueadas"
set "SESSION_DIR=%AUTH_DIR%\session-%CLIENT_ID%"
set "REAUTH_EXIT=21"
set "COOLDOWN_EXIT=23"
set "LOCK_DIR=%BASE_DIR%\.sendwhatsapp.lock"
set "LOCK_EXIT=40"
set "LOCK_ACQUIRED=0"

:: ---------------------------------------------------------------------------
:: BOOTSTRAP LOG — Primeiro registro, ANTES de qualquer call ou validação.
:: 2>nul garante que falha de escrita (arquivo aberto no editor) NÃO aborta o BAT.
:: ---------------------------------------------------------------------------
>> "%LOG_FILE%" echo([%date% %time:~0,8%] [BAT] ========================================================= 2>nul
>> "%LOG_FILE%" echo([%date% %time:~0,8%] [BAT] BOOTSTRAP: BAT iniciado. Args: ExecId=%EXEC_ID% Mode=%MODE% 2>nul

:: Defaults
if not defined EXEC_ID set "EXEC_ID=sem-exec-id"
if not defined MODE set "MODE=AUTO"

if /I not "%MODE%"=="AUTO" if /I not "%MODE%"=="PAIRING" (
    call :log AVISO: MODE invalido recebido: [%MODE%]. Assumindo AUTO.
    set "MODE=AUTO"
)

call :log INICIO - BAT recebido. ExecId=%EXEC_ID% Mode=%MODE%
call :log BASE_DIR=%BASE_DIR%
call :log NODE_EXE=%NODE_EXE%
call :log NODE_SCRIPT=%NODE_SCRIPT%
call :log CONFIG_FILE=%CONFIG_FILE%
call :log SESSION_DIR=%SESSION_DIR%
call :log LOG_FILE=%LOG_FILE%

:: ---------------------------------------------------------------------------
:: Validar pré-requisitos
:: ---------------------------------------------------------------------------
call :validar_pre_requisitos
set "PRE_EXIT=!ERRORLEVEL!"
if !PRE_EXIT! NEQ 0 (
    call :log ERRO: Validacao de pre-requisitos falhou. ExitCode=!PRE_EXIT!
    call :log FIM - BAT finalizado com erro. ExitCode=!PRE_EXIT! ExecId=%EXEC_ID%
    call :log =========================================================
    exit /b !PRE_EXIT!
)

:: ---------------------------------------------------------------------------
:: Garantir diretório de trabalho correto
:: ---------------------------------------------------------------------------
cd /d "%BASE_DIR%"
set "CD_EXIT=!ERRORLEVEL!"
if !CD_EXIT! NEQ 0 (
    call :log ERRO: Falha ao acessar pasta base. PATH=%BASE_DIR% ExitCode=!CD_EXIT!
    exit /b 1
)
call :log WorkingDir alterado para: %CD%

:: ---------------------------------------------------------------------------
:: Verificar sessão LocalAuth
:: ---------------------------------------------------------------------------
if exist "%SESSION_DIR%\" (
    call :log Sessao LocalAuth: ENCONTRADA em %SESSION_DIR%
    set "SESSION_EXISTS=1"
) else (
    call :log Sessao LocalAuth: NAO encontrada em %SESSION_DIR%
    set "SESSION_EXISTS=0"
)

:: ---------------------------------------------------------------------------
:: Roteamento por MODE
:: ---------------------------------------------------------------------------
if /I "%MODE%"=="PAIRING" (
    call :log MODE=PAIRING solicitado explicitamente. Lancando modo visivel interativo.
    goto :launch_visible
)

if /I "%MODE%"=="AUTO" (
    if "!SESSION_EXISTS!"=="0" (
        call :log AUTO: Sessao ausente. Lancando modo visivel para parear.
        goto :launch_visible
    )
    call :log AUTO: Sessao presente. Executando Node em modo silencioso.
    goto :run_silent_flow
)

:: Fallback
call :log AVISO: MODE desconhecido [%MODE%]. Assumindo AUTO silencioso.

:run_silent_flow
call :acquire_lock
set "LOCK_RESULT=!ERRORLEVEL!"
if !LOCK_RESULT! NEQ 0 (
    call :log FIM - BAT finalizado sem executar NODE por lock ativo. ExitCode=!LOCK_RESULT! ExecId=%EXEC_ID%
    call :log =========================================================
    exit /b !LOCK_RESULT!
)

call :run_node_silent
set "NODE_EXIT=!ERRORLEVEL!"
call :release_lock
call :log NODE finalizado em modo silencioso. ExitCode=!NODE_EXIT! ExecId=%EXEC_ID%

:: Se Node solicitou reautenticação interativa (ExitCode=21)
if "!NODE_EXIT!"=="!REAUTH_EXIT!" (
    call :log REAUTH: Node exigiu reautenticacao. ExitCode=!REAUTH_EXIT!

    :: Deletar sessão corrompida para forçar re-pareamento limpo
    if exist "%SESSION_DIR%\" (
        call :log REAUTH: Deletando sessao corrompida: %SESSION_DIR%
        rmdir /s /q "%SESSION_DIR%" 2>nul
        if exist "%SESSION_DIR%\" (
            call :log AVISO: Nao foi possivel deletar sessao. Tentando prosseguir assim mesmo.
        ) else (
            call :log REAUTH: Sessao deletada com sucesso.
        )
    )

    call :log REAUTH: Relancando em modo visivel interativo.
    goto :launch_visible
)

if "!NODE_EXIT!"=="!COOLDOWN_EXIT!" (
    call :log NODE informou cooldown de retry ativo (ExitCode=!COOLDOWN_EXIT!). Nenhum novo envio foi realizado nesta execução.
)

call :log FIM - BAT finalizado. ExitCode=!NODE_EXIT! ExecId=%EXEC_ID%
call :log =========================================================
exit /b !NODE_EXIT!

:: ---------------------------------------------------------------------------
:launch_visible
:: ---------------------------------------------------------------------------
call :log Lancando NODE em janela CMD visivel. ExecId=%EXEC_ID% Mode=PAIRING
start "WhatsApp Pareamento" cmd /k ^
  "echo Iniciando WhatsApp Pairing... && "%NODE_EXE%" "%NODE_SCRIPT%" "%EXEC_ID%" "PAIRING""
set "START_EXIT=!ERRORLEVEL!"
if !START_EXIT! NEQ 0 (
    call :log ERRO: Falha ao abrir janela CMD visivel. ExitCode=!START_EXIT!
    exit /b 30
)
call :log Janela interativa aberta com sucesso. Controle transferido ao usuario.
call :log FIM - BAT finalizado. ExitCode=0 ExecId=%EXEC_ID%
call :log =========================================================
exit /b 0

:: ---------------------------------------------------------------------------
:acquire_lock
:: ---------------------------------------------------------------------------
if exist "%LOCK_DIR%\" (
    call :check_bridge_running
    if "!BRIDGE_RUNNING!"=="0" (
        call :log LOCK: lock obsoleto detectado. Tentando limpar %LOCK_DIR%
        rmdir /s /q "%LOCK_DIR%" 2>nul
    )
)

if exist "%LOCK_DIR%\" (
    call :log LOCK: execucao concorrente detectada. Lock em uso: %LOCK_DIR%
    exit /b %LOCK_EXIT%
)

mkdir "%LOCK_DIR%" 2>nul
set "MKDIR_EXIT=!ERRORLEVEL!"
if !MKDIR_EXIT! NEQ 0 (
    call :log LOCK: falha ao adquirir lock (mkdir retornou !MKDIR_EXIT!).
    exit /b %LOCK_EXIT%
)

set "LOCK_ACQUIRED=1"
> "%LOCK_DIR%\owner.txt" echo ExecId=%EXEC_ID%;Mode=%MODE%;Started=%date% %time:~0,8% 2>nul
call :log LOCK: lock adquirido com sucesso em %LOCK_DIR%
exit /b 0

:: ---------------------------------------------------------------------------
:release_lock
:: ---------------------------------------------------------------------------
if "!LOCK_ACQUIRED!"=="1" (
    if exist "%LOCK_DIR%\" (
        rmdir /s /q "%LOCK_DIR%" 2>nul
        if exist "%LOCK_DIR%\" (
            call :log AVISO: nao foi possivel liberar lock em %LOCK_DIR%
        ) else (
            call :log LOCK: lock liberado com sucesso.
        )
    )
    set "LOCK_ACQUIRED=0"
)
exit /b 0

:: ---------------------------------------------------------------------------
:check_bridge_running
:: ---------------------------------------------------------------------------
set "BRIDGE_RUNNING=0"
for /f "usebackq delims=" %%a in (
    `powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Get-CimInstance Win32_Process -Filter \"Name = 'node.exe'\" | Where-Object { $_.CommandLine -match 'sendWhatsApp\\.js' }; if($p){'1'} else {'0'}" 2^>nul`
) do set "BRIDGE_RUNNING=%%a"
if not defined BRIDGE_RUNNING set "BRIDGE_RUNNING=0"
exit /b 0

:: ---------------------------------------------------------------------------
:run_node_silent
:: ---------------------------------------------------------------------------
:: CORREÇÃO: agora passa "%MODE%" como argv[3] ao Node.
:: Sem isso, process.argv[3] chegava undefined → Node não sabia o modo.
call :log Disparando NODE em modo silencioso. ExecId=%EXEC_ID% Mode=%MODE%
"%NODE_EXE%" "%NODE_SCRIPT%" "%EXEC_ID%" "%MODE%"
set "INNER_EXIT=!ERRORLEVEL!"
call :log NODE processo encerrado. ExitCode=!INNER_EXIT!
exit /b !INNER_EXIT!

:: ---------------------------------------------------------------------------
:validar_pre_requisitos
:: ---------------------------------------------------------------------------
if not exist "%BASE_DIR%\" (
    call :log ERRO: Pasta base nao encontrada: %BASE_DIR%
    exit /b 1
)
if not exist "%NODE_EXE%" (
    call :log ERRO: node.exe nao encontrado em: %NODE_EXE%
    exit /b 2
)
if not exist "%NODE_SCRIPT%" (
    call :log ERRO: sendWhatsApp.js nao encontrado em: %NODE_SCRIPT%
    exit /b 3
)
if not exist "%CONFIG_FILE%" (
    call :log ERRO: whatsapp-config.json nao encontrado em: %CONFIG_FILE%
    exit /b 4
)
call :log Pre-requisitos validados com sucesso.
exit /b 0

:: ---------------------------------------------------------------------------
:log
:: ---------------------------------------------------------------------------
:: Timestamp via PowerShell com fallback para %date%/%time%
:: 2>nul em TODAS as escritas para nunca abortar quando o arquivo está travado.
set "TS="
for /f "usebackq delims=" %%a in (
    `powershell -NoProfile -ExecutionPolicy Bypass -Command "[DateTime]::Now.ToString('dd/MM/yyyy HH:mm:ss')" 2^>nul`
) do set "TS=%%a"
if not defined TS set "TS=%date% %time:~0,8%"
>> "%LOG_FILE%" echo([%TS%] [BAT] %* 2>nul
goto :eof