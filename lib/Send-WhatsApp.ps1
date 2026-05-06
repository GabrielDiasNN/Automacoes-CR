# ==============================================================================
# ARQUIVO: Send-WhatsApp.ps1
# VERSAO : 1.2
# DESCRICAO: Wrapper PS-nativo para envio de WhatsApp via Node.js (sendWhatsApp.js).
# ==============================================================================

[CmdletBinding()]
param(
    [string]$ExecId = "",
    [string]$Mode = "AUTO",
    [string]$BaseDir = "",
    [string]$NodeExe = "node"
)

$ErrorActionPreference = "Stop"

# --- Detectar Node.js dinamicamente se nao estiver no PATH ---
if (-not (Get-Command $NodeExe -ErrorAction SilentlyContinue)) {
    $progFiles = [Environment]::GetFolderPath("ProgramFiles")
    $NodeExe = Join-Path $progFiles "nodejs\node.exe"
}

# --- Detectar BaseDir dinamicamente se nao fornecido ---
if ([string]::IsNullOrWhiteSpace($BaseDir)) {
    $scriptDir = $PSScriptRoot
    if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
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

# --- Importar Lib-Logging ---
$libDir = $PSScriptRoot
Import-Module (Join-Path $libDir "Lib-Logging.psm1") -Force

if ([string]::IsNullOrWhiteSpace($ExecId)) { $ExecId = New-ExecId }

function Write-Log {
    param([string]$Msg, [string]$Lvl = "INFO")
    if ($Msg -match '[\u00C0-\u00FF]') {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Msg)
        $b64 = [System.Convert]::ToBase64String($bytes)
        Write-AutomacaoLog -Message "B64:$b64" -Level $Lvl -ExecId $ExecId -LogPath $LogFile
    } else {
        Write-AutomacaoLog -Message $Msg -Level $Lvl -ExecId $ExecId -LogPath $LogFile
    }
}

function Test-BridgeRunning {
    try {
        $match = Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" |
        Where-Object { $_.CommandLine -match [regex]::Escape($NodeScript) }
        return ($null -ne $match)
    }
    catch [System.Exception] { return $false }
}

function Invoke-AcquireLock {
    if (Test-Path $LockDir) {
        if (-not (Test-BridgeRunning)) {
            Write-Log "LOCK: lock obsoleto removido."
            Remove-Item $LockDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    if (Test-Path $LockDir) { return $false }
    try {
        New-Item -ItemType Directory -Path $LockDir -Force | Out-Null
        return $true
    }
    catch [System.Exception] { return $false }
}

function Invoke-ReleaseLock {
    if (Test-Path $LockDir) {
        Remove-Item $LockDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# --- VALIDACAO DE REQUISITOS ---
if (-not (Test-Path $BaseDir)) { Write-Log "BaseDir ausente." -Lvl "ERRO"; exit 1 }
if (-not (Test-Path $NodeExe)) { Write-Log "Node.exe ausente em $NodeExe." -Lvl "ERRO"; exit 1 }

# --- ROTEAMENTO ---
if ($Mode -eq "PAIRING" -or -not (Test-Path $SessionDir)) {
    $launchArg = "`"$NodeExe`" `"$NodeScript`" `"$ExecId`" `"PAIRING`""
    Start-Process "cmd" -ArgumentList "/k `"echo Iniciando WhatsApp Pairing... && $launchArg`"" -WindowStyle Normal
    exit 0
}

# --- EXECUCAO SILENCIOSA ---
if (Invoke-AcquireLock) {
    try {
        $proc = Start-Process -FilePath $NodeExe -ArgumentList "`"$NodeScript`" `"$ExecId`" `"$Mode`"" -WorkingDirectory $BaseDir -WindowStyle Hidden -Wait -PassThru
        $nodeExit = $proc.ExitCode
    } finally {
        Invoke-ReleaseLock
    }
    exit $nodeExit
} else {
    exit $EXIT_LOCK_ACTIVE
}
