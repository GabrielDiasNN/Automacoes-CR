# ==============================================================================
# ARQUIVO: Send-WhatsApp.ps1
# VERSÃO: 1.0
# DESCRIÇÃO: Wrapper PS-nativo para envio de WhatsApp via Node.js (sendWhatsApp.js).
#            Substitui a lógica de RunWhatsApp.bat, expondo uma interface PS limpa.
#            RunWhatsApp.bat se torna um shim de 5 linhas que chama este script.
#
# MODOS:
#   AUTO    — Executa Node em modo silencioso (requer sessão LocalAuth ativa).
#             Se sessão ausente, redireciona automaticamente para PAIRING.
#   PAIRING — Abre janela CMD visível para pareamento manual do dispositivo.
#
# EXIT CODES (espelhados do Node/BAT):
#   0  — Sucesso ou desabilitado por config
#   11 — Anexo ausente
#   20 — Erro fatal Node
#   21 — Reautenticação exigida (sessão expirada)
#   22 — Config inválida
#   23 — Cooldown de retry ativo
#   30 — Falha ao abrir janela interativa
#   40 — Execução concorrente bloqueada (lock ativo)
# ==============================================================================

[CmdletBinding()]
param(
    [string]$ExecId = "",
    [string]$Mode = "AUTO",
    [string]$BaseDir = "",
    [string]$NodeExe = "C:\Program Files\nodejs\node.exe"
)

$ErrorActionPreference = "Stop"

# --- Detectar BaseDir dinamicamente se não fornecido ---
if ([string]::IsNullOrWhiteSpace($BaseDir)) {
    $scriptDir = $PSScriptRoot
    if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
    
    # Assume que se está em \lib\, a pasta base das receitas bloqueadas é ..\Receitas Bloqueadas
    $root = Split-Path -Parent $scriptDir
    $BaseDir = Join-Path $root "Receitas Bloqueadas"
}

# --- Caminhos derivados ---
$NodeScript = Join-Path $BaseDir "sendWhatsApp.js"
$ConfigFile = Join-Path $BaseDir "whatsapp-config.json"
$LogFile = Join-Path $BaseDir "ReceitasBloqueadas.txt"
$AuthDir = Join-Path $BaseDir ".wwebjs_auth"
$ClientId = "receitas-bloqueadas"
$SessionDir = Join-Path $AuthDir "session-$ClientId"
$LockDir = Join-Path $BaseDir ".sendwhatsapp.lock"

$EXIT_LOCK_ACTIVE = 40
$EXIT_REAUTH = 21
$EXIT_COOLDOWN = 23
$EXIT_LAUNCH_FAIL = 30

# --- Importar Lib-Logging (localizada relativa a este script) ---
$libDir = $PSScriptRoot
Import-Module (Join-Path $libDir "Lib-Logging.psm1") -Force

if ([string]::IsNullOrWhiteSpace($ExecId)) { $ExecId = New-ExecId }

function Write-Log {
    param([string]$Msg, [string]$Lvl = "INFO")
    Write-AutomacaoLog -Message $Msg -Level $Lvl -ExecId $ExecId -LogPath $LogFile
}

function Test-BridgeRunning {
    try {
        $match = Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" |
        Where-Object { $_.CommandLine -match [regex]::Escape($NodeScript) }
        return ($null -ne $match)
    }
    catch { return $false }
}

function Invoke-AcquireLock {
    # Se lock existe, verificar se processo ainda está vivo
    if (Test-Path $LockDir) {
        if (-not (Test-BridgeRunning)) {
            Write-Log "LOCK: lock obsoleto detectado. Tentando limpar: $LockDir"
            try { Remove-Item $LockDir -Recurse -Force -ErrorAction Stop }
            catch {
                Write-Log "LOCK: nao foi possivel limpar lock obsoleto. Abortando." -Lvl "WARN"
                return $false
            }
            Write-Log "LOCK: lock obsoleto removido com sucesso."
        }
    }

    if (Test-Path $LockDir) {
        Write-Log "LOCK: execucao concorrente detectada. Lock em uso: $LockDir" -Lvl "WARN"
        return $false
    }

    try {
        New-Item -ItemType Directory -Path $LockDir -Force | Out-Null
        $ownerInfo = "ExecId=$ExecId;Mode=$Mode;Started=$(Get-Date -Format 'dd/MM/yyyy HH:mm:ss')"
        Set-Content -Path (Join-Path $LockDir "owner.txt") -Value $ownerInfo -Encoding UTF8
        Write-Log "LOCK: lock adquirido em: $LockDir"
        return $true
    }
    catch {
        Write-Log "LOCK: falha ao adquirir lock: $_" -Lvl "WARN"
        return $false
    }
}

