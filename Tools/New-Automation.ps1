[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory = $true)]
    [string]$Name,

    [switch]$WithWhatsApp,
    [switch]$WithOracle,
    [switch]$WithoutEmail,
    [switch]$DryRun,
    [string]$BasePath = "",
    [string]$OwnerArea = "Owner de negócio pendente",
    [ValidateSet("critical", "high", "medium", "low")]
    [string]$Criticality = "medium",
    [string]$QueueGroup = "",
    [ValidateRange(1, 10080)]
    [int]$SlaMinutes = 360,
    [ValidateRange(1, 480)]
    [int]$MaxRuntimeMinutes = 30,
    [ValidateRange(0, 10)]
    [int]$MaxRetries = 0,
    [ValidateSet("powershell", "python", "node")]
    [string]$Runtime = "powershell",
    [string]$SupportContact = "Definir suporte técnico",

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
$runbookTemplatePath = Join-Path $resolvedBasePath "docs\templates\automation-runbook-template.md"
$smokeTestTemplatePath = Join-Path $resolvedBasePath "docs\templates\automation-smoke-test-template.py"
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
$runbookDir = Join-Path $resolvedBasePath "docs\runbooks"
$orchestratorTestsDir = Join-Path $resolvedBasePath "Orchestrator\tests"
$slug = Get-AutomationSlug -AutomationName $Name
$testId = $slug.Replace("-", "_")
$runbookPath = Join-Path $runbookDir "$slug-runbook.md"
$smokeTestPath = Join-Path $orchestratorTestsDir "test_$slug.py"
$effectiveQueueGroup = if ([string]::IsNullOrWhiteSpace($QueueGroup)) { $slug.Replace("-", "_") } else { $QueueGroup.Trim() }
$channels = New-Object System.Collections.Generic.List[string]
if (-not $WithoutEmail) { $channels.Add("email") }
if ($WithWhatsApp) { $channels.Add("whatsapp") }
$channelsJson = if ($channels.Count -gt 0) {
    ($channels | ConvertTo-Json -Compress)
} else {
    "[]"
}
$dependencyOracle = if ($WithOracle) { "true" } else { "false" }
$dependencyOutlook = if (-not $WithoutEmail) { "true" } else { "false" }
$dependencyWhatsApp = if ($WithWhatsApp) { "true" } else { "false" }

if (Test-Path -LiteralPath $automationDir) {
    Write-Step "Diretorio ja existe: $automationDir" -Type "ERRO"
    exit 1
}

$replacements = @{
    "[Nome da Automação]" = $Name
    "TEMPLATE_SLUG" = $slug
    "TEMPLATE_TEST_ID" = $testId
    "TEMPLATE_CRITICALITY" = $Criticality
    "TEMPLATE_OWNER_AREA" = $OwnerArea
    "TEMPLATE_RUNTIME" = $Runtime
    "TEMPLATE_QUEUE_GROUP" = $effectiveQueueGroup
}

$readmeContent = Convert-Template -Content (Get-TemplateContent -TemplateName "README.md") -Replacements $replacements
$contextContent = Convert-Template -Content (Get-TemplateContent -TemplateName "CONTEXT.md") -Replacements $replacements
$runContent = Convert-Template -Content (Get-TemplateContent -TemplateName "run.ps1") -Replacements $replacements
$manifestContent = Convert-Template -Content (Get-TemplateContent -TemplateName "automation.manifest.json") -Replacements $replacements
$smokeTestContent = ""

$manifestContent = $manifestContent.Replace('"__TEMPLATE_SLA_MINUTES__"', [string]$SlaMinutes)
$manifestContent = $manifestContent.Replace('"__TEMPLATE_CHANNELS_JSON__"', $channelsJson)
$manifestContent = $manifestContent.Replace('"__TEMPLATE_MAX_RUNTIME__"', [string]$MaxRuntimeMinutes)
$manifestContent = $manifestContent.Replace('"__TEMPLATE_MAX_RETRIES__"', [string]$MaxRetries)
$manifestContent = $manifestContent.Replace('"__TEMPLATE_DEP_ORACLE__"', $dependencyOracle)
$manifestContent = $manifestContent.Replace('"__TEMPLATE_DEP_OUTLOOK__"', $dependencyOutlook)
$manifestContent = $manifestContent.Replace('"__TEMPLATE_DEP_WHATSAPP__"', $dependencyWhatsApp)

if (-not (Test-Path -LiteralPath $runbookTemplatePath -PathType Leaf)) {
    Write-Step "Template de runbook nao encontrado em: $runbookTemplatePath" -Type "ERRO"
    exit 1
}

