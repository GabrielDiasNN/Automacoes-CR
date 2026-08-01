# cSpell:words cscript nologo RESUMO
# {
#   "version": "9.3.3",
#   "skill": "enterprise-orchestration-contract",
#   "description": "Orquestrador de Validacao 100% Nativo (Soberano) - Otimizado para DX e Pre-commit"
# }
[CmdletBinding()]
param(
    [string]$BasePath = ".",
    [switch]$SkipGovernance,
    [switch]$SkipSkillsGovernance,
    [switch]$SkipDashboardTemplateGovernance,
    [switch]$OnlyGovernance,
    [switch]$StagedOnly,
    [switch]$FailOnHtmlCssWarnings,
    [switch]$FailOnTermWarnings,
    [string[]]$Paths = @(),
    [string]$SummaryJsonPath = ""
)

$ErrorActionPreference = "Stop"

function New-BatchExecId {
    param([string]$Prefix)
    return ("{0}_{1}" -f $Prefix, (Get-Date -Format "yyyyMMdd_HHmmss"))
}

function Add-StepTiming {
    param(
        [System.Collections.Generic.List[object]]$Collector,
        [string]$Step,
        [System.Diagnostics.Stopwatch]$Stopwatch,
        [string]$Status = "ok",
        [hashtable]$Metadata = @{}
    )

    $entry = [ordered]@{
        step        = $Step
        duration_ms = [math]::Round($Stopwatch.Elapsed.TotalMilliseconds, 2)
        status      = $Status
    }

    foreach ($key in $Metadata.Keys) {
        $entry[$key] = $Metadata[$key]
    }

    $Collector.Add([pscustomobject]$entry) | Out-Null
}

function Write-TimingSummary {
    param(
        [System.Collections.Generic.List[object]]$Collector,
        [string]$SelectionMode,
        [int]$ChangedFileCount,
        [int]$GovernancePathCount,
        [int]$LogTargetCount,
        [string]$SummaryPath = ""
    )

    $totalMs = [math]::Round((($Collector | Measure-Object -Property duration_ms -Sum).Sum), 2)

    Write-Host "`n=== RESUMO DO CICLO LOCAL ===" -ForegroundColor Cyan
    Write-Host ("Modo de selecao: {0}" -f $SelectionMode) -ForegroundColor Gray
    Write-Host ("Arquivos alterados analisados: {0}" -f $ChangedFileCount) -ForegroundColor Gray
    Write-Host ("Alvos governados direcionados: {0}" -f $GovernancePathCount) -ForegroundColor Gray
    Write-Host ("Alvos elegiveis para log: {0}" -f $LogTargetCount) -ForegroundColor Gray
    foreach ($entry in $Collector) {
        Write-Host ("- {0}: {1} ms [{2}]" -f $entry.step, $entry.duration_ms, $entry.status) -ForegroundColor DarkGray
    }
    Write-Host ("Tempo total observado: {0} ms" -f $totalMs) -ForegroundColor Gray

    if (-not [string]::IsNullOrWhiteSpace($SummaryPath)) {
        $resolvedSummaryPath = if ([System.IO.Path]::IsPathRooted($SummaryPath)) {
            $SummaryPath
        }
        else {
            Join-Path $PWD.Path $SummaryPath
        }

        $payload = [ordered]@{
            generated_at          = Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"
            selection_mode        = $SelectionMode
            changed_file_count    = $ChangedFileCount
            governance_path_count = $GovernancePathCount
            log_target_count      = $LogTargetCount
            total_ms              = $totalMs
            steps                 = @($Collector)
        } | ConvertTo-Json -Depth 6

        $parent = Split-Path -Parent $resolvedSummaryPath
        if (-not [string]::IsNullOrWhiteSpace($parent) -and -not (Test-Path $parent)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }

        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($resolvedSummaryPath, $payload, $utf8NoBom)
        Write-Host ("Resumo JSON salvo em: {0}" -f $resolvedSummaryPath) -ForegroundColor Gray
    }
}

function Invoke-SkillsGovernanceCheck {
    param([string]$RootPath)
    $checkerPath = Join-Path $RootPath "Tools\Test-SkillsGovernance.ps1"
    if (-not (Test-Path $checkerPath)) { return 0 }
    Write-Host "`n=== Governanca de Skills ===" -ForegroundColor Cyan
    & powershell -NoProfile -ExecutionPolicy Bypass -File $checkerPath -BasePath $RootPath | Out-Host
    return $LASTEXITCODE
}

