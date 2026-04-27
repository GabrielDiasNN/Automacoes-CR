# ==============================================================================
# ARQUIVO: New-Automation.ps1
# VERSAO: 1.0
# DESCRICAO: Scaffolding para novas automacoes. Cria a estrutura de diretorios,
#            Trigger_Automation.vbs configurado e registra a tarefa em config.json.
#
# USO:
#   .\New-Automation.ps1 -Name "Minha Automacao" -MacroName "ExecutarProcesso" `
#       -XlsmName "MinhaAutomacao.xlsm" -Schedule @{daysOfWeek=@(1,2,3,4,5); hours=@(8); minutes=@(0)} `
#       [-WithWhatsApp] [-DryRun]
# ==============================================================================

[CmdletBinding(SupportsShouldProcess)]
param(
    # Nome da automacao (sera o nome do diretorio e da entrada em config.json)
    [Parameter(Mandatory = $true)]
    [string]$Name,

    # Nome da macro VBA a ser chamada pelo Trigger
    [Parameter(Mandatory = $true)]
    [string]$MacroName,

    # Nome do arquivo .xlsm (sem caminho - ficara dentro do diretorio criado)
    [Parameter(Mandatory = $true)]
    [string]$XlsmName,

    # Dias da semana separados por virgula (0=Dom,1=Seg,...,6=Sab). Ex: "1,2,3,4,5"
    [Parameter(Mandatory = $true)]
    [string]$DaysOfWeek,

    # Horas de disparo separadas por virgula (vazio = toda hora). Ex: "7,15"
    [string]$Hours = "",

    # Minutos de disparo separados por virgula. Ex: "0" ou "30"
    [Parameter(Mandatory = $true)]
    [string]$Minutes,

    # Adicionar suporte a WhatsApp (cria flag POST_EXECUTION_BAT no Trigger)
    [switch]$WithWhatsApp,

    # Simular criacao sem gravar arquivos
    [switch]$DryRun,

    # Caminho raiz das automacoes
    [string]$BasePath = "C:\Automacoes"
)

$ErrorActionPreference = "Stop"

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Step {
    param([string]$Msg, [string]$Type = "INFO")
    $color = switch ($Type) { "ERRO" { "Red" } "WARN" { "Yellow" } default { "Cyan" } }
    $prefix = if ($DryRun) { "[DRY-RUN] " } else { "" }
    Write-Host "$prefix[$Type]  $Msg" -ForegroundColor $color
}