if (-not (Test-Path -LiteralPath $smokeTestTemplatePath -PathType Leaf)) {
    Write-Step "Template de smoke test nao encontrado em: $smokeTestTemplatePath" -Type "ERRO"
    exit 1
}

$runbookContent = Get-Content -LiteralPath $runbookTemplatePath -Raw
$smokeTestContent = Get-Content -LiteralPath $smokeTestTemplatePath -Raw
$runbookContent = $runbookContent.Replace("[Nome da Automação]", $Name)
$runbookContent = $runbookContent.Replace("[Caminho do Diretório, ex: Receitas Bloqueadas]", $Name)
$runbookContent = $runbookContent.Replace("[CRÍTICA / ALTA / MÉDIA / BAIXA]", $Criticality.ToUpperInvariant())
$runbookContent = $runbookContent.Replace("[Tempo de recuperação tolerado, ex: 2 horas]", "$SlaMinutes minutos")
$runbookContent = $runbookContent.Replace("[Horários cron, ex: Seg-Sex às 07:30, 10:00, 14:00]", "Definir no cadastro operacional")
$runbookContent = $runbookContent.Replace("[Nome / Setor, ex: Laboratório de Receitas / PCP]", $OwnerArea)
$runbookContent = $runbookContent.Replace("[Contato TI, ex: suporte.automacoes@empresa.com]", $SupportContact)
$runbookContent = $runbookContent.Replace("<CAMINHO_AUTOMACAO>", "$BasePath\$Name")
$runbookContent = $runbookContent.Replace("[Versão]", "0.1.0")
$smokeTestContent = Convert-Template -Content $smokeTestContent -Replacements $replacements

$readmeContent += @"

## 🚀 Cadastro Operacional
Esta automação usa o fluxo atual do Hub: primeiro faça o scaffold local, depois registre a automação pelo Dashboard (`/dashboard/`) ou pela API do Orchestrator.

- **Script principal sugerido:** `run.ps1`
- **Logs esperados:** `Logs/`
- **Manifesto canônico:** `automation.manifest.json`
- **Runbook inicial:** `docs/runbooks/$slug-runbook.md`
- **Smoke test inicial:** `Orchestrator/tests/test_$slug.py`
- **Queue group inicial:** `$effectiveQueueGroup`
- **Cadastro no Orchestrator:** informe `script_path` apontando para o `run.ps1` desta pasta
"@

$contextContent += @"

- **Registro no Orchestrator:** esta pasta nasce desacoplada de `config.json` legado; o cadastro operacional deve ser feito pelo Dashboard ou API.
- **Catálogo governado:** preencha `automation.manifest.json` antes de promover a automação para operação recorrente.
- **Smoke inicial:** o scaffold já cria `Orchestrator/tests/test_$slug.py` como prova mínima de existência dos artefatos obrigatórios.
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
    Write-Step "Criaria diretorio: $runbookDir"
    Write-Step "Criaria diretorio: $orchestratorTestsDir"
}

Invoke-SafeWrite -FilePath (Join-Path $automationDir "README.md") -Content $readmeContent -Operation "Gerar README da automacao"
Invoke-SafeWrite -FilePath (Join-Path $automationDir "CONTEXT.md") -Content $contextContent -Operation "Gerar CONTEXT da automacao"
Invoke-SafeWrite -FilePath (Join-Path $automationDir "run.ps1") -Content $runContent -Operation "Gerar run.ps1 da automacao"
Invoke-SafeWrite -FilePath (Join-Path $automationDir "automation.manifest.json") -Content $manifestContent -Operation "Gerar automation.manifest.json"
Invoke-SafeWrite -FilePath $runbookPath -Content $runbookContent -Operation "Gerar runbook operacional"
Invoke-SafeWrite -FilePath $smokeTestPath -Content $smokeTestContent -Operation "Gerar smoke test inicial"

if ($WithWhatsApp) {
    Invoke-SafeWrite -FilePath (Join-Path $automationDir "RunWhatsApp.bat") -Content $runBatContent -Operation "Gerar RunWhatsApp.bat"
}

Write-Step "Scaffold concluido para '$Name'."
Write-Step "Manifesto inicial: criticidade=$Criticality, queue_group=$effectiveQueueGroup, smoke_test=test_$slug.py"
Write-Step "Registro no Orchestrator deve ser feito separadamente via Dashboard/API." -Type "WARN"

if ($DryRun) {
    Write-Step "Modo DRY-RUN: nenhum arquivo foi criado." -Type "WARN"
}
