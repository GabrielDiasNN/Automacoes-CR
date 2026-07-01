# ==============================================================================
# ARQUIVO: Send-WhatsApp.ps1
# VERSAO : 2.2
# DESCRICAO: Wrapper Global para envio de WhatsApp. Suporta parametros explicitos
#            ou carregamento de 'whatsapp-config.json' para retrocompatibilidade.
#            Inclui rotina de autolimpeza direcionada de processos zumbis e locks.
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
$ProcessModule = Join-Path $LibDir "Lib-Process.psm1"
Import-Module $ProcessModule -Force

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
    $resolvedConfig = Convert-Path $ConfigPath
    $base = Split-Path -Parent $resolvedConfig

    # Suporte a contactId completo (grupos @g.us) com fallback para contactPhone
    $finalPhone = if ($json.target.contactId) { $json.target.contactId } else { $json.target.contactPhone }
    $finalClientId = $json.auth.clientId

    # Suporte a mensagem via arquivo externo (textFile) com fallback para caption inline
    if ($json.message.textFile) {
        $txtPath = Join-Path $base $json.message.textFile
        $finalMessage = Get-Content $txtPath -Raw -Encoding UTF8
    } else {
        $finalMessage = "*$($json.message.caption.title.text)*`n$($json.message.caption.body.text)"
    }

    # Resolve anexo (assume relativo ao config.json se nao for absoluto)
    if ($json.message.sendAttachment -and $json.paths.attachmentPath) {
        $finalAttachment = Join-Path $base $json.paths.attachmentPath
    }
}

# --- Limpeza de Locks de Sessão e Processos Zumbis (Mitigação de travamentos de Puppeteer) ---
function Clear-StaleWhatsAppLocksAndProcesses {
    $now = [DateTime]::Now
    $authSessionDir = Join-Path $LibDir ".wwebjs_auth"
    
    # 1. Limpeza direcionada de processos zumbis do Chromium e Node vinculados ao repositório
    try {
        $processes = Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe' OR Name = 'node.exe'" -ErrorAction SilentlyContinue
        foreach ($proc in $processes) {
            $cmd = $proc.CommandLine
            $path = $proc.ExecutablePath
            
            # Filtro seguro: encerra apenas se originar de 'Automacoes' e tiver mais de 10 segundos
            if (($cmd -and $cmd -like "*Automacoes*") -or ($path -and $path -like "*Automacoes*")) {
                $creationDate = $proc.CreationDate
                if ($creationDate) {
                    $age = $now - $creationDate
                    if ($age.TotalSeconds -lt 10) {
                        continue
                    }
                }
                try {
                    Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
                } catch [System.Exception] {}
            }
        }
    } catch [System.Exception] {}

    # 2. Remoção de arquivos LOCK residuais do perfil
    if ($finalClientId) {
        $sessionPath = Join-Path $authSessionDir "session-$finalClientId"
        if (Test-Path $sessionPath) {
            Write-Host "Limpando arquivos de lock residuais no perfil: $sessionPath" -ForegroundColor Gray
            $lockFiles = Get-ChildItem -Path $sessionPath -Recurse -Filter "*lock*" -ErrorAction SilentlyContinue
            $mainLock = Join-Path $sessionPath "Default\Lock"
            if (Test-Path $mainLock) {
                $lockFiles += Get-Item $mainLock -ErrorAction SilentlyContinue
            }
            
            foreach ($file in $lockFiles) {
                if (Test-Path $file.FullName) {
                    try {
                        Remove-Item -Path $file.FullName -Force -ErrorAction Stop
                    } catch [System.Exception] {}
                }
            }
        }
    }
}

# Executar a limpeza antes do início da inicialização do canal
Clear-StaleWhatsAppLocksAndProcesses

# --- Validacao ---
if ([string]::IsNullOrWhiteSpace($finalPhone)) { Write-Error "Telefone de destino ausente."; exit 1 }
if ([string]::IsNullOrWhiteSpace($finalMessage)) { Write-Error "Mensagem vazia."; exit 1 }

# --- Configurar Log padrao se vazio ---
if ([string]::IsNullOrWhiteSpace($LogFile)) {
    $root = Split-Path -Parent $LibDir
    $LogFile = Join-Path $root "Logs\WhatsApp_Global.log"
}

# --- Execucao ---
Write-Host "Acionando Motor de WhatsApp Global..." -ForegroundColor Cyan

$nodeArgs = @(
    "`"$NodeScript`"",
    "`"$ExecId`"",
    "`"$Mode`"",
    "`"$finalClientId`"",
    "`"$finalPhone`"",
    $(if ($finalAttachment) { "`"$finalAttachment`"" } else { '""' }),
    "`"$finalMessage`"",
    "`"$LogFile`""
)

$WorkDir = if ($ConfigPath -and (Test-Path $ConfigPath)) {
    $resolvedPath = Convert-Path $ConfigPath
    $parent = Split-Path -Parent $resolvedPath
    if ([string]::IsNullOrWhiteSpace($parent)) { (Get-Location).Path } else { $parent }
} else {
    (Get-Location).Path
}
# Resolve node_modules: usa WorkDir quando existe, senão fallback para Receitas Bloqueadas
$candidateNodePath = Join-Path $WorkDir "node_modules"
$fallbackNodePath  = Join-Path $LibDir "..\Receitas Bloqueadas\node_modules"
$env:NODE_PATH = if (Test-Path $candidateNodePath) { $candidateNodePath } else { $fallbackNodePath }

$result = Invoke-NativeProcess -FilePath $NodeExe -Arguments ($nodeArgs -join " ") -WorkingDirectory $WorkDir -LogAction {
    param($msg, $lvl)
    if ($lvl -eq "WARN") {
        Write-Host $msg -ForegroundColor Yellow
    } else {
        Write-Host $msg
    }
}

if ($result.ExitCode -eq 0) {
    Write-Host "[OK] WhatsApp enviado com sucesso." -ForegroundColor Green
} else {
    Write-Host "[FAIL] Falha no envio do WhatsApp (ExitCode: $($result.ExitCode)). Verifique os logs." -ForegroundColor Red
    exit $result.ExitCode
}
