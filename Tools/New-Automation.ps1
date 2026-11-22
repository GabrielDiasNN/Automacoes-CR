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
    [ValidateSet("powershell", "python", "node", "promovida")]
    [string]$Runtime = "python",
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
$utf8Bom = New-Object System.Text.UTF8Encoding($true)

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

    $encoding = if ($FilePath -match '\.(ps1|psm1)$') { $utf8Bom } else { $utf8NoBom }
    $writer = New-Object System.IO.StreamWriter($FilePath, $false, $encoding)
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

    return Get-Content -LiteralPath $templatePath -Raw -Encoding UTF8
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

$slug = Get-AutomationSlug -AutomationName $Name
$testId = $slug.Replace("-", "_")
$isPromovida = ($Runtime -eq "promovida")
$automationRelDir = if ($isPromovida) { "Consultas Promovidas\$slug" } else { $Name }
$automationRelPosix = $automationRelDir.Replace("\", "/")
$automationDir = Join-Path $resolvedBasePath $automationRelDir
$logsDir = Join-Path $automationDir "Logs"
$runbookDir = Join-Path $resolvedBasePath "docs\runbooks"
$orchestratorTestsDir = Join-Path $resolvedBasePath "Orchestrator\tests"
$runbookPath = Join-Path $runbookDir "$slug-runbook.md"
$smokeTestPath = Join-Path $orchestratorTestsDir "test_$slug.py"
$effectiveQueueGroup = if ($isPromovida -and [string]::IsNullOrWhiteSpace($QueueGroup)) {
    "oracle"
} elseif ([string]::IsNullOrWhiteSpace($QueueGroup)) {
    $slug.Replace("-", "_")
} else {
    $QueueGroup.Trim()
}
$channels = New-Object System.Collections.Generic.List[string]
if ($isPromovida) { $channels.Add("dashboard") }
if (-not $WithoutEmail -and -not $isPromovida) { $channels.Add("email") }
if ($WithWhatsApp) { $channels.Add("whatsapp") }
$channelsJson = if ($channels.Count -gt 0) {
    ($channels | ConvertTo-Json -Compress)
} else {
    "[]"
}
$dependencyOracle = if ($WithOracle -or $isPromovida) { "true" } else { "false" }
$dependencyOutlook = if (-not $WithoutEmail -and -not $isPromovida) { "true" } else { "false" }
$dependencyWhatsApp = if ($WithWhatsApp) { "true" } else { "false" }

if (Test-Path -LiteralPath $automationDir) {
    Write-Step "Diretorio ja existe: $automationDir" -Type "ERRO"
    exit 1
}

$runnerFileName = if ($isPromovida) { "promocao.json" } else { "run_$testId.py" }

$replacements = @{
    "[Nome da Automação]" = $Name
    "TEMPLATE_SLUG" = $slug
    "TEMPLATE_TEST_ID" = $testId
    "TEMPLATE_RUNNER" = $runnerFileName
    "TEMPLATE_CRITICALITY" = $Criticality
    "TEMPLATE_OWNER_AREA" = $OwnerArea
    "TEMPLATE_RUNTIME" = $Runtime
    "TEMPLATE_QUEUE_GROUP" = $effectiveQueueGroup
}

$readmeContent = Convert-Template -Content (Get-TemplateContent -TemplateName "README.md") -Replacements $replacements
$contextContent = Convert-Template -Content (Get-TemplateContent -TemplateName "CONTEXT.md") -Replacements $replacements
$runContent = if ($isPromovida) {
@"
[CmdletBinding()]
param(
    [string]`$ExecId = "",
    [switch]`$DryRun
)

`$ErrorActionPreference = "Stop"
`$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

`$ScriptDir = `$PSScriptRoot
if (-not `$ScriptDir) { `$ScriptDir = Split-Path -Parent `$MyInvocation.MyCommand.Path }

`$projectRoot = Split-Path -Parent (Split-Path -Parent `$ScriptDir)
`$libProcess  = Join-Path `$projectRoot "lib\Lib-Process.psm1"
`$configPath  = Join-Path `$ScriptDir "promocao.json"

Import-Module `$libProcess -Force

`$pythonExe = Resolve-HubPythonExe -ProjectRoot `$projectRoot
if (-not (Test-Path -LiteralPath `$pythonExe -PathType Leaf)) {
    Write-Host "[ERRO] Python do projeto nao encontrado em '`$pythonExe'."
    exit 9
}

`$env:PYTHONUTF8 = "1"
`$env:PYTHONIOENCODING = "utf-8"
`$env:PYTHONPATH = Join-Path `$projectRoot "lib\python"

`$runnerArgs = @("-m", "promovidas.run_promocao", "--config", `$configPath)
if (-not [string]::IsNullOrWhiteSpace(`$ExecId)) { `$runnerArgs += `$ExecId }
if (`$DryRun) { `$runnerArgs += "--dry-run" }

`$exitCode = Invoke-HubPythonRunner -PythonExe `$pythonExe -Arguments `$runnerArgs -WorkingDirectory `$ScriptDir
exit `$exitCode
"@
} else {
    Convert-Template -Content (Get-TemplateContent -TemplateName "run.ps1") -Replacements $replacements
}
$runnerContent = if ($isPromovida) {
@"
{
  "slug": "$slug",
  "nome": "$Name",
  "consulta": "consulta.sql",
  "modo": "sombra",
  "chave": ["NUMERO_OB"],
  "destinos": $($channelsJson),
  "painel": {
    "titulo": "$Name",
    "kpis": ["count"],
    "colunas": []
  }
}
"@
} else {
    Convert-Template -Content (Get-TemplateContent -TemplateName "run_template.py") -Replacements $replacements
}
$manifestContent = Convert-Template -Content (Get-TemplateContent -TemplateName "automation.manifest.json") -Replacements $replacements
if ($isPromovida) {
    $manifestContent = $manifestContent.Replace("$Name/CONTEXT.md", "$automationRelPosix/CONTEXT.md")
    $manifestContent = $manifestContent.Replace("$Name/README.md", "$automationRelPosix/README.md")
    $manifestContent = $manifestContent.Replace("./$Name/run.ps1", "./$automationRelPosix/run.ps1")
}
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

$runbookContent = Get-Content -LiteralPath $runbookTemplatePath -Raw -Encoding UTF8
$smokeTestContent = Get-Content -LiteralPath $smokeTestTemplatePath -Raw -Encoding UTF8
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
if ($isPromovida) {
    $smokeTestContent = $smokeTestContent.Replace("root / `"$Name`"", "root / `"Consultas Promovidas`" / `"$slug`"")
}

$readmeContent += @"

## 🚀 Cadastro Operacional
Esta automação usa o fluxo atual do Hub: primeiro faça o scaffold local, depois registre a automação pelo Dashboard (`/dashboard/`) ou pela API do Orchestrator.

- **Entrypoint (shim):** `run.ps1` resolve o Python do projeto, chama o runner e repassa o exit code
- **Runner Python:** `$runnerFileName` (pre-flight, lock, etapas e entrega sobre `lib/python/hub_runner.py`)
- **Logs esperados:** `Logs/`
- **Manifesto canônico:** `automation.manifest.json`
- **Runbook inicial:** `docs/runbooks/$slug-runbook.md`
- **Smoke test inicial:** `Orchestrator/tests/test_$slug.py`
- **Queue group inicial:** `$effectiveQueueGroup`
- **Cadastro no Orchestrator:** informe `script_path` apontando para o `run.ps1` desta pasta
"@

$contextContent += @"

- **Runner:** a logica fica em `$runnerFileName`; o `run.ps1` e so o shim. Mudanca de contrato (lock, telemetria, idempotencia) vale no runner, nao no shim.
- **Registro no Orchestrator:** esta pasta nasce desacoplada de `config.json` legado; o cadastro operacional deve ser feito pelo Dashboard ou API.
- **Catálogo governado:** preencha `automation.manifest.json` antes de promover a automação para operação recorrente.
- **Smoke inicial:** o scaffold já cria `Orchestrator/tests/test_$slug.py` como prova mínima de existência dos artefatos obrigatórios.
"@

$runBatContent = @"
@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "..\lib\Send-WhatsApp.ps1" -ExecId "MANUAL_BAT" -Mode VISUAL -ConfigPath "%~dp0whatsapp-config.json"
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
Invoke-SafeWrite -FilePath (Join-Path $automationDir $runnerFileName) -Content $runnerContent -Operation "Gerar runner Python da automacao"
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