function Invoke-DashboardTemplateCheck {
    param([string]$RootPath, [switch]$StrictWarnings)
    $checkerPath = (Get-Item (Join-Path $RootPath "Tools\Test-DashboardTemplate.ps1")).FullName
    if (-not (Test-Path $checkerPath)) { return 0 }
    Write-Host "`n=== Dashboard HTML/CSS ===" -ForegroundColor Cyan
    $psArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $checkerPath, "-BasePath", $RootPath)
    if ($StrictWarnings) { $psArgs += "-FailOnWarnings" }
    & powershell @psArgs | Out-Host
    return $LASTEXITCODE
}

function Get-GovernanceTargetSummary {
    param(
        [string]$RootPath,
        [switch]$UseStagedFiles,
        [string[]]$InputPaths = @()
    )

    $helperPath = Join-Path $RootPath "Tools\Get-GovernanceTargetSummary.ps1"
    if (-not (Test-Path $helperPath)) {
        throw "Classificador de diff governado nao encontrado em $helperPath"
    }

    if ($UseStagedFiles) {
        return & $helperPath -BasePath $RootPath -StagedOnly
    }

    if ($InputPaths.Count -gt 0) {
        return & $helperPath -BasePath $RootPath -Paths $InputPaths
    }

    return & $helperPath -BasePath $RootPath
}

function Invoke-NativeGovernanceCheck {
    param(
        [string]$RootPath,
        [string[]]$TargetPaths = @()
    )
    Write-Host "`n=== Governanca Nativa (Seguranca, SQL, Python, PS, JSON) ===" -ForegroundColor Cyan
    $checks = @("Test-ZeroTrust.ps1", "Test-SqlPerformance.ps1", "Test-PythonGovernance.ps1", "Test-PowerShellGovernance.ps1", "Test-PowerShellApprovedVerbs.ps1", "Test-PortablePaths.ps1", "Test-SourceEncoding.ps1", "Test-JsonConfig.ps1", "Test-PlaywrightEvidence.ps1", "Test-AutomationCatalog.ps1", "Test-ArchitectureStandard.ps1", "Test-DateConformidade.ps1", "Test-SemanticGovernance.ps1", "Test-NodeCommunications.ps1")
    $allOk = $true
    
    foreach ($script in $checks) {
        $path = Join-Path $RootPath "Tools\$script"
        if (Test-Path $path) {
            Write-Host "--- Rodando: $script ---" -ForegroundColor Gray

            if ($TargetPaths.Count -gt 0) {
                & $path -RootPath $RootPath -Paths $TargetPaths | Out-Host
            } else {
                & $path -RootPath $RootPath | Out-Host
            }

            if ($LASTEXITCODE -ne 0) {
                Write-Host "[FALHA] $script retornou erro." -ForegroundColor Red
                $allOk = $false
            }
        }
        else {
            # Ate 31/07/2026 nao havia este 'else': renomear, mover ou apagar um
            # script de checagem fazia o gate correspondente DESAPARECER com
            # $allOk intacto, e tanto o pre-commit quanto o job de CI reportavam
            # sucesso. O meta-gate nao tinha manifesto do que deveria ter rodado.
            Write-Host "[FALHA] Checagem obrigatoria ausente: Tools\$script. Se foi renomeada ou removida deliberadamente, atualize a lista `$checks no mesmo commit." -ForegroundColor Red
            $allOk = $false
        }
    }
    if ($allOk) { return 0 } else { return 1 }
}

function Invoke-LogConformidadeCheck {
    param(
        [string]$RootPath,
        [string[]]$TargetPaths = @()
    )

    if ($TargetPaths.Count -eq 0) {
        Write-Host "`n=== Conformidade de Log ===" -ForegroundColor Cyan
        Write-Host "[SKIP] Nenhum arquivo PowerShell operacional elegivel no diff atual." -ForegroundColor DarkYellow
        return 0
    }

    $checkerPath = Join-Path $RootPath "Tools\Test-LogConformidade.ps1"
    if (-not (Test-Path $checkerPath)) { return 0 }

    Write-Host "`n=== Conformidade de Log ===" -ForegroundColor Cyan
    & $checkerPath -RootPath $RootPath -Paths $TargetPaths | Out-Host
    return $LASTEXITCODE
}

# --- FLUXO PRINCIPAL ---
$globalResult = 0
$logTargetPaths = @()
$stepTimings = New-Object 'System.Collections.Generic.List[object]'
$selectionMode = "full_scan"
$changedFileCount = 0
$governancePathCount = 0
$logTargetCount = 0

