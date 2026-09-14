# ==============================================================================
# ARQUIVO: Test-SemanticGovernance.ps1
# VERSAO: 1.0.0
# DESCRICAO: Guardrail de drift semantico entre documentacao viva, catalogo,
#            versao operacional, skills e dependencias versionadas.
# ==============================================================================
[CmdletBinding()]
param(
    [string]$RootPath = ".",
    [string[]]$Paths = @()
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$base = (Resolve-Path -LiteralPath $RootPath).Path
$issues = @()

function Add-GovernanceIssue {
    param(
        [string]$File,
        [string]$Rule,
        [string]$Detail
    )

    $script:issues += [pscustomobject]@{
        File   = $File
        Rule   = $Rule
        Detail = $Detail
    }
}

function Get-RepoText {
    param([string]$RelativePath)

    $path = Join-Path $base $RelativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Add-GovernanceIssue -File $RelativePath -Rule "MISSING_FILE" -Detail "Arquivo esperado nao encontrado."
        return ""
    }

    return Get-Content -LiteralPath $path -Raw
}

function Get-CurrentVersion {
    $monitor = Get-RepoText -RelativePath "docs/ai-native-context-monitor.md"
    if ($monitor -match 'Hub em linha `v(?<version>\d+\.\d+\.\d+)`') {
        return $Matches.version
    }

    Add-GovernanceIssue -File "docs/ai-native-context-monitor.md" -Rule "CURRENT_VERSION_NOT_FOUND" -Detail "Nao foi possivel extrair a versao operacional atual."
    return $null
}

function Test-TextContains {
    param(
        [string]$RelativePath,
        [string]$Needle,
        [string]$Rule
    )

    $content = Get-RepoText -RelativePath $RelativePath
    if (-not $content.Contains($Needle)) {
        Add-GovernanceIssue -File $RelativePath -Rule $Rule -Detail "Texto esperado ausente: $Needle"
    }
}

function Test-TextNotContains {
    param(
        [string]$RelativePath,
        [string]$Needle,
        [string]$Rule
    )

    $content = Get-RepoText -RelativePath $RelativePath
    if ($content.Contains($Needle)) {
        Add-GovernanceIssue -File $RelativePath -Rule $Rule -Detail "Texto obsoleto encontrado: $Needle"
    }
}

function Get-ActiveSkillCount {
    $governanceScript = Get-RepoText -RelativePath "Tools/Test-SkillsGovernance.ps1"
    if ($governanceScript -match '(?s)\$script:ActiveSkillNames\s*=\s*@\((?<list>.*?)\)') {
        return ([regex]::Matches($Matches.list, '"[^"]+"')).Count
    }

    Add-GovernanceIssue -File "Tools/Test-SkillsGovernance.ps1" -Rule "ACTIVE_SKILL_COUNT_NOT_FOUND" -Detail "Nao foi possivel extrair `$script:ActiveSkillNames para derivar a contagem de skills."
    return $null
}

# Numeros por extenso usados em prosa PT-BR (ex.: "Nove skills governam...") para
# pegar drift que a forma numerica ("9 skills") nao cobre.
$script:SkillCountNumberWords = @{
    5  = "Cinco"
    6  = "Seis"
    7  = "Sete"
    8  = "Oito"
    9  = "Nove"
    10 = "Dez"
    11 = "Onze"
    12 = "Doze"
}

function Test-SkillCountDrift {
    param(
        [string[]]$RequiredDocs,
        [string[]]$SweepDocs
    )

    $count = Get-ActiveSkillCount
    if (-not $count) {
        return
    }

    foreach ($doc in $RequiredDocs) {
        Test-TextContains -RelativePath $doc -Needle "$count skills" -Rule "SKILL_TAXONOMY_DRIFT"
    }

    $allDocs = @($RequiredDocs + $SweepDocs) | Select-Object -Unique
    foreach ($doc in $allDocs) {
        $content = Get-RepoText -RelativePath $doc

        foreach ($match in [regex]::Matches($content, '(?<n>\d+)\s+skills\b')) {
            $n = [int]$match.Groups['n'].Value
            if ($n -eq $count) {
                continue
            }
            # "N skills operacionais" (as de .claude/skills fora do padrao, hoje 6)
            # e uma contagem legitima diferente da taxonomia de padrao — nao e drift.
            $windowStart = [Math]::Max(0, $match.Index - 40)
            $windowEnd = [Math]::Min($content.Length, $match.Index + $match.Length + 40)
            $window = $content.Substring($windowStart, $windowEnd - $windowStart)
            if ($window -match '(?i)operacion') {
                continue
            }
            Add-GovernanceIssue -File $doc -Rule "SKILL_TAXONOMY_DRIFT" -Detail "Contagem de skills desatualizada: '$($match.Value)' (atual: $count skills)."
        }

        foreach ($wordEntry in $script:SkillCountNumberWords.GetEnumerator()) {
            if ($wordEntry.Key -eq $count) {
                continue
            }
            $staleNeedle = "$($wordEntry.Value) skills"
            if ($content.Contains($staleNeedle)) {
                Add-GovernanceIssue -File $doc -Rule "SKILL_TAXONOMY_DRIFT" -Detail "Contagem de skills desatualizada (por extenso): '$staleNeedle' (atual: $count skills)."
            }
        }
    }
}

