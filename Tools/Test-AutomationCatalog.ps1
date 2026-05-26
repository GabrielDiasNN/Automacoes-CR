[CmdletBinding()]
param(
    [string]$RootPath = "."
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Resolve-ProjectPath {
    param(
        [string]$BasePath,
        [string]$RelativePath
    )

    $combined = Join-Path $BasePath $RelativePath
    $resolved = [System.IO.Path]::GetFullPath($combined)
    $rootFull = [System.IO.Path]::GetFullPath($BasePath)
    if (-not $resolved.StartsWith($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Caminho fora do projeto: $RelativePath"
    }
    return $resolved
}

function Test-ManifestShape {
    param(
        [pscustomobject]$Manifest,
        [string]$ManifestPath,
        [switch]$TemplateMode
    )

    $requiredFields = @(
        "id",
        "name",
        "slug",
        "criticality",
        "owner_area",
        "entrypoint",
        "runtime",
        "channels",
        "max_runtime_minutes",
        "max_retries",
        "schedule_summary",
        "runbook_path",
        "context_path",
        "readme_path",
        "orchestrator",
        "dependencies",
        "smoke_tests"
    )

    foreach ($field in $requiredFields) {
        if (-not $Manifest.PSObject.Properties.Name.Contains($field)) {
            throw "Manifesto sem campo obrigatório '$field': $ManifestPath"
        }
    }

    if (-not $Manifest.orchestrator.PSObject.Properties.Name.Contains("script_path")) {
        throw "Manifesto sem orchestrator.script_path: $ManifestPath"
    }

    if (-not $TemplateMode) {
        if ($Manifest.criticality -notin @("critical", "high", "medium", "low")) {
            throw "criticality inválido em $ManifestPath"
        }

        if ([string]::IsNullOrWhiteSpace([string]$Manifest.owner_area) -or [string]$Manifest.owner_area -match "^\[.+\]$") {
            throw "owner_area ausente ou com placeholder em $ManifestPath"
        }

        if ([string]::IsNullOrWhiteSpace([string]$Manifest.queue_group)) {
            throw "queue_group obrigatório ausente em $ManifestPath"
        }

        if (-not [string]$Manifest.runbook_path.StartsWith("docs/runbooks/", [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "runbook_path deve apontar para docs/runbooks/ em $ManifestPath"
        }

        if (@($Manifest.smoke_tests).Count -lt 1) {
            throw "smoke_tests deve declarar ao menos um teste em $ManifestPath"
        }

        foreach ($channel in @($Manifest.channels)) {
            if ($channel -notin @("email", "whatsapp")) {
                throw "Canal inválido '$channel' em $ManifestPath"
            }
        }
    }
}

Write-Host "=== GOVERNANCA DO CATALOGO DE AUTOMACOES ===" -ForegroundColor Cyan

$base = (Resolve-Path -LiteralPath $RootPath).Path
$issues = 0
$validated = 0

$manifestPaths = Get-ChildItem -LiteralPath $base -Directory |
    Where-Object { $_.Name -notlike ".*" } |
    ForEach-Object {
        $candidate = Join-Path $_.FullName "automation.manifest.json"
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            Get-Item -LiteralPath $candidate
        }
    }

foreach ($manifestFile in $manifestPaths) {
    $isTemplate = $manifestFile.Directory.Name -eq "_Template"
    try {
        $manifest = Get-Content -LiteralPath $manifestFile.FullName -Raw | ConvertFrom-Json
        Test-ManifestShape -Manifest $manifest -ManifestPath $manifestFile.FullName -TemplateMode:$isTemplate

        if (-not $isTemplate) {
            $readmePath = Resolve-ProjectPath -BasePath $base -RelativePath $manifest.readme_path
            $contextPath = Resolve-ProjectPath -BasePath $base -RelativePath $manifest.context_path
            $runbookPath = Resolve-ProjectPath -BasePath $base -RelativePath $manifest.runbook_path
            $scriptPath = Resolve-ProjectPath -BasePath $base -RelativePath $manifest.orchestrator.script_path
            $entrypointPath = Resolve-ProjectPath -BasePath $manifestFile.Directory.FullName -RelativePath $manifest.entrypoint

            foreach ($requiredPath in @($readmePath, $contextPath, $runbookPath, $scriptPath, $entrypointPath)) {
                if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
                    throw "Arquivo obrigatório ausente: $requiredPath"
                }
            }

            foreach ($smokeTest in @($manifest.smoke_tests)) {
                $smokePath = Resolve-ProjectPath -BasePath $base -RelativePath $smokeTest
                if (-not (Test-Path -LiteralPath $smokePath -PathType Leaf)) {
                    throw "Smoke test declarado no manifesto não encontrado: $smokeTest"
                }
            }
        }

        $validated++
        Write-Host "[OK] $($manifestFile.FullName)" -ForegroundColor Green
    }
    catch [System.Exception] {
        $issues++
        Write-Host "[ERRO] $($manifestFile.FullName) :: $($_.Exception.Message)" -ForegroundColor Red
    }
}

if ($validated -eq 0) {
    Write-Host "[ERRO] Nenhum automation.manifest.json foi validado." -ForegroundColor Red
    exit 1
}

Write-Host "Manifestos validados: $validated" -ForegroundColor Gray
Write-Host "Erros: $issues" -ForegroundColor Gray

if ($issues -gt 0) {
    exit 1
}

Write-Host "[OK] Catálogo de automações em conformidade." -ForegroundColor Green