# Auto-resolução de arquivos staged para pre-commit
if ($StagedOnly) {
    Write-Host "`n--- [Git pre-commit] Resolvendo arquivos staged automaticamente ---" -ForegroundColor Gray
    $stepWatch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $targetSummary = Get-GovernanceTargetSummary -RootPath $BasePath -UseStagedFiles
        $selectionMode = [string]$targetSummary.SelectionMode
        $changedFileCount = [int]$targetSummary.ChangedFileCount
        $governancePathCount = @($targetSummary.GovernancePaths).Count
        $logTargetCount = [int]$targetSummary.LogTargetCount
        if ($targetSummary.ChangedFileCount -eq 0) {
            $stepWatch.Stop()
            Add-StepTiming -Collector $stepTimings -Step "classificacao_diff" -Stopwatch $stepWatch -Status "ok" -Metadata @{
                selection_mode = $selectionMode
            }
            Write-TimingSummary -Collector $stepTimings -SelectionMode $selectionMode -ChangedFileCount $changedFileCount -GovernancePathCount $governancePathCount -LogTargetCount $logTargetCount -SummaryPath $SummaryJsonPath
            Write-Host "[OK] Nenhum arquivo staged na staged area para validar." -ForegroundColor Green
            exit 0
        }

        $Paths = @($targetSummary.GovernancePaths)
        $logTargetPaths = @($targetSummary.LogTargetPaths)

        Write-Host ("Arquivos staged encontrados para analise: " + $targetSummary.ChangedFileCount) -ForegroundColor Gray
        Write-Host ("Modo de selecao governada: " + $targetSummary.SelectionMode) -ForegroundColor Gray
        if ($targetSummary.HasCriticalPaths) {
            Write-Host "[AVISO] Alteracoes em arquivos centrais de infraestrutura/governanca detectadas." -ForegroundColor Yellow
            Write-Host "Forcando scan completo de governanca estatica no repositorio para seguranca de integridade." -ForegroundColor Yellow
        }
        if ($targetSummary.HasLogTargets) {
            Write-Host ("Arquivos elegiveis para conformidade de log: " + $targetSummary.LogTargetCount) -ForegroundColor Gray
        }
        $stepWatch.Stop()
        Add-StepTiming -Collector $stepTimings -Step "classificacao_diff" -Stopwatch $stepWatch -Status "ok" -Metadata @{
            selection_mode = $selectionMode
        }
    }
    catch [System.Exception] {
        $stepWatch.Stop()
        Add-StepTiming -Collector $stepTimings -Step "classificacao_diff" -Stopwatch $stepWatch -Status "warning" -Metadata @{
            selection_mode = "fallback"
        }
        Write-Host "[AVISO] Falha ao classificar arquivos staged. Certifique-se de que o Git esta instalado e o path esta correto." -ForegroundColor Yellow
    }
}

if (-not $StagedOnly -and $Paths.Count -gt 0) {
    $stepWatch = [System.Diagnostics.Stopwatch]::StartNew()
    $targetSummary = Get-GovernanceTargetSummary -RootPath $BasePath -InputPaths $Paths
    $Paths = @($targetSummary.GovernancePaths)
    $logTargetPaths = @($targetSummary.LogTargetPaths)
    $selectionMode = [string]$targetSummary.SelectionMode
    $changedFileCount = [int]$targetSummary.ChangedFileCount
    $governancePathCount = @($targetSummary.GovernancePaths).Count
    $logTargetCount = [int]$targetSummary.LogTargetCount

    if ($targetSummary.HasCriticalPaths) {
        Write-Host "[AVISO] Alteracoes em arquivos centrais de infraestrutura/governanca detectadas." -ForegroundColor Yellow
        Write-Host "Forcando scan completo de governanca estatica no repositorio para seguranca de integridade." -ForegroundColor Yellow
    }
    $stepWatch.Stop()
    Add-StepTiming -Collector $stepTimings -Step "classificacao_diff" -Stopwatch $stepWatch -Status "ok" -Metadata @{
        selection_mode = $selectionMode
    }
}
elseif (-not $StagedOnly) {
    $selectionMode = "full_scan"
    $changedFileCount = @($Paths).Count
    $governancePathCount = @($Paths).Count
}

