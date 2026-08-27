# ==============================================================================
# ARQUIVO: Send-WhatsApp.ps1
# VERSAO : 2.4
# DESCRICAO: Wrapper Global para envio de WhatsApp. Suporta parametros explicitos
#            ou carregamento de 'whatsapp-config.json' para retrocompatibilidade.
#            Inclui rotina de autolimpeza direcionada de processos zumbis e locks.
#            Suporta modo BATCH (lote), delegando a montagem dos argumentos ao chamador.
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
    [string]$LogFile = "",
    [string]$BatchInputFile = "",  # Obrigatorio quando -Mode BATCH: JSON com itens {phase_key,image_path,caption}
    [string]$BatchResultFile = "" # Obrigatorio quando -Mode BATCH: caminho de saida do resultado por item
)

$ErrorActionPreference = "Stop"

# Este script roda como processo powershell.exe FILHO do run.ps1 da automacao
# (invocado via Invoke-NativeProcess), com sua propria code page de console —
# independente da do pai. No padrao de logging estruturado, WhatsApp-Core.js
# (filho deste processo) emite o envelope JSON em UTF-8 no stdout SEM gravar
# arquivo proprio (o run.ps1 pai e o unico writer do .jsonl); o relay abaixo
# (Write-Host $msg) reemitiria esses bytes na code page OEM sem este ajuste,
# corrompendo toda mensagem acentuada antes mesmo de chegar ao pai.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$LibDir = $PSScriptRoot
$NodeScript = Join-Path $LibDir "WhatsApp-Core.js"
$ProcessModule = Join-Path $LibDir "Lib-Process.psm1"
$ConfigModule = Join-Path $LibDir "Lib-Config.psm1"
Import-Module $ProcessModule -Force
Import-Module $ConfigModule -Force

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

    # Resolve o destino real (contactId/contactPhone do JSON, ou o override via .env em
    # contactIdEnv). Falha cedo se contactIdEnv estiver declarado mas a env var ausente —
    # nesse caso o contactId do config e apenas placeholder, nunca um destino valido.
    $finalPhone = Resolve-WhatsAppTarget -Target $json.target -ConfigPath $resolvedConfig
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
    $authSessionDir = Get-WhatsAppAuthPath
    
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

$isBatchMode = $Mode -eq "BATCH"

# --- Validacao ---
if ([string]::IsNullOrWhiteSpace($finalPhone)) { Write-Error "Telefone/ChatId de destino ausente."; exit 1 }
if ($isBatchMode) {
    if ([string]::IsNullOrWhiteSpace($BatchInputFile)) { Write-Error "BatchInputFile ausente para -Mode BATCH."; exit 1 }
    if ([string]::IsNullOrWhiteSpace($BatchResultFile)) { Write-Error "BatchResultFile ausente para -Mode BATCH."; exit 1 }
} elseif ([string]::IsNullOrWhiteSpace($finalMessage)) {
    Write-Error "Mensagem vazia."
    exit 1
}

# --- Configurar Log padrao se vazio ---
if ([string]::IsNullOrWhiteSpace($LogFile)) {
    $root = Split-Path -Parent $LibDir
    $LogFile = Join-Path $root "Logs\WhatsApp_Global.log"
}

# --- Execucao ---
Write-Host "Acionando Motor de WhatsApp Global..." -ForegroundColor Cyan

$nodeArgs = if ($isBatchMode) {
    @(
        "`"$NodeScript`"",
        "`"$ExecId`"",
        "`"$Mode`"",
        "`"$finalClientId`"",
        "`"$finalPhone`"",
        "`"$BatchInputFile`"",
        "`"$BatchResultFile`"",
        "`"$LogFile`""
    )
} else {
    @(
        "`"$NodeScript`"",
        "`"$ExecId`"",
        "`"$Mode`"",
        "`"$finalClientId`"",
        "`"$finalPhone`"",
        $(if ($finalAttachment) { "`"$finalAttachment`"" } else { '""' }),
        "`"$finalMessage`"",
        "`"$LogFile`""
    )
}

$WorkDir = if ($ConfigPath -and (Test-Path $ConfigPath)) {
    $resolvedPath = Convert-Path $ConfigPath
    $parent = Split-Path -Parent $resolvedPath
    if ([string]::IsNullOrWhiteSpace($parent)) { (Get-Location).Path } else { $parent }
} else {
    (Get-Location).Path
}
# Resolve node_modules: usa WorkDir quando existe, senão fallback para o motor compartilhado em lib/
$candidateNodePath = Join-Path $WorkDir "node_modules"
$fallbackNodePath  = Join-Path $LibDir "node_modules"
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