function Invoke-SafeWrite {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [string]$FilePath,
        [string]$Content,
        [string]$Operation = "Gravar arquivo"
    )

    if ($DryRun) {
        Write-Step "Criaria arquivo: $FilePath"
        return
    }

    if (-not $PSCmdlet.ShouldProcess($FilePath, $Operation)) {
        Write-Step "Operacao ignorada por ShouldProcess: $Operation em $FilePath" -Type "WARN"
        return
    }

    $dir = Split-Path -Parent $FilePath
    if ($dir -and -not (Test-Path $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    $sw = New-Object System.IO.StreamWriter($FilePath, $false, $Utf8NoBom)
    try { $sw.Write($Content); $sw.Flush() }
    finally { $sw.Close(); $sw.Dispose() }
    Write-Step "Criado: $FilePath"
}

# ============================================================
# VALIDACOES
# ============================================================
Write-Step "Iniciando scaffold para automacao: '$Name'"

if (-not (Test-Path $BasePath)) {
    Write-Step "BasePath nao encontrado: $BasePath" -Type "ERRO"
    exit 1
}

$configPath = Join-Path $BasePath "config.json"
if (-not (Test-Path $configPath)) {
    Write-Step "config.json nao encontrado em: $configPath" -Type "ERRO"
    exit 1
}

# Validacao ja garantida pelos parametros obrigatorios

# Diretorio destino
$automDir = Join-Path $BasePath $Name
$logsDir = Join-Path $automDir "Logs"
$triggerPath = Join-Path $automDir "Trigger_Automation.vbs"
$xlsmFullPath = Join-Path $automDir $XlsmName
$execLogPath = Join-Path $logsDir "Execution.log"
$vbaLogPath = Join-Path $logsDir "VBA_Internal.log"

if (Test-Path $automDir) {
    Write-Step "Diretorio ja existe: $automDir" -Type "WARN"
    Write-Step "Use -DryRun para simular sem criar. Abortando para nao sobrescrever." -Type "ERRO"
    exit 1
}

# ============================================================
# CRIAR DIRETORIOS
# ============================================================
if (-not $DryRun) {
    if ($PSCmdlet.ShouldProcess($automDir, "Criar diretorio da automacao")) {
        New-Item -ItemType Directory -Force -Path $automDir | Out-Null
        Write-Step "Diretorio criado: $automDir"
    }
    else {
        Write-Step "Criacao ignorada por ShouldProcess: $automDir" -Type "WARN"
    }

    if ($PSCmdlet.ShouldProcess($logsDir, "Criar diretorio de logs")) {
        New-Item -ItemType Directory -Force -Path $logsDir  | Out-Null
        Write-Step "Diretorio criado: $logsDir"
    }
    else {
        Write-Step "Criacao ignorada por ShouldProcess: $logsDir" -Type "WARN"
    }
}
else {
    Write-Step "Criaria diretorio: $automDir"
    Write-Step "Criaria diretorio: $logsDir"
}

# ============================================================
# TRIGGER_AUTOMATION.VBS
# ============================================================
$postBatLine = if ($WithWhatsApp) {
    "POST_EXECUTION_BAT  = `"$automDir\RunWhatsApp.bat`""
}
else {
    "POST_EXECUTION_BAT  = `"`" ' Nao configurado"
}

$vbsContent = @"
Option Explicit

' =============================================================================
' Trigger_Automation.vbs (GERADO POR New-Automation.ps1)
' Modulo: $Name
' =============================================================================

Dim excelApp, wb, fso, wsh
Dim scriptStart, logPath, execId

Dim excelPath, macroName
excelPath = "$xlsmFullPath"
macroName = "$MacroName"
logPath   = "$execLogPath"

Dim USE_TIMEOUT_MONITOR, vbaLogPath, maxTimeoutSeconds
USE_TIMEOUT_MONITOR = True
vbaLogPath          = "$vbaLogPath"
maxTimeoutSeconds   = 300

Dim POST_EXECUTION_BAT
$postBatLine

"@

# Copiar o restante do template VBS (logica universal)
$templatePath = Join-Path $BasePath "_Template\Trigger_Automation.vbs"
if (Test-Path $templatePath) {
    $template = Get-Content $templatePath -Raw -Encoding UTF8
    # Localizar onde terminam as configuracoes no template (apos a linha ' ===...===)
    $configEndMarker = "' ============================================="
    $markerIdx = $template.IndexOf($configEndMarker)
    if ($markerIdx -ge 0) {
        $templateBody = $template.Substring($markerIdx + $configEndMarker.Length).TrimStart("`r", "`n")
        $vbsContent += "`r`n$configEndMarker`r`n$templateBody"
    }
    else {
        Write-Step "Marcador de fim de config nao encontrado no template. VBS gerado sem corpo universal." -Type "WARN"
    }
}
else {
    Write-Step "Template VBS nao encontrado em: $templatePath. VBS gerado apenas com cabecalho." -Type "WARN"
}

Invoke-SafeWrite -FilePath $triggerPath -Content $vbsContent -Operation "Gerar Trigger_Automation.vbs"

# ============================================================
# RUNWHATSAPP.BAT (se -WithWhatsApp)
# ============================================================
if ($WithWhatsApp) {
    $batContent = "@echo off`r`n:: Shim WhatsApp - delega para lib\Send-WhatsApp.ps1`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"$BasePath\lib\Send-WhatsApp.ps1`" -ExecId `"%~1`" -Mode `"%~2`" -BaseDir `"$automDir`"`r`nexit /b %ERRORLEVEL%`r`n"
    Invoke-SafeWrite -FilePath (Join-Path $automDir "RunWhatsApp.bat") -Content $batContent -Operation "Gerar RunWhatsApp.bat"
}

# ============================================================
# REGISTRAR EM CONFIG.JSON
# ============================================================
$scheduleObj = [ordered]@{
    daysOfWeek = @($DaysOfWeek.Split(',') | ForEach-Object { [int]$_.Trim() })
    hours      = @(if ([string]::IsNullOrWhiteSpace($Hours)) { @() } else { $Hours.Split(',') | ForEach-Object { [int]$_.Trim() } })
    minutes    = @($Minutes.Split(',')    | ForEach-Object { [int]$_.Trim() })
}

$newTask = [ordered]@{
    name              = $Name
    scriptPath        = $triggerPath
    enabled           = $true
    preventOverlap    = $true
    waitForExit       = $false
    maxRuntimeMinutes = 30
    schedule          = $scheduleObj
}

if ($DryRun) {
    Write-Step "Adicionaria ao config.json: $(($newTask | ConvertTo-Json -Compress))"
}
else {
    $configRaw = Get-Content $configPath -Raw -Encoding UTF8
    $config = $configRaw | ConvertFrom-Json

    # Verificar se ja existe tarefa com mesmo nome
    $exists = @($config.tasks | Where-Object { $_.name -eq $Name })
    if ($exists.Count -gt 0) {
        Write-Step "Tarefa '$Name' ja existe em config.json. Nenhuma alteracao feita no config." -Type "WARN"
    }
    else {
        # ConvertFrom-Json retorna array fixo - convertemos para lista mutavel
        $tasksList = [System.Collections.Generic.List[object]]($config.tasks)
        $tasksList.Add(($newTask | ConvertTo-Json -Depth 5 | ConvertFrom-Json))
        $config.tasks = $tasksList.ToArray()

        if ($PSCmdlet.ShouldProcess($configPath, "Atualizar config.json com nova tarefa")) {
            $updatedJson = $config | ConvertTo-Json -Depth 10
            $sw = New-Object System.IO.StreamWriter($configPath, $false, $Utf8NoBom)
            try { $sw.Write($updatedJson); $sw.Flush() }
            finally { $sw.Close(); $sw.Dispose() }

            Write-Step "Tarefa '$Name' adicionada ao config.json."
        }
        else {
            Write-Step "Atualizacao ignorada por ShouldProcess: $configPath" -Type "WARN"
        }
    }
}

Write-Step "Scaffold concluido para '$Name'."
if ($DryRun) { Write-Step "Modo DRY-RUN: nenhum arquivo foi criado." -Type "WARN" }
