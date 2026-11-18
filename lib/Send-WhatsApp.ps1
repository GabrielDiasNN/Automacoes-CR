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
    [string]$BatchResultFile = "", # Obrigatorio quando -Mode BATCH: caminho de saida do resultado por item
    [int]$SessionLockTimeoutMs = 180000
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
Import-Module (Join-Path $LibDir "Lib-WhatsAppBatch.psm1") -Force

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

    # Distincao de exit codes: 22 = adiado por lock/cooldown (comportamento normal, o chamador
    # reavalia no proximo ciclo); 23 = desabilitado na configuracao (nada enviado, falha de config
    # que o chamador deve tratar como falha, nunca como sucesso silencioso).
    if (-not (Test-WhatsAppConfigEnabled -Config $json)) {
        if ($Mode -eq "BATCH" -and -not [string]::IsNullOrWhiteSpace($BatchResultFile)) {
            Write-Host "Envio WhatsApp desabilitado na configuracao ($resolvedConfig) em modo BATCH (BatchResultFile='$BatchResultFile' nao gravado com success: true). Encerrando com exit 23." -ForegroundColor Yellow
        }
        else {
            Write-Host "Envio WhatsApp desabilitado na configuracao ($resolvedConfig). Encerrando com exit 23 sem enviar." -ForegroundColor Yellow
        }
        exit 23
    }

    # Resolve o destino real (contactId/contactPhone do JSON, ou o override via .env em
    # contactIdEnv). Falha cedo se contactIdEnv estiver declarado mas a env var ausente —
    # nesse caso o contactId do config e apenas placeholder, nunca um destino valido.
    $finalPhone = Resolve-WhatsAppTarget -Target $json.target -ConfigPath $resolvedConfig
    $finalClientId = $json.auth.clientId

    if ($Mode -ne "BATCH") {
        # Suporte a mensagem via arquivo externo (textFile) com fallback para caption inline
        if ($json.message.textFile) {
            $txtPath = Join-Path $base $json.message.textFile
            $finalMessage = Get-Content $txtPath -Raw -Encoding UTF8
        }
        else {
            $finalMessage = "*$($json.message.caption.title.text)*`n$($json.message.caption.body.text)"
        }

        # Resolve anexo (assume relativo ao config.json se nao for absoluto)
        if ($json.message.sendAttachment -and $json.paths.attachmentPath) {
            $finalAttachment = Join-Path $base $json.paths.attachmentPath
        }
    }
}

# --- Limpeza de Locks de Sessão e Processos Zumbis (Mitigação de travamentos de Puppeteer) ---
function Clear-StaleWhatsAppLocksAndProcesses {
    $now = [DateTime]::Now
    $authSessionDir = Get-WhatsAppAuthPath

    # 1. Limpeza direcionada de processos zumbis do Chromium e Node vinculados ao repositório.
    # O daemon WhatsApp (opt-in) e' processo de vida longa e TODA a sua arvore de descendentes
    # (chrome.exe do Puppeteer) fica protegida: a selecao e' feita por Select-WhatsAppStaleProcessIds.
    try {
        $todosProcessos = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
        $pidsDaemon = @(Get-WhatsAppDaemonProcess | ForEach-Object { [int]$_.ProcessId })
        $pidsEncerrar = @(Select-WhatsAppStaleProcessIds -Processes $todosProcessos -DaemonPids $pidsDaemon -Now $now)
        foreach ($idZumbi in $pidsEncerrar) {
            Stop-Process -Id $idZumbi -Force -ErrorAction SilentlyContinue
        }
    }
    catch [System.Exception] {}

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
                    }
                    catch [System.Exception] {}
                }
            }
        }
    }
}

# --- Daemon WhatsApp (opt-in, somente BATCH) ---
# Get-WhatsAppDaemonProcess, Get-WhatsAppDaemonHealth, Get-WhatsAppDaemonRoute, Invoke-WhatsAppDaemonBatch e Invoke-WhatsAppDaemonSend vivem em
# Lib-WhatsAppBatch.psm1 (importado acima) para serem testaveis; este script apenas as usa.

$isBatchMode = $Mode -eq "BATCH"

# --- Validacao ---
if ([string]::IsNullOrWhiteSpace($finalPhone)) { Write-Error "Telefone/ChatId de destino ausente."; exit 1 }
if ($isBatchMode) {
    if ([string]::IsNullOrWhiteSpace($BatchInputFile)) { Write-Error "BatchInputFile ausente para -Mode BATCH."; exit 1 }
    if ([string]::IsNullOrWhiteSpace($BatchResultFile)) { Write-Error "BatchResultFile ausente para -Mode BATCH."; exit 1 }
}
elseif ([string]::IsNullOrWhiteSpace($finalMessage)) {
    Write-Error "Mensagem vazia."
    exit 1
}