function Test-RootNodeLock {
    $rootPackageJson = Join-Path $base "package.json"
    $rootPackageLock = Join-Path $base "package-lock.json"

    if ((Test-Path -LiteralPath $rootPackageLock -PathType Leaf) -and -not (Test-Path -LiteralPath $rootPackageJson -PathType Leaf)) {
        Add-GovernanceIssue -File "package-lock.json" -Rule "ORPHAN_ROOT_PACKAGE_LOCK" -Detail "package-lock.json na raiz exige package.json correspondente."
    }
}

function Test-CatalogMap {
    $mapPath = "docs/automation-criticality-map.md"
    $map = Get-RepoText -RelativePath $mapPath
    $manifestFiles = Get-ChildItem -LiteralPath $base -Directory |
        Where-Object { $_.Name -notlike ".*" -and $_.Name -ne "_Template" } |
        ForEach-Object {
            $candidate = Join-Path $_.FullName "automation.manifest.json"
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                Get-Item -LiteralPath $candidate
            }
        }

    foreach ($manifestFile in $manifestFiles) {
        $manifest = Get-Content -LiteralPath $manifestFile.FullName -Raw | ConvertFrom-Json
        foreach ($expected in @($manifest.id, $manifest.name, $manifest.schedule_summary)) {
            if ([string]::IsNullOrWhiteSpace([string]$expected)) {
                continue
            }
            if (-not $map.Contains([string]$expected)) {
                Add-GovernanceIssue -File $mapPath -Rule "CATALOG_MAP_DRIFT" -Detail "Mapa de criticidade nao contem valor do manifesto $($manifestFile.Name): $expected"
            }
        }
    }
}

Write-Host "=== GOVERNANCA SEMANTICA ===" -ForegroundColor Cyan

$currentVersion = Get-CurrentVersion
if ($currentVersion) {
    foreach ($doc in @(
            "README.md",
            "CONTEXT.md",
            "docs/quality-dashboard.md",
            "docs/testing-strategy.md",
            "docs/test-coverage-map.md",
            "docs/repository-governance.md",
            "docs/security-policy.md",
            "docs/release-checklist.md"
        )) {
        Test-TextContains -RelativePath $doc -Needle "v$currentVersion" -Rule "VERSION_DRIFT"
    }

    $constants = Get-RepoText -RelativePath "Orchestrator/app/constants.py"
    if ($constants -notmatch "ORCHESTRATOR_VERSION\s*=\s*`"$currentVersion`"") {
        Add-GovernanceIssue -File "Orchestrator/app/constants.py" -Rule "RUNTIME_VERSION_DRIFT" -Detail "ORCHESTRATOR_VERSION deve refletir v$currentVersion."
    }
    if ($constants -notmatch "WORKER_VERSION\s*=\s*`"$currentVersion`"") {
        Add-GovernanceIssue -File "Orchestrator/app/constants.py" -Rule "RUNTIME_VERSION_DRIFT" -Detail "WORKER_VERSION deve refletir v$currentVersion."
    }
}

Test-SkillCountDrift -RequiredDocs @(
    ".github/skills/README.md",
    "CONTEXT.md"
) -SweepDocs @(
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    ".github/copilot-instructions.md",
    ".gemini/README.md",
    ".github/skills/ai-native-development-standard/SKILL.md"
)
Test-RootNodeLock
Test-CatalogMap

if ($issues.Count -eq 0) {
    Write-Host "[OK] Governanca semantica em conformidade." -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Red
Write-Host " VIOLACOES DE GOVERNANCA SEMANTICA ($($issues.Count) encontrada(s))" -ForegroundColor Red
Write-Host "============================================================" -ForegroundColor Red
Write-Host ""

foreach ($issue in $issues) {
    Write-Host ("  {0} - {1}" -f $issue.File, $issue.Rule) -ForegroundColor Yellow
    Write-Host ("    > {0}" -f $issue.Detail) -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "[FAIL] Corrija os drifts semanticos antes de prosseguir." -ForegroundColor Red
exit 1
