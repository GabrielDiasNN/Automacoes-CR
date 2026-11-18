# ==============================================================================
# ARQUIVO: Start-WhatsAppDaemon.ps1
# DESCRICAO: Sobe o daemon persistente do WhatsApp (lib/whatsapp-daemon.js) em modo
#            oculto, somente quando WHATSAPP_DAEMON_ENABLED=1 no .env (opt-in).
#            Chamado pelo Start-Orchestrator.ps1 de forma NAO fatal: falha aqui vira
#            aviso e nunca impede o Orchestrator de subir.
# Saidas : 0 = desligado, ja em execucao ou iniciado; 1 = token ausente ou curto (< 32).
# ==============================================================================

$ErrorActionPreference = "Stop"

$InfrastructureDir = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $InfrastructureDir

Import-Module (Join-Path $ProjectRoot "lib\Lib-OrchestratorRuntime.psm1") -Force

$habilitado = Get-OrchestratorEnvValue -ProjectRoot $ProjectRoot -Key "WHATSAPP_DAEMON_ENABLED"
if ($habilitado -ne "1") {
    Write-Host "[WhatsApp Daemon] Desabilitado (WHATSAPP_DAEMON_ENABLED diferente de 1). Nada a fazer." -ForegroundColor Gray
    exit 0
}

# Mesma deteccao da rota em Send-WhatsApp.ps1: CIM (Get-Process nao expoe CommandLine no PS 5.1).
$jaRodando = @(Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*whatsapp-daemon.js*" })
if ($jaRodando.Count -gt 0) {
    Write-Host "[WhatsApp Daemon] Ja esta em execucao (PID $($jaRodando[0].ProcessId))." -ForegroundColor Gray
    exit 0
}

# O token nunca e' escrito na saida: apenas o tamanho e' validado.
$token = Get-OrchestratorEnvValue -ProjectRoot $ProjectRoot -Key "WHATSAPP_DAEMON_TOKEN"
if ([string]::IsNullOrEmpty($token) -or $token.Length -lt 32) {
    Write-Host "[WhatsApp Daemon] WHATSAPP_DAEMON_TOKEN ausente ou com menos de 32 caracteres. Daemon nao iniciado." -ForegroundColor Red
    exit 1
}

$porta = Get-OrchestratorEnvValue -ProjectRoot $ProjectRoot -Key "WHATSAPP_DAEMON_PORT" -Default "8765"
$clientId = Get-OrchestratorEnvValue -ProjectRoot $ProjectRoot -Key "WHATSAPP_DAEMON_CLIENT_ID" -Default "hub-global"
$maxNaoReady = Get-OrchestratorEnvValue -ProjectRoot $ProjectRoot -Key "WHATSAPP_DAEMON_MAX_NOT_READY_MS"

$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
$nodeExe = "node"
if ($nodeCmd) {
    $nodeExe = $nodeCmd.Source
}
else {
    $nodeExe = Join-Path ([Environment]::GetFolderPath("ProgramFiles")) "nodejs\node.exe"
}
$daemonScript = Join-Path $ProjectRoot "lib\whatsapp-daemon.js"
$libDir = Join-Path $ProjectRoot "lib"

# As variaveis WHATSAPP_DAEMON_* sao definidas apenas para o processo que este script
# inicia (Start-Process herda o ambiente atual) e removidas logo em seguida.
$env:WHATSAPP_DAEMON_TOKEN = $token
$env:WHATSAPP_DAEMON_PORT = $porta
$env:WHATSAPP_DAEMON_CLIENT_ID = $clientId
# Teto sem 'ready' (ms): repassado so quando definido no .env; sem ele o daemon usa o padrao (600000).
if (-not [string]::IsNullOrEmpty($maxNaoReady)) { $env:WHATSAPP_DAEMON_MAX_NOT_READY_MS = $maxNaoReady }
try {
    $processo = Start-Process -FilePath $nodeExe -ArgumentList "`"$daemonScript`"" -WorkingDirectory $libDir -WindowStyle Hidden -PassThru
    Write-Host "[WhatsApp Daemon] Iniciado (PID $($processo.Id)) em 127.0.0.1:$porta." -ForegroundColor Green
}
finally {
    Remove-Item Env:\WHATSAPP_DAEMON_TOKEN -ErrorAction SilentlyContinue
    Remove-Item Env:\WHATSAPP_DAEMON_PORT -ErrorAction SilentlyContinue
    Remove-Item Env:\WHATSAPP_DAEMON_CLIENT_ID -ErrorAction SilentlyContinue
    Remove-Item Env:\WHATSAPP_DAEMON_MAX_NOT_READY_MS -ErrorAction SilentlyContinue
}

exit 0