function Invoke-ReleaseLock {
    if (Test-Path $LockDir) {
        try {
            Remove-Item $LockDir -Recurse -Force -ErrorAction Stop
            Write-Log "LOCK: lock liberado."
        }
        catch {
            Write-Log "LOCK: nao foi possivel liberar lock em $LockDir" -Lvl "WARN"
        }
    }
}

# ============================================================
# INÍCIO — log de bootstrap e validação de prerrequisitos
# ============================================================
Write-Log "=================================================================================="
Write-Log "INICIO - Send-WhatsApp.ps1 iniciado. ExecId=$ExecId Mode=$Mode"
Write-Log "BaseDir=$BaseDir | NodeExe=$NodeExe | NodeScript=$NodeScript"

# Validar pré-requisitos
$preErro = $null
if (-not (Test-Path $BaseDir)) { $preErro = "Pasta base nao encontrada: $BaseDir" }
elseif (-not (Test-Path $NodeExe)) { $preErro = "node.exe nao encontrado: $NodeExe" }
elseif (-not (Test-Path $NodeScript)) { $preErro = "sendWhatsApp.js nao encontrado: $NodeScript" }
elseif (-not (Test-Path $ConfigFile)) { $preErro = "whatsapp-config.json nao encontrado: $ConfigFile" }

if ($preErro) {
    Write-Log "ERRO: $preErro" -Lvl "ERRO"
    Write-Log "FIM - Finalizado com erro de pre-requisito."
    Write-Log "=================================================================================="
    exit 1
}
Write-Log "Pre-requisitos validados com sucesso."

# Normalizar Mode
$Mode = $Mode.ToUpper().Trim()
if ($Mode -ne "AUTO" -and $Mode -ne "PAIRING") {
    Write-Log "MODE invalido recebido: [$Mode]. Assumindo AUTO." -Lvl "WARN"
    $Mode = "AUTO"
}

# Verificar sessão LocalAuth
$sessionExists = Test-Path $SessionDir
if ($sessionExists) { Write-Log "Sessao LocalAuth: ENCONTRADA em $SessionDir" }
else { Write-Log "Sessao LocalAuth: NAO encontrada em $SessionDir" }

# Roteamento por Mode e sessão
if ($Mode -eq "PAIRING") {
    Write-Log "MODE=PAIRING solicitado. Lancando modo visivel interativo."
    $launchArg = "`"$NodeExe`" `"$NodeScript`" `"$ExecId`" `"PAIRING`""
    try {
        Start-Process "cmd" -ArgumentList "/k `"echo Iniciando WhatsApp Pairing... && $launchArg`"" -WindowStyle Normal -ErrorAction Stop
        Write-Log "Janela interativa aberta com sucesso."
        Write-Log "FIM - Finalizado. ExitCode=0"
        Write-Log "=================================================================================="
        exit 0
    }
    catch {
        Write-Log "ERRO: Falha ao abrir janela interativa: $_" -Lvl "ERRO"
        Write-Log "FIM - Finalizado. ExitCode=$EXIT_LAUNCH_FAIL"
        Write-Log "=================================================================================="
        exit $EXIT_LAUNCH_FAIL
    }
}