# --- Configurar Log padrao se vazio ---
if ([string]::IsNullOrWhiteSpace($LogFile)) {
    $root = Split-Path -Parent $LibDir
    $LogFile = Join-Path $root "Logs\WhatsApp_Global.log"
}

$lockKeySource = if ([string]::IsNullOrWhiteSpace($finalClientId)) { "default" } else { $finalClientId }
$safeClientId = $lockKeySource -replace '[^A-Za-z0-9_.-]', '_'
$sessionMutexName = "Global\AutomationHub_WA_$safeClientId"
$sessionMutex = New-Object System.Threading.Mutex($false, $sessionMutexName)
$sessionMutexOwned = $false
$lockTimedOut = $false
$result = $null

try {
    try {
        $sessionMutexOwned = $sessionMutex.WaitOne($SessionLockTimeoutMs)
    }
    catch [System.Threading.AbandonedMutexException] {
        Write-Host "Mutex de sessao WhatsApp anterior foi abandonado ($sessionMutexName). Reciclando lock..." -ForegroundColor Yellow
        $sessionMutexOwned = $true
    }

    if (-not $sessionMutexOwned) {
        Write-Host "Outra automacao esta usando a sessao WhatsApp '$finalClientId' (Mutex: $sessionMutexName, timeout=${SessionLockTimeoutMs}ms). Adiando envio com exit 22 sem encerrar processos." -ForegroundColor Yellow
        $lockTimedOut = $true
    }
    else {
        # Rota do daemon WhatsApp: decidida somente apos adquirir o mutex da sessao.
        # Daemon vivo no MESMO perfil segura a sessao: envio pelo daemon (ou adiamento com 22). Sem daemon,
        # ou com daemon de outro perfil, segue o fluxo atual ('spawn'). WHATSAPP_DAEMON_ENABLED nao entra
        # aqui: governa apenas a subida do daemon (Start-WhatsAppDaemon.ps1).
        $daemonPort = "8765"
        $portaLida = Get-EnvFileValue -Key "WHATSAPP_DAEMON_PORT"
        if (-not [string]::IsNullOrWhiteSpace($portaLida)) { $daemonPort = $portaLida }
        $daemonToken = Get-EnvFileValue -Key "WHATSAPP_DAEMON_TOKEN"
        $daemonVivo = (@(Get-WhatsAppDaemonProcess)).Count -gt 0
        $saudeDaemon = [pscustomobject]@{ State = ""; ClientId = "" }
        if ($daemonVivo) {
            $saudeDaemon = Get-WhatsAppDaemonHealth -Port $daemonPort -Token $daemonToken
        }
        $daemonRoute = Get-WhatsAppDaemonRoute -DaemonRunning $daemonVivo -ClientId $finalClientId -HealthState $saudeDaemon.State -HealthClientId $saudeDaemon.ClientId

        # VISUAL e LIST_GROUPS abrem node proprio no perfil: com daemon vivo no mesmo perfil, recusam (exit 22).
        if (($Mode -eq "VISUAL" -or $Mode -eq "LIST_GROUPS") -and $daemonRoute -ne "spawn") {
            Write-Host "Daemon WhatsApp ativo no perfil '$finalClientId': pare o daemon antes de usar o modo $Mode. Adiando com exit 22 sem subir node." -ForegroundColor Yellow
            $lockTimedOut = $true
            $daemonRoute = "bloqueado"
        }

        if ($daemonRoute -eq "defer") {
            # 'unauthorized' = health respondeu 401: o daemon esta vivo e segura o perfil, mas o token nao confere.
            # Nunca subir outro node aqui (conflitaria com o perfil do daemon); o token nao e' impresso.
            if ($saudeDaemon.State -eq "unauthorized") {
                Write-Host "Daemon WhatsApp recusou o health (HTTP 401): token do daemon nao confere: confira WHATSAPP_DAEMON_TOKEN no .env. Adiando envio com exit 22 sem subir node." -ForegroundColor Red
            }
            else {
                Write-Host "Daemon WhatsApp ativo mas nao pronto (estado: '$($saudeDaemon.State)'). Adiando envio com exit 22 sem subir node." -ForegroundColor Yellow
            }
            $lockTimedOut = $true
        }

        if ($daemonRoute -eq "daemon") {
            Write-Host "Enviando pelo daemon WhatsApp (127.0.0.1:$daemonPort, perfil '$finalClientId')..." -ForegroundColor Cyan
            if ($isBatchMode) {
                $codigoDaemon = Invoke-WhatsAppDaemonBatch -Port $daemonPort -Token $daemonToken -ExecId $ExecId -ClientId $finalClientId -ChatTarget $finalPhone -BatchInputFile $BatchInputFile -BatchResultFile $BatchResultFile
            }
            else {
                # Mesmo contato, mesma mensagem final e mesmo anexo resolvido do fluxo spawn (HUB_WA_CAPTION_FILE).
                # Anexo ausente cai para texto, como o core faz no spawn.
                $anexoDaemon = ""
                if (-not [string]::IsNullOrWhiteSpace($finalAttachment)) {
                    if (Test-Path -LiteralPath $finalAttachment) { $anexoDaemon = $finalAttachment }
                    else { Write-Host "Anexo ausente ou nao encontrado ($finalAttachment). Enviando apenas a mensagem de texto." -ForegroundColor Yellow }
                }
                $codigoDaemon = Invoke-WhatsAppDaemonSend -Port $daemonPort -Token $daemonToken -ExecId $ExecId -ClientId $finalClientId -ChatTarget $finalPhone -Caption $finalMessage -AttachmentPath $anexoDaemon
            }
            $result = [pscustomobject]@{ ExitCode = $codigoDaemon }
        }

        if ($daemonRoute -eq "spawn") {
        # Executar a limpeza antes do inicio da inicializacao do canal (somente apos adquirir o mutex da sessao)
        Clear-StaleWhatsAppLocksAndProcesses

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
        }
        else {
            @(
                "`"$NodeScript`"",
                "`"$ExecId`"",
                "`"$Mode`"",
                "`"$finalClientId`"",
                "`"$finalPhone`"",
                $(if ($finalAttachment) { "`"$finalAttachment`"" } else { '""' }),
                '""',
                "`"$LogFile`""
            )
        }

        $WorkDir = if ($ConfigPath -and (Test-Path $ConfigPath)) {
            $resolvedPath = Convert-Path $ConfigPath
            $parent = Split-Path -Parent $resolvedPath
            if ([string]::IsNullOrWhiteSpace($parent)) { (Get-Location).Path } else { $parent }
        }
        else {
            (Get-Location).Path
        }
        # Resolve node_modules: usa WorkDir quando existe, senão fallback para o motor compartilhado em lib/
        $candidateNodePath = Join-Path $WorkDir "node_modules"
        $fallbackNodePath = Join-Path $LibDir "node_modules"
        $env:NODE_PATH = if (Test-Path $candidateNodePath) { $candidateNodePath } else { $fallbackNodePath }

        # Legenda em modo AUTO vai via arquivo UTF-8 temporario (HUB_WA_CAPTION_FILE) para
        # evitar truncamento/corrupcao de aspas, quebras de linha e limite CreateProcess no argv.
        $captionTempFile = $null
        $prevCaptionEnv = $env:HUB_WA_CAPTION_FILE
        $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
        try {
            if (-not $isBatchMode) {
                $safeExec = $ExecId -replace '[^A-Za-z0-9_.-]', '_'
                $captionTempFile = Join-Path ([System.IO.Path]::GetTempPath()) ("wa_caption_{0}_{1}.txt" -f $safeExec, [guid]::NewGuid().ToString("N"))
                [System.IO.File]::WriteAllText($captionTempFile, $finalMessage, $utf8NoBom)
                $env:HUB_WA_CAPTION_FILE = $captionTempFile
            }
            else {
                Remove-Item Env:\HUB_WA_CAPTION_FILE -ErrorAction SilentlyContinue
            }

            $result = Invoke-NativeProcess -FilePath $NodeExe -Arguments ($nodeArgs -join " ") -WorkingDirectory $WorkDir -LogAction {
                param($msg, $lvl)
                if ($lvl -eq "WARN") {
                    Write-Host $msg -ForegroundColor Yellow
                }
                else {
                    Write-Host $msg
                }
            }
        }
        finally {
            if ($null -eq $prevCaptionEnv) {
                Remove-Item Env:\HUB_WA_CAPTION_FILE -ErrorAction SilentlyContinue
            }
            else {
                $env:HUB_WA_CAPTION_FILE = $prevCaptionEnv
            }
            if ($captionTempFile -and (Test-Path -LiteralPath $captionTempFile)) {
                Remove-Item -LiteralPath $captionTempFile -Force -ErrorAction SilentlyContinue
            }
        }
        }
    }
}
finally {
    if ($sessionMutexOwned) {
        try { $sessionMutex.ReleaseMutex() } catch [System.ApplicationException] {}
    }
    if ($null -ne $sessionMutex) {
        $sessionMutex.Dispose()
    }
}

if ($lockTimedOut) {
    exit 22
}

if ($result.ExitCode -eq 0) {
    Write-Host "[OK] WhatsApp enviado com sucesso." -ForegroundColor Green
}
else {
    Write-Host "[FAIL] Falha no envio do WhatsApp (ExitCode: $($result.ExitCode)). Verifique os logs." -ForegroundColor Red
    exit $result.ExitCode
}
