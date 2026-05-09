# ==============================================================================
# ARQUIVO: Send-WhatsApp.ps1
# VERSAO : 2.1
# DESCRICAO: Wrapper Global para envio de WhatsApp. Suporta parametros explicitos
#            ou carregamento de 'whatsapp-config.json' para retrocompatibilidade.
# ==============================================================================

[CmdletBinding()]
param(
    [string]$Message = "",
    [string]$Phone = "",
    [string]$AttachmentPath = "",
    [string]$ConfigPath = "", # Se informado, ignora Message/Phone/AttachmentPath e usa o JSON
    [string]$ExecId = "manual",
    [string]$Mode = "AUTO",
    [string]$ClientId = "hub-global",
    [string]$LogFile = ""
)

$ErrorActionPreference = "Stop"
$LibDir = $PSScriptRoot
$NodeScript = Join-Path $LibDir "WhatsApp-Core.js"

# --- Detectar Node.js ---
$NodeExe = "node"
if (-not (Get-Command $NodeExe -ErrorAction SilentlyContinue)) {
    $progFiles = [Environment]::GetFolderPath("ProgramFiles")
    $NodeExe = Join-Path $progFiles "nodejs\node.exe"
}

# --- Carregar de Config se informado ---
$finalMessage = $Message
$finalPhone = $Phone
$finalAttachment = $AttachmentPath
$finalClientId = $ClientId

if ($ConfigPath -and (Test-Path $ConfigPath)) {
    $json = Get-Content $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $finalPhone = $json.target.contactPhone
    $finalMessage = "*$($json.message.caption.title.text)*`n$($json.message.caption.body.text)"
    $finalClientId = $json.auth.clientId
    
    # Resolve anexo (assume relativo ao config.json se nao for absoluto)
    if ($json.message.sendAttachment -and $json.paths.attachmentPath) {
        $base = Split-Path -Parent $ConfigPath
        $finalAttachment = Join-Path $base $json.paths.attachmentPath
    }
}

# --- Validacao ---
if ([string]::IsNullOrWhiteSpace($finalPhone)) { Write-Error "Telefone de destino ausente."; exit 1 }
if ([string]::IsNullOrWhiteSpace($finalMessage)) { Write-Error "Mensagem vazia."; exit 1 }

# --- Configurar Log padrao se vazio ---
if ([string]::IsNullOrWhiteSpace($LogFile)) {
    $root = Split-Path -Parent $LibDir
    $LogFile = Join-Path $root "Logs\WhatsApp_Global.log"
}

# --- Execucao ---
Write-Host "📱 Acionando Motor de WhatsApp Global..." -ForegroundColor Cyan

$args = @(
    "`"$NodeScript`"",
    "`"$ExecId`"",
    "`"$Mode`"",
    "`"$finalClientId`"",
    "`"$finalPhone`"",
    (if ($finalAttachment) { "`"$finalAttachment`"" } else { '""' }),
    "`"$finalMessage`"",
    "`"$LogFile`""
)

$proc = Start-Process -FilePath $NodeExe -ArgumentList $args -WindowStyle Hidden -Wait -PassThru -WorkingDirectory $LibDir

if ($proc.ExitCode -eq 0) {
    Write-Host "✅ WhatsApp enviado com sucesso." -ForegroundColor Green
} else {
    Write-Host "❌ Falha no envio do WhatsApp (ExitCode: $($proc.ExitCode)). Verifique os logs." -ForegroundColor Red
    exit $proc.ExitCode
}
