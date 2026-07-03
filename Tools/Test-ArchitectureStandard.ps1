# {
#   "version": "1.0.0",
#   "skill": "protocolo-valeg",
#   "description": "Validador de padronizacao arquitetural do Hub de Automacoes"
# }
[CmdletBinding()]
param(
    [string]$RootPath = ".",
    [string[]]$Paths = @(),
    [switch]$AsJson
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$script:Findings = @()
$script:RulesetRelativePath = "Tools\architecture-standard.rules.json"
$script:Ruleset = $null
$script:ExcludedFragments = @(
    "\.git\",
    "\.venv\",
    "\.mypy_cache\",
    "\.pytest_cache\",
    "\node_modules\",
    "\Logs\",
    "\Backups\",
    "\.wwebjs_auth\",
    "\.claude\worktrees\"
)

function Convert-ToRelativePath {
    param(
        [string]$Path,
        [string]$BasePath
    )

    $rootFull = [System.IO.Path]::GetFullPath($BasePath)
    $pathFull = [System.IO.Path]::GetFullPath($Path)

    if ($pathFull.StartsWith($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $pathFull.Substring($rootFull.Length).TrimStart([char]'\', [char]'/' ).Replace("/", "\")
    }

    return $Path.Replace("/", "\")
}

function Resolve-RepoRelativePath {
    param(
        [string]$BasePath,
        [string]$InputPath
    )

    $rootFull = [System.IO.Path]::GetFullPath($BasePath).TrimEnd([char[]]@("\", "/"))
    $candidate = Join-Path $rootFull $InputPath.Trim('"')
    $resolved = [System.IO.Path]::GetFullPath($candidate)
    $rootPrefix = $rootFull + [System.IO.Path]::DirectorySeparatorChar

    if ($resolved.Equals($rootFull, [System.StringComparison]::OrdinalIgnoreCase) -or
        $resolved.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        return [pscustomobject]@{
            IsInside     = $true
            FullPath     = $resolved
            RelativePath = (Convert-ToRelativePath -Path $resolved -BasePath $rootFull)
        }
    }

    return [pscustomobject]@{
        IsInside     = $false
        FullPath     = $resolved
        RelativePath = $InputPath.Replace("/", "\")
    }
}

function Test-ShouldSkipPath {
    param([string]$Path)

    $normalized = $Path.Replace("/", "\")
    foreach ($fragment in $script:ExcludedFragments) {
        if ($normalized.IndexOf($fragment, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            return $true
        }
    }

    return $false
}

function Test-MatchAnyPattern {
    param(
        [string]$Value,
        [string[]]$Patterns
    )

    foreach ($pattern in $Patterns) {
        if ($Value -match $pattern) {
            return $true
        }
    }

    return $false
}

function Add-ArchitectureFinding {
    param(
        [ValidateSet("critical", "warning", "info")]
        [string]$Severity,
        [string]$Rule,
        [string]$File,
        [string]$Detail,
        [string]$RecommendedAction
    )

    $null = $script:Findings += [pscustomobject]@{
        severity           = $Severity
        rule               = $Rule
        file               = $File
        detail             = $Detail
        recommended_action = $RecommendedAction
    }
}

function Get-Utf8FileText {
    param([string]$FilePath)

    $encoding = New-Object System.Text.UTF8Encoding($false, $true)
    return [System.IO.File]::ReadAllText($FilePath, $encoding)
}

function Import-ArchitectureRules {
    param([string]$BasePath)

    $rulesPath = Join-Path $BasePath $script:RulesetRelativePath
    if (-not (Test-Path -LiteralPath $rulesPath -PathType Leaf)) {
        Add-ArchitectureFinding `
            -Severity "critical" `
            -Rule "RULESET_MISSING" `
            -File $script:RulesetRelativePath `
            -Detail "Arquivo de regras arquiteturais nao encontrado." `
            -RecommendedAction "Crie Tools/architecture-standard.rules.json antes de confiar no validador."
        return
    }

    try {
        $content = Get-Utf8FileText -FilePath $rulesPath
        $script:Ruleset = $content | ConvertFrom-Json
    }
    catch [System.Exception] {
        Add-ArchitectureFinding `
            -Severity "critical" `
            -Rule "RULESET_LOAD_FAILED" `
            -File $script:RulesetRelativePath `
            -Detail "Falha ao carregar ruleset arquitetural: $($_.Exception.Message)" `
            -RecommendedAction "Corrija a sintaxe e o encoding UTF-8 sem BOM do arquivo de regras."
    }
}

function Get-RulePatterns {
    param([string]$PropertyName)

    if ($null -eq $script:Ruleset -or -not $script:Ruleset.PSObject.Properties.Name.Contains($PropertyName)) {
        return @()
    }

    return @($script:Ruleset.$PropertyName | ForEach-Object { [string]$_ })
}

function Get-TargetFiles {
    param(
        [string]$BasePath,
        [string[]]$InputPaths,
        [ref]$ResolvedRelativePaths
    )

    $extensions = @(".py", ".ps1", ".psm1", ".md", ".json")
    $files = @()

    if ($InputPaths.Count -gt 0) {
        foreach ($path in $InputPaths) {
            if ([string]::IsNullOrWhiteSpace($path)) {
                continue
            }

            $resolvedPath = Resolve-RepoRelativePath -BasePath $BasePath -InputPath $path
            if (-not $resolvedPath.IsInside) {
                Add-ArchitectureFinding `
                    -Severity "critical" `
                    -Rule "PATH_OUTSIDE_ROOT" `
                    -File $resolvedPath.RelativePath `
                    -Detail "Caminho informado em -Paths resolve fora da raiz do projeto." `
                    -RecommendedAction "Passe apenas caminhos relativos contidos em RootPath."
                continue
            }

            $ResolvedRelativePaths.Value += @($resolvedPath.RelativePath)
            if ((Test-Path -LiteralPath $resolvedPath.FullPath -PathType Leaf) -and -not (Test-ShouldSkipPath -Path $resolvedPath.FullPath)) {
                $item = Get-Item -LiteralPath $resolvedPath.FullPath
                if ($extensions -contains $item.Extension.ToLowerInvariant()) {
                    $files += $item
                }
            }
        }

        return @($files | Sort-Object FullName -Unique)
    }

    return @(
        Get-ChildItem -LiteralPath $BasePath -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object {
                $extensions -contains $_.Extension.ToLowerInvariant() -and
                -not (Test-ShouldSkipPath -Path $_.FullName)
            } |
            Sort-Object FullName
    )
}

function Get-RepoText {
    param(
        [string]$BasePath,
        [string]$RelativePath
    )

    $fullPath = Join-Path $BasePath $RelativePath
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        return $null
    }

    return Get-Utf8FileText -FilePath $fullPath
}

function Test-ArchitectureDocumentation {
    param([string]$BasePath)

    $standardPath = "docs\architecture-standard.md"
    $standardText = Get-RepoText -BasePath $BasePath -RelativePath $standardPath
    if ($null -eq $standardText) {
        Add-ArchitectureFinding `
            -Severity "critical" `
            -Rule "ARCH_STANDARD_DOC_MISSING" `
            -File $standardPath `
            -Detail "O padrao arquitetural oficial nao foi encontrado." `
            -RecommendedAction "Crie docs/architecture-standard.md com camadas, ownership, severidade e validacao."
        return
    }

    $requiredSections = @()
    if ($null -ne $script:Ruleset -and $script:Ruleset.PSObject.Properties.Name.Contains("documentation_required_sections")) {
        $requiredSections = @($script:Ruleset.documentation_required_sections)
    }
    if ($requiredSections.Count -eq 0) {
        $requiredSections = @(
            [pscustomobject]@{ Label = "Camadas"; Pattern = "Camadas" },
            [pscustomobject]@{ Label = "Severidade"; Pattern = "Severidade" },
            [pscustomobject]@{ Label = "Validação"; Pattern = "Valida(cao|ção)" }
        )
    }

    foreach ($required in $requiredSections) {
        if ($standardText -notmatch $required.Pattern) {
            Add-ArchitectureFinding `
                -Severity "warning" `
                -Rule "ARCH_STANDARD_SECTION_MISSING" `
                -File $standardPath `
                -Detail "Secao esperada ausente no padrao arquitetural: $($required.Label)." `
                -RecommendedAction "Atualize o documento para manter o contrato operacional completo."
        }
    }

    foreach ($doc in @("README.md", "CONTEXT.md", "docs\repository-governance.md")) {
        $content = Get-RepoText -BasePath $BasePath -RelativePath $doc
        if ($null -eq $content) {
            Add-ArchitectureFinding `
                -Severity "warning" `
                -Rule "ARCH_REFERENCE_DOC_MISSING" `
                -File $doc `
                -Detail "Documento esperado para referencia arquitetural nao foi encontrado." `
                -RecommendedAction "Confirme se o documento continua fazendo parte da documentacao viva do Hub."
            continue
        }

        if (-not $content.Contains("docs/architecture-standard.md") -and -not $content.Contains("architecture-standard.md")) {
            Add-ArchitectureFinding `
                -Severity "warning" `
                -Rule "ARCH_STANDARD_REFERENCE_MISSING" `
                -File $doc `
                -Detail "Documento nao referencia o padrao arquitetural oficial." `
                -RecommendedAction "Inclua referencia curta para docs/architecture-standard.md."
        }
    }
}

function Test-GetEndpointContainsOracleImport {
    param([string]$Content)

    $insideGetEndpoint = $false
    foreach ($line in @($Content -split "`r?`n")) {
        $codeLine = ($line -replace '#.*$', '')
        if ($codeLine -match '^\s*@router\.get\(') {
            $insideGetEndpoint = $true
            continue
        }

        if ($insideGetEndpoint -and $codeLine -match '^\s*@router\.') {
            $insideGetEndpoint = $false
        }

        if ($insideGetEndpoint -and $codeLine -match '^\s*(import|from)\s+(oracledb|cx_Oracle)\b') {
            return $true
        }
    }

    return $false
}

function Test-PythonArchitecture {
    param(
        [System.IO.FileInfo[]]$Files,
        [string]$BasePath
    )

    foreach ($file in @($Files | Where-Object { $_ -is [System.IO.FileInfo] -and $_.Extension -eq ".py" })) {
        $relativePath = Convert-ToRelativePath -Path $file.FullName -BasePath $BasePath
        $content = Get-Utf8FileText -FilePath $file.FullName
        $normalizedRelativePath = $relativePath.Replace("/", "\")
        $subprocessAllowlist = Get-RulePatterns -PropertyName "python_subprocess_allowlist"
        $sqliteAllowlist = Get-RulePatterns -PropertyName "python_sqlite_allowlist"

        if ($content -match '(?m)^\s*(import|from)\s+(oracledb|cx_Oracle)\b' -and
            $normalizedRelativePath -match '^Orchestrator\\app\\routers\\') {
            Add-ArchitectureFinding `
                -Severity "critical" `
                -Rule "ORACLE_IN_API_ROUTER" `
                -File $relativePath `
                -Detail "Router FastAPI importando Oracle diretamente quebra o contrato snapshot-first e Zero Trust." `
                -RecommendedAction "Mova acesso Oracle para runner controlado fora de endpoints GET e exponha somente snapshots sanitizados."
        }

        if (Test-GetEndpointContainsOracleImport -Content $content) {
            Add-ArchitectureFinding `
                -Severity "critical" `
                -Rule "ORACLE_IN_GET_ENDPOINT" `
                -File $relativePath `
                -Detail "Endpoint GET contem referencia direta a Oracle no mesmo bloco de rota." `
                -RecommendedAction "Preserve leitura de API por snapshots locais e mantenha refresh Oracle fora do contrato de leitura."
        }

        if ($content -match '(?m)^\s*import\s+sqlite3\b|^\s*from\s+sqlite3\s+import\b' -and
            -not (Test-MatchAnyPattern -Value $normalizedRelativePath -Patterns $sqliteAllowlist)) {
            Add-ArchitectureFinding `
                -Severity "critical" `
                -Rule "SQLITE_DIRECT_ACCESS_OUTSIDE_DB_LAYER" `
                -File $relativePath `
                -Detail "Uso direto de sqlite3 fora das camadas autorizadas cria atalho de persistencia." `
                -RecommendedAction "Use a camada de banco/runtime existente ou declare uma excecao arquitetural documentada."
        }

        if ($normalizedRelativePath -match '^Orchestrator\\tests\\') {
            continue
        }

        if ($content -match '(?m)^\s*import\s+subprocess\b|^\s*from\s+subprocess\s+import\b' -and
            -not (Test-MatchAnyPattern -Value $normalizedRelativePath -Patterns $subprocessAllowlist)) {
            Add-ArchitectureFinding `
                -Severity "warning" `
                -Rule "SUBPROCESS_OUTSIDE_RUNTIME_ALLOWLIST" `
                -File $relativePath `
                -Detail "Novo uso de subprocess fora das fronteiras runtime autorizadas pode criar ownership opaco de processos." `
                -RecommendedAction "Centralize execucao em worker/runtime/service autorizado ou registre excecao no padrao arquitetural."
        }
    }
}

function Test-IsRelatedAutomationPath {
    param(
        [string]$CandidatePath,
        [string[]]$RelatedPaths
    )

    foreach ($relatedPath in $RelatedPaths) {
        $normalized = $relatedPath.Replace("/", "\").TrimEnd("\")
        if ([string]::IsNullOrWhiteSpace($normalized)) {
            continue
        }

        if ($CandidatePath.Equals($normalized, [System.StringComparison]::OrdinalIgnoreCase) -or
            $CandidatePath.StartsWith($normalized + "\", [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }

    return $false
}

function Get-AutomationRelatedPaths {
    param(
        [string]$BasePath,
        [System.IO.FileInfo]$RunFile,
        [object]$Manifest
    )

    $automationDir = $RunFile.Directory.FullName
    $relatedPaths = @(
        (Convert-ToRelativePath -Path $automationDir -BasePath $BasePath),
        (Convert-ToRelativePath -Path $RunFile.FullName -BasePath $BasePath),
        (Convert-ToRelativePath -Path (Join-Path $automationDir "automation.manifest.json") -BasePath $BasePath)
    )

    if ($null -ne $Manifest) {
        foreach ($propertyName in @("runbook_path", "readme_path", "context_path")) {
            if ($Manifest.PSObject.Properties.Name.Contains($propertyName)) {
                $relatedPaths += [string]$Manifest.$propertyName
            }
        }

        if ($Manifest.PSObject.Properties.Name.Contains("smoke_tests")) {
            foreach ($smokeTest in @($Manifest.smoke_tests)) {
                $relatedPaths += [string]$smokeTest
            }
        }
    }

    return @($relatedPaths | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Sort-Object -Unique)
}

function Test-AutomationArchitecture {
    param(
        [string]$BasePath,
        [string[]]$TargetRelativePaths = @(),
        [switch]$Targeted
    )

    $runFiles = @(
        Get-ChildItem -LiteralPath $BasePath -Recurse -Filter "run.ps1" -File -ErrorAction SilentlyContinue |
            Where-Object {
                -not (Test-ShouldSkipPath -Path $_.FullName) -and
                -not (Test-MatchAnyPattern -Value (Convert-ToRelativePath -Path $_.FullName -BasePath $BasePath) -Patterns (Get-RulePatterns -PropertyName "automation_exclusions"))
            }
    )

    foreach ($runFile in $runFiles) {
        $automationDir = $runFile.Directory.FullName
        $relativeRun = Convert-ToRelativePath -Path $runFile.FullName -BasePath $BasePath
        $manifestPath = Join-Path $automationDir "automation.manifest.json"
        $manifest = $null

        if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
            if ($Targeted -and -not (Test-IsRelatedAutomationPath -CandidatePath $relativeRun -RelatedPaths $TargetRelativePaths)) {
                continue
            }

            Add-ArchitectureFinding `
                -Severity "critical" `
                -Rule "AUTOMATION_MANIFEST_MISSING" `
                -File $relativeRun `
                -Detail "Automacao com run.ps1 sem automation.manifest.json no mesmo diretorio." `
                -RecommendedAction "Gere ou alinhe o manifesto governado antes de promover a automacao."
            continue
        }

        try {
            $manifest = (Get-Utf8FileText -FilePath $manifestPath) | ConvertFrom-Json
        }
        catch [System.Exception] {
            if ($Targeted -and -not (Test-IsRelatedAutomationPath -CandidatePath $relativeRun -RelatedPaths $TargetRelativePaths)) {
                continue
            }

            Add-ArchitectureFinding `
                -Severity "critical" `
                -Rule "AUTOMATION_MANIFEST_INVALID_JSON" `
                -File (Convert-ToRelativePath -Path $manifestPath -BasePath $BasePath) `
                -Detail "Manifesto da automacao nao pode ser lido como JSON valido." `
                -RecommendedAction "Corrija a sintaxe JSON do manifesto."
            continue
        }

        if ($Targeted) {
            $relatedPaths = Get-AutomationRelatedPaths -BasePath $BasePath -RunFile $runFile -Manifest $manifest
            $isImpacted = $false
            foreach ($targetPath in $TargetRelativePaths) {
                if (Test-IsRelatedAutomationPath -CandidatePath $targetPath -RelatedPaths $relatedPaths) {
                    $isImpacted = $true
                    break
                }
            }

            if (-not $isImpacted) {
                continue
            }
        }
    }
}

function New-ArchitectureReport {
    param(
        [string]$ResolvedRoot,
        [string]$Scope
    )

    $criticalCount = @($script:Findings | Where-Object { $_.severity -eq "critical" }).Count
    $warningCount = @($script:Findings | Where-Object { $_.severity -eq "warning" }).Count
    $infoCount = @($script:Findings | Where-Object { $_.severity -eq "info" }).Count
    $status = if ($criticalCount -gt 0) {
        "incident"
    }
    elseif ($warningCount -gt 0) {
        "attention"
    }
    else {
        "healthy"
    }

    return [pscustomobject]@{
        tool     = "Test-ArchitectureStandard"
        version  = "1.0.0"
        root     = $ResolvedRoot
        status   = $status
        scope    = $Scope
        summary  = [pscustomobject]@{
            critical = $criticalCount
            warning  = $warningCount
            info     = $infoCount
        }
        findings = @($script:Findings | Sort-Object severity, file, rule)
    }
}

try {
    $resolvedRoot = (Resolve-Path -LiteralPath $RootPath).Path
    $scope = if ($Paths.Count -gt 0) { "targeted" } else { "full" }
    Import-ArchitectureRules -BasePath $resolvedRoot

    $targetRelativePaths = @()
    $targetFiles = Get-TargetFiles -BasePath $resolvedRoot -InputPaths $Paths -ResolvedRelativePaths ([ref]$targetRelativePaths)

    Test-ArchitectureDocumentation -BasePath $resolvedRoot
    Test-PythonArchitecture -Files $targetFiles -BasePath $resolvedRoot
    Test-AutomationArchitecture -BasePath $resolvedRoot -TargetRelativePaths $targetRelativePaths -Targeted:($Paths.Count -gt 0)

    $report = New-ArchitectureReport -ResolvedRoot $resolvedRoot -Scope $scope

    if ($AsJson) {
        $report | ConvertTo-Json -Depth 8
    }
    else {
        Write-Host "=== PADRAO ARQUITETURAL DO HUB ===" -ForegroundColor Cyan
        Write-Host ("Escopo: " + $report.scope) -ForegroundColor Gray
        Write-Host ("Status: " + $report.status) -ForegroundColor Gray
        Write-Host ("Criticos: {0} | Avisos: {1} | Infos: {2}" -f $report.summary.critical, $report.summary.warning, $report.summary.info) -ForegroundColor Gray
        Write-Host ""

        if ($report.findings.Count -eq 0) {
            Write-Host "[OK] Padrao arquitetural em conformidade." -ForegroundColor Green
        }
        else {
            foreach ($finding in $report.findings) {
                $color = if ($finding.severity -eq "critical") {
                    "Red"
                }
                elseif ($finding.severity -eq "warning") {
                    "Yellow"
                }
                else {
                    "Gray"
                }

                Write-Host ("[{0}] {1} :: {2}" -f $finding.severity.ToUpperInvariant(), $finding.file, $finding.rule) -ForegroundColor $color
                Write-Host ("  Detalhe: " + $finding.detail) -ForegroundColor DarkGray
                Write-Host ("  Acao: " + $finding.recommended_action) -ForegroundColor DarkGray
            }
        }
    }

    if ($report.summary.critical -gt 0) {
        exit 1
    }

    exit 0
}
catch [System.Exception] {
    $errorReport = [pscustomobject]@{
        tool     = "Test-ArchitectureStandard"
        version  = "1.0.0"
        status   = "incident"
        scope    = "execution_error"
        summary  = [pscustomobject]@{
            critical = 1
            warning  = 0
            info     = 0
        }
        findings = @(
            [pscustomobject]@{
                severity           = "critical"
                rule               = "TOOL_EXECUTION_ERROR"
                file               = "Tools\Test-ArchitectureStandard.ps1"
                detail             = $_.Exception.Message
                recommended_action = "Corrija a falha de execucao do validador antes de confiar no resultado."
            }
        )
    }

    if ($AsJson) {
        $errorReport | ConvertTo-Json -Depth 8
    }
    else {
        Write-Host "[ERRO] Falha ao executar Test-ArchitectureStandard.ps1: $($_.Exception.Message)" -ForegroundColor Red
    }

    exit 2
}
