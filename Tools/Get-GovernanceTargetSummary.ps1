[CmdletBinding()]
param(
    [string]$BasePath = ".",
    [switch]$StagedOnly,
    [string[]]$Paths = @(),
    [switch]$AsJson,

    # Suprime a promocao automatica a full_scan quando um caminho critico e
    # alterado. Existe para o hook Stop de .claude/hooks, que precisa de um
    # veredito em segundos: com a promocao ligada, um unico arquivo sob lib\ ou
    # Tools\ zerava GovernancePaths e fazia os 15 checks varrerem o repositorio
    # inteiro (340 s medidos em 01/09/2026 contra 6,7 s no modo direcionado),
    # estourando o timeout de 240 s do hook em toda execucao.
    # NAO use no pre-commit nem no CI: la a promocao e a rede de seguranca.
    [switch]$NoCriticalPromotion
)

$ErrorActionPreference = "Stop"

$resolvedRoot = (Resolve-Path -LiteralPath $BasePath).Path

function Get-NormalizedPaths {
    param([string[]]$InputPaths)

    return @(
        $InputPaths |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            ForEach-Object { $_.Trim().Trim('"').Replace('/', '\') } |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            Sort-Object -Unique
    )
}

function Test-MatchAnyPattern {
    param(
        [string]$Path,
        [string[]]$Patterns
    )

    foreach ($pattern in $Patterns) {
        if ($Path -match $pattern) {
            return $true
        }
    }

    return $false
}

if ($StagedOnly -and $Paths.Count -eq 0) {
    $stagedRaw = git diff --cached --name-only --diff-filter=ACM 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao obter arquivos staged via git diff --cached."
    }

    if (-not [string]::IsNullOrWhiteSpace($stagedRaw)) {
        $Paths = @($stagedRaw -split "`r?`n")
    }
}

$normalizedPaths = Get-NormalizedPaths -InputPaths $Paths

$criticalPatterns = @(
    "^lib\\",
    "^Tools\\",
    "^AGENTS\.md$",
    "^GEMINI\.md$",
    "^CONTEXT\.md$",
    "^SECURITY\.md$",
    "^\.gitleaks\.toml$",
    "^\.githooks\\pre-commit$",
    "^\.github\\workflows\\",
    "^\.github\\skills\\"
)

$logTargetPatterns = @(
    "\.(ps1|psm1)$"
)

$excludedLogTargetPatterns = @(
    "^Audit\\",
    "^Tools\\"
)

$criticalPaths = @(
    $normalizedPaths |
        Where-Object { Test-MatchAnyPattern -Path $_ -Patterns $criticalPatterns }
)

$logTargetPaths = @(
    $normalizedPaths |
        Where-Object { Test-MatchAnyPattern -Path $_ -Patterns $logTargetPatterns } |
        Where-Object { -not (Test-MatchAnyPattern -Path $_ -Patterns $excludedLogTargetPatterns) }
)

# CriticalPaths continua registrando o que foi detectado; HasCriticalPaths
# responde a pergunta diferente de "a promocao a full_scan vale aqui?". Com
# -NoCriticalPromotion as duas divergem, e e assim que o consumidor descobre
# que havia caminho critico sem que o scan completo tenha sido forcado.
$fullScanRequired = ($criticalPaths.Count -gt 0) -and (-not $NoCriticalPromotion)
$governancePaths = if ($fullScanRequired) { @() } else { $normalizedPaths }

$selectionMode = if ($normalizedPaths.Count -eq 0) {
    "no_paths"
}
elseif ($fullScanRequired) {
    "full_scan"
}
else {
    "targeted_paths"
}

# Flags por area para selecao de jobs no CI. Em full_scan (caminho critico
# alterado) ou diff vazio/indeterminado, todas as areas sao consideradas
# afetadas para garantir cobertura completa.
$forceAllAreas = $fullScanRequired -or ($normalizedPaths.Count -eq 0)

function Test-AreaAffected {
    param([string[]]$Patterns)

    if ($forceAllAreas) {
        return $true
    }

    return @(
        $normalizedPaths |
            Where-Object { Test-MatchAnyPattern -Path $_ -Patterns $Patterns }
    ).Count -gt 0
}

$hasPython = Test-AreaAffected -Patterns @("\.py$", "^requirements[^\\]*\.(txt|in)$")
$hasPowerShell = Test-AreaAffected -Patterns @("\.(ps1|psm1|psd1)$")
# `package.json` / `package-lock.json` entram aqui desde 31/07/2026: eles sao
# `.json` e nao batiam em nenhuma area, entao um PR que so alterasse dependencias
# do Dashboard passava pela governanca com ZERO jobs de build/teste executados —
# o job `frontend` (npm ci, ESLint, Vitest com gate de cobertura, tsc+vite build)
# depende de `has_js`, e `testes-e2e`/`testes-powershell` das mesmas flags.
$hasJs = Test-AreaAffected -Patterns @(
    "\.(js|mjs|cjs|ts|tsx)$",
    "\.(html|css)$",
    "package(-lock)?\.json$"
)
$hasMarkdown = Test-AreaAffected -Patterns @("\.md$")

$summary = [PSCustomObject]@{
    BasePath          = $resolvedRoot
    NormalizedPaths   = @($normalizedPaths)
    CriticalPaths     = @($criticalPaths)
    GovernancePaths   = @($governancePaths)
    LogTargetPaths    = @($logTargetPaths)
    HasCriticalPaths  = $fullScanRequired
    HasLogTargets     = $logTargetPaths.Count -gt 0
    HasPython         = $hasPython
    HasPowerShell     = $hasPowerShell
    HasJs             = $hasJs
    HasMarkdown       = $hasMarkdown
    SelectionMode     = $selectionMode
    ChangedFileCount  = $normalizedPaths.Count
    CriticalPathCount = $criticalPaths.Count
    LogTargetCount    = $logTargetPaths.Count
}

if ($AsJson) {
    $summary | ConvertTo-Json -Depth 6 -Compress
    exit 0
}

$summary
