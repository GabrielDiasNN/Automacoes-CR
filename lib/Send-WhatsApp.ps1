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
    $finalPhone = $json.target.contactPhone
    $finalMessage = "*$($json.message.caption.title.text)*`n$($json.message.caption.body.text)"
    $finalClientId = $json.auth.clientId

    # Resolve anexo (assume relativo ao config.json se nao for absoluto)
    if ($json.message.sendAttachment -and $json.paths.attachmentPath) {
        $resolvedConfig = Convert-Path $ConfigPath
        $base = Split-Path -Parent $resolvedConfig
        $finalAttachment = Join-Path $base $json.paths.attachmentPath
    }
}

# --- Limpeza de Processos Zumbis e Locks de Sessão (Mitigação de timeouts do Puppeteer) ---
function Clear-StaleWhatsAppProcesses {
    Write-Host "Iniciando verificação de processos zumbis do WhatsApp..." -ForegroundColor Gray
    
    # 1. Encerramento direcionado de processos do Chromium e Node vinculados ao repositório
    try {
        $processes = Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe' OR Name = 'node.exe'" -ErrorAction SilentlyContinue
        foreach ($proc in $processes) {
            $cmd = $proc.CommandLine
            $path = $proc.ExecutablePath
            
            # Filtro seguro: encerra apenas se a execução originar do diretório 'Automacoes'
            if (($cmd -and $cmd -like "*Automacoes*") -or ($path -and $path -like "*Automacoes*")) {
                Write-Host "Detectado processo zumbi ativo: Name=$($proc.Name), Id=$($proc.ProcessId)" -ForegroundColor Yellow
                try {
                    Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
                    Write-Host "Processo $($proc.ProcessId) encerrado com sucesso." -ForegroundColor Green
                } catch [System.Exception] {
                    Write-Warning "Não foi possível encerrar o processo $($proc.ProcessId) (zumbi): $($_.Exception.Message)"
                }
            }
        }
    } catch [System.Exception] {
        Write-Warning "Falha ao consultar processos ativos via WMI/CIM: $($_.Exception.Message)"
    }
    
    # 2. Remoção de arquivos de lock temporários na pasta do perfil da sessão
    $authSessionDir = Join-Path $LibDir ".wwebjs_auth"
    if ($finalClientId) {
        $sessionPath = Join-Path $authSessionDir "session-$finalClientId"
        if (Test-Path $sessionPath) {
            Write-Host "Verificando arquivos de lock temporários no perfil: $sessionPath" -ForegroundColor Gray
            $lockFiles = Get-ChildItem -Path $sessionPath -Recurse -Filter "*lock*" -ErrorAction SilentlyContinue
            $mainLock = Join-Path $sessionPath "Default\Lock"
            if (Test-Path $mainLock) {
                $lockFiles += Get-Item $mainLock -ErrorAction SilentlyContinue
            }
            
            foreach ($file in $lockFiles) {
                if (Test-Path $file.FullName) {
                    try {
                        Remove-Item -Path $file.FullName -Force -ErrorAction Stop
                        Write-Host "Arquivo de lock residual removido: $($file.FullName)" -ForegroundColor Green
                    } catch [System.Exception] {
                        Write-Warning "Não foi possível remover o arquivo de lock $($file.FullName): $($_.Exception.Message)"
                    }
                }
            }
        }
    }
}

# Executar a limpeza antes do início da inicialização do canal
Clear-StaleWhatsAppProcesses

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
$env:NODE_PATH = Join-Path $WorkDir "node_modules"

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
