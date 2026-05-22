[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory = $true)]
    [string]$Name,

    [switch]$WithWhatsApp,
    [switch]$DryRun,
    [string]$BasePath = "",

    # Parametros legados preservados apenas para compatibilidade de chamada.
    [string]$MacroName = "",
    [string]$XlsmName = "",
    [string]$DaysOfWeek = "",
    [string]$Hours = "",
    [string]$Minutes = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ([string]::IsNullOrWhiteSpace($BasePath)) {
    $BasePath = Split-Path -Parent $PSScriptRoot
    if (-not $BasePath) { $BasePath = "." }
}

$resolvedBasePath = (Resolve-Path -LiteralPath $BasePath).Path
$templateDir = Join-Path $resolvedBasePath "_Template"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Step {
    param(
        [string]$Message,
        [string]$Type = "INFO"
    )

    $color = switch ($Type) {
        "ERRO" { "Red" }
        "WARN" { "Yellow" }
        default { "Cyan" }
    }

    $prefix = if ($DryRun) { "[DRY-RUN] " } else { "" }
    Write-Host "$prefix[$Type] $Message" -ForegroundColor $color
}

function Get-AutomationSlug {
    param([string]$AutomationName)

    $normalized = $AutomationName.ToLowerInvariant()
    $normalized = [regex]::Replace($normalized, "[^a-z0-9]+", "-")
    $normalized = $normalized.Trim("-")
    if ([string]::IsNullOrWhiteSpace($normalized)) {
        throw "Nao foi possivel derivar um slug seguro a partir de '$AutomationName'."
    }

    return $normalized
}

function Invoke-SafeWrite {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [string]$FilePath,
        [string]$Content,
        [string]$Operation
    )

    if ($DryRun) {
        Write-Step "Criaria arquivo: $FilePath"
        return
    }

    if (-not $PSCmdlet.ShouldProcess($FilePath, $Operation)) {
        Write-Step "Operacao ignorada por ShouldProcess: $Operation em $FilePath" -Type "WARN"
        return
    }

    $directory = Split-Path -Parent $FilePath
    if ($directory -and -not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Force -Path $directory | Out-Null
    }

    $writer = New-Object System.IO.StreamWriter($FilePath, $false, $utf8NoBom)
    try {
        $writer.Write($Content)
        $writer.Flush()
    }
    finally {
        $writer.Close()
        $writer.Dispose()
    }

    Write-Step "Criado: $FilePath"
}

function Get-TemplateContent {
    param([string]$TemplateName)

    $templatePath = Join-Path $templateDir $TemplateName
    if (-not (Test-Path -LiteralPath $templatePath -PathType Leaf)) {
        throw "Template obrigatorio nao encontrado: $templatePath"
    }

    return Get-Content -LiteralPath $templatePath -Raw
}

function Convert-Template {
    param(
        [string]$Content,
        [hashtable]$Replacements
    )

    $result = $Content
    foreach ($key in $Replacements.Keys) {
        $result = $result.Replace($key, [string]$Replacements[$key])
    }

    return $result
}

Write-Step "Iniciando scaffold da automacao '$Name'"

if (-not (Test-Path -LiteralPath $templateDir -PathType Container)) {
    Write-Step "Diretorio _Template nao encontrado em: $templateDir" -Type "ERRO"
    exit 1
}

$legacyArgsUsed = @()
foreach ($pair in @(
    @{ Name = "MacroName"; Value = $MacroName },
    @{ Name = "XlsmName"; Value = $XlsmName },
    @{ Name = "DaysOfWeek"; Value = $DaysOfWeek },
    @{ Name = "Hours"; Value = $Hours },
    @{ Name = "Minutes"; Value = $Minutes }
)) {
    if (-not [string]::IsNullOrWhiteSpace([string]$pair.Value)) {
        $legacyArgsUsed += $pair.Name
    }
}

if ($legacyArgsUsed.Count -gt 0) {
    Write-Step "Parametros legados ignorados no fluxo atual: $($legacyArgsUsed -join ', ')." -Type "WARN"
}

$automationDir = Join-Path $resolvedBasePath $Name
$logsDir = Join-Path $automationDir "Logs"
$slug = Get-AutomationSlug -AutomationName $Name

if (Test-Path -LiteralPath $automationDir) {
    Write-Step "Diretorio ja existe: $automationDir" -Type "ERRO"
    exit 1
}

$replacements = @{
    "[Nome da Automação]" = $Name
    "TEMPLATE_SLUG" = $slug
}

$readmeContent = Convert-Template -Content (Get-TemplateContent -TemplateName "README.md") -Replacements $replacements
$contextContent = Convert-Template -Content (Get-TemplateContent -TemplateName "CONTEXT.md") -Replacements $replacements
$runContent = Convert-Template -Content (Get-TemplateContent -TemplateName "run.ps1") -Replacements $replacements

$readmeContent += @"

## 🚀 Cadastro Operacional
Esta automação usa o fluxo atual do Hub: primeiro faça o scaffold local, depois registre a automação pelo Dashboard (`/dashboard/`) ou pela API do Orchestrator.

- **Script principal sugerido:** `run.ps1`
- **Logs esperados:** `Logs/`
- **Cadastro no Orchestrator:** informe `script_path` apontando para o `run.ps1` desta pasta
"@

$contextContent += @"

- **Registro no Orchestrator:** esta pasta nasce desacoplada de `config.json` legado; o cadastro operacional deve ser feito pelo Dashboard ou API.
"@

$runBatContent = @"
@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "..\lib\Send-WhatsApp.ps1" -ExecId "MANUAL_BAT" -Mode VISUAL -BaseDir "%~dp0"
exit /b %ERRORLEVEL%
"@

if (-not $DryRun) {
    if ($PSCmdlet.ShouldProcess($automationDir, "Criar diretorio da automacao")) {
        New-Item -ItemType Directory -Force -Path $automationDir | Out-Null
        Write-Step "Diretorio criado: $automationDir"
    }

    if ($PSCmdlet.ShouldProcess($logsDir, "Criar diretorio de logs")) {
        New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
        Write-Step "Diretorio criado: $logsDir"
    }
}
else {
    Write-Step "Criaria diretorio: $automationDir"
    Write-Step "Criaria diretorio: $logsDir"
}

Invoke-SafeWrite -FilePath (Join-Path $automationDir "README.md") -Content $readmeContent -Operation "Gerar README da automacao"
Invoke-SafeWrite -FilePath (Join-Path $automationDir "CONTEXT.md") -Content $contextContent -Operation "Gerar CONTEXT da automacao"
Invoke-SafeWrite -FilePath (Join-Path $automationDir "run.ps1") -Content $runContent -Operation "Gerar run.ps1 da automacao"

if ($WithWhatsApp) {
    Invoke-SafeWrite -FilePath (Join-Path $automationDir "RunWhatsApp.bat") -Content $runBatContent -Operation "Gerar RunWhatsApp.bat"
}

Write-Step "Scaffold concluido para '$Name'."
Write-Step "Registro no Orchestrator deve ser feito separadamente via Dashboard/API." -Type "WARN"

if ($DryRun) {
    Write-Step "Modo DRY-RUN: nenhum arquivo foi criado." -Type "WARN"
}