# AUTO: sem sessão → redirecionar para PAIRING
if (-not $sessionExists) {
    Write-Log "AUTO: Sessao ausente. Redirecionando para modo PAIRING." -Lvl "WARN"
    $launchArg = "`"$NodeExe`" `"$NodeScript`" `"$ExecId`" `"PAIRING`""
    try {
        Start-Process "cmd" -ArgumentList "/k `"echo Iniciando WhatsApp Pairing... && $launchArg`"" -WindowStyle Normal -ErrorAction Stop
        Write-Log "Janela interativa aberta. Controle transferido ao usuario."
        Write-Log "FIM - Finalizado. ExitCode=0"
        Write-Log "=================================================================================="
        exit 0
    }
    catch {
        Write-Log "ERRO: Falha ao abrir janela de pairing: $_" -Lvl "ERRO"
        Write-Log "FIM - Finalizado. ExitCode=$EXIT_LAUNCH_FAIL"
        Write-Log "=================================================================================="
        exit $EXIT_LAUNCH_FAIL
    }
}

# AUTO + sessão presente → modo silencioso
Write-Log "AUTO: Sessao presente. Executando Node em modo silencioso."

# Adquirir lock
$lockAcquired = Invoke-AcquireLock
if (-not $lockAcquired) {
    Write-Log "FIM - Finalizado sem executar NODE por lock ativo. ExitCode=$EXIT_LOCK_ACTIVE"
    Write-Log "=================================================================================="
    exit $EXIT_LOCK_ACTIVE
}

# Executar Node
Write-Log "Disparando NODE em modo silencioso. ExecId=$ExecId Mode=$Mode"

try {
    $proc = Start-Process -FilePath $NodeExe `
        -ArgumentList "`"$NodeScript`" `"$ExecId`" `"$Mode`"" `
        -WorkingDirectory $BaseDir `
        -WindowStyle Hidden `
        -Wait `
        -PassThru `
        -ErrorAction Stop
    $nodeExit = $proc.ExitCode
}
catch {
    Write-Log "ERRO: Falha ao iniciar processo Node: $_" -Lvl "ERRO"
    Invoke-ReleaseLock
    Write-Log "FIM - Finalizado com erro de processo. ExitCode=20"
    Write-Log "=================================================================================="
    exit 20
}

Invoke-ReleaseLock
Write-Log "NODE finalizado. ExitCode=$nodeExit"

# Tratamento de REAUTH (exit 21)
if ($nodeExit -eq $EXIT_REAUTH) {
    Write-Log "REAUTH: Node exigiu reautenticacao. ExitCode=$EXIT_REAUTH" -Lvl "WARN"
    if (Test-Path $SessionDir) {
        Write-Log "REAUTH: Deletando sessao corrompida: $SessionDir"
        try {
            Remove-Item $SessionDir -Recurse -Force -ErrorAction Stop
            Write-Log "REAUTH: Sessao deletada com sucesso."
        }
        catch {
            Write-Log "REAUTH: Nao foi possivel deletar sessao: $_" -Lvl "WARN"
        }
    }
    Write-Log "REAUTH: Relancando em modo visivel interativo."
    $launchArg = "`"$NodeExe`" `"$NodeScript`" `"$ExecId`" `"PAIRING`""
    try {
        Start-Process "cmd" -ArgumentList "/k `"echo Iniciando WhatsApp Re-Pairing... && $launchArg`"" -WindowStyle Normal -ErrorAction Stop
        Write-Log "Janela de re-pairing aberta com sucesso."
    }
    catch {
        Write-Log "ERRO: Falha ao abrir janela de re-pairing: $_" -Lvl "ERRO"
    }
    Write-Log "FIM - Finalizado. ExitCode=$EXIT_REAUTH"
    Write-Log "=================================================================================="
    exit $EXIT_REAUTH
}

# Cooldown (exit 23) — apenas log, pass-through
if ($nodeExit -eq $EXIT_COOLDOWN) {
    Write-Log "NODE informou cooldown de retry ativo - ExitCode=$EXIT_COOLDOWN. Nenhum envio realizado." -Lvl "WARN"
}

Write-Log "FIM - Finalizado. ExitCode=$nodeExit"
Write-Log "=================================================================================="
exit $nodeExit