if (-not $SkipGovernance) {
    $stepWatch = [System.Diagnostics.Stopwatch]::StartNew()
    $res = Invoke-NativeGovernanceCheck -RootPath $BasePath -TargetPaths $Paths
    $stepWatch.Stop()
    Add-StepTiming -Collector $stepTimings -Step "governanca_nativa" -Stopwatch $stepWatch -Status $(if ($res -eq 0) { "ok" } else { "error" })
    if ($res -ne 0) { $globalResult = 1 }

    if ($StagedOnly -or $logTargetPaths.Count -gt 0) {
        $stepWatch = [System.Diagnostics.Stopwatch]::StartNew()
        $res = Invoke-LogConformidadeCheck -RootPath $BasePath -TargetPaths $logTargetPaths
        $stepWatch.Stop()
        Add-StepTiming -Collector $stepTimings -Step "conformidade_log" -Stopwatch $stepWatch -Status $(if ($res -eq 0) { "ok" } else { "error" })
        if ($res -ne 0) { $globalResult = 1 }
    }

    $pytestExitCode = 0
    # Só executa pytest e testes pesados de Playwright se NÃO for OnlyGovernance
    if (-not $OnlyGovernance) {
        Write-Host "`n=== Testes Automatizados (pytest + Playwright E2E) ===" -ForegroundColor Cyan
        $stepWatch = [System.Diagnostics.Stopwatch]::StartNew()
        $rootPath = (Get-Item -LiteralPath $BasePath).FullName
        $localPython = Join-Path $rootPath ".venv\Scripts\python.exe"
        $orchestratorPath = Join-Path $rootPath "Orchestrator"
        Push-Location $orchestratorPath
        try {
            if (Test-Path -LiteralPath $localPython) {
                & $localPython -m pytest -v | Out-Host
            }
            else {
                python -m pytest -v | Out-Host
            }
            $pytestExitCode = $LASTEXITCODE
        }
        finally {
            Pop-Location
        }
        $stepWatch.Stop()
        Add-StepTiming -Collector $stepTimings -Step "pytest_e2e" -Stopwatch $stepWatch -Status $(if ($pytestExitCode -eq 0) { "ok" } else { "error" })

        # Executa a limpeza pós-testes para expurgar temporários (Fase E/G do V.A.L.E.G.)
        $cleanupScript = Join-Path $BasePath "Tools\AplicarPoliticaRetencao.ps1"
        if (Test-Path $cleanupScript) {
            Write-Host "`n=== Limpeza Segura pós-testes ===" -ForegroundColor Cyan
            $stepWatch = [System.Diagnostics.Stopwatch]::StartNew()
            & powershell -NoProfile -ExecutionPolicy Bypass -File $cleanupScript -RootPath $BasePath | Out-Host
            $stepWatch.Stop()
            Add-StepTiming -Collector $stepTimings -Step "limpeza_pos_testes" -Stopwatch $stepWatch -Status "ok"
        }
    }

    if (-not $OnlyGovernance) {
        if ($pytestExitCode -ne 0) {
            Write-Host "[FALHA] Suite de testes pytest falhou ou retornou erros de integridade." -ForegroundColor Red
            $globalResult = 1
        } else {
            Write-Host "[OK] Suite de testes pytest executada com 100% de sucesso." -ForegroundColor Green
        }
    }
}

if (-not $SkipSkillsGovernance) {
    $stepWatch = [System.Diagnostics.Stopwatch]::StartNew()
    $res = Invoke-SkillsGovernanceCheck -RootPath $BasePath
    $stepWatch.Stop()
    Add-StepTiming -Collector $stepTimings -Step "governanca_skills" -Stopwatch $stepWatch -Status $(if ($res -eq 0) { "ok" } else { "error" })
    if ($res -ne 0) { $globalResult = 1 }
}

if (-not $SkipDashboardTemplateGovernance) {
    $stepWatch = [System.Diagnostics.Stopwatch]::StartNew()
    $res = Invoke-DashboardTemplateCheck -RootPath $BasePath -StrictWarnings:$FailOnHtmlCssWarnings
    $stepWatch.Stop()
    Add-StepTiming -Collector $stepTimings -Step "governanca_dashboard_template" -Stopwatch $stepWatch -Status $(if ($res -eq 0) { "ok" } else { "error" })
    if ($res -ne 0) { $globalResult = 1 }
}

Write-TimingSummary -Collector $stepTimings -SelectionMode $selectionMode -ChangedFileCount $changedFileCount -GovernancePathCount $governancePathCount -LogTargetCount $logTargetCount -SummaryPath $SummaryJsonPath

if ($globalResult -ne 0) {
    Write-Host "`n[ERRO] A governanca reprovou um ou mais componentes." -ForegroundColor Red
    if ($OnlyGovernance) { exit 1 }
}

if ($OnlyGovernance) {
    Write-Host "`n[OK] Governanca executada com sucesso." -ForegroundColor Green
    exit 0
}

Write-Host "`n=== RESUMO DE SAUDE DO HUB ===" -ForegroundColor Cyan
Write-Host "Governanca: APROVADA" -ForegroundColor Green
Write-Host "Para disparar as automacoes, utilize o Orquestrador (Dashboard ou API)." -ForegroundColor Gray

if ($globalResult -ne 0) { exit 1 } else { exit 0 }
