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
    [string]$SummaryJsonPath = "",

    # Repassado a Get-GovernanceTargetSummary: mantem a validacao restrita aos
    # -Paths informados mesmo quando um deles e critico (lib\, Tools\, AGENTS.md,
    # workflows, skills). Reservado ao hook Stop, que precisa responder em
    # segundos; pre-commit e CI devem manter a promocao a full_scan.
    [switch]$NoCriticalPromotion
)

$ErrorActionPreference = "Stop"

# A saida do git (diff --cached, ls-files) e' decodificada com [Console]::OutputEncoding.
# Disparado pelo hook (sh -> pwsh -File) ou pelo CI, o console herda ibm850 e o nome
# "Producao" (com acento) chegava corrompido: o Test-Path das checagens falhava e os
# arquivos de "Produção Beneficimento" saiam do gate sem aviso (18/11/2026). As
# checagens rodam in-process, entao este ajuste vale para todas elas.
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) }
catch [System.IO.IOException] { Write-Verbose "Sem console para ajustar a codificacao: $($_.Exception.Message)" }

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
        [string[]]$InputPaths = @(),
        [switch]$SuppressCriticalPromotion
    )

    $helperPath = Join-Path $RootPath "Tools\Get-GovernanceTargetSummary.ps1"
    if (-not (Test-Path $helperPath)) {
        throw "Classificador de diff governado nao encontrado em $helperPath"
    }

    if ($UseStagedFiles) {
        return & $helperPath -BasePath $RootPath -StagedOnly -NoCriticalPromotion:$SuppressCriticalPromotion
    }

    if ($InputPaths.Count -gt 0) {
        return & $helperPath -BasePath $RootPath -Paths $InputPaths -NoCriticalPromotion:$SuppressCriticalPromotion
    }

    return & $helperPath -BasePath $RootPath
}

function Invoke-NativeGovernanceCheck {
    param(
        [string]$RootPath,
        [string[]]$TargetPaths = @(),

        # Arquivos do diff local (staged ou -Paths) quando um caminho critico promoveu
        # a full_scan. Com -LintChangedOnly, pylint e PSScriptAnalyzer rodam so' sobre
        # eles (mais dependentes, no pylint); o resto das 15 checagens segue completo.
        # O CI nao passa nada disto e continua com pylint e PSScriptAnalyzer completos.
        [string[]]$LintScopePaths = @(),
        [switch]$LintChangedOnly
    )
    Write-Host "`n=== Governanca Nativa (Seguranca, SQL, Python, PS, JSON) ===" -ForegroundColor Cyan
    $checks = @("Test-ZeroTrust.ps1", "Test-SqlPerformance.ps1", "Test-PythonGovernance.ps1", "Test-PowerShellGovernance.ps1", "Test-PowerShellApprovedVerbs.ps1", "Test-PortablePaths.ps1", "Test-SourceEncoding.ps1", "Test-JsonConfig.ps1", "Test-PlaywrightEvidence.ps1", "Test-AutomationCatalog.ps1", "Test-ArchitectureStandard.ps1", "Test-DateConformidade.ps1", "Test-SemanticGovernance.ps1", "Test-NodeCommunications.ps1", "Test-LogEventSchema.ps1")
    $lintAwareChecks = @("Test-PythonGovernance.ps1", "Test-PowerShellGovernance.ps1")

    # Python (mypy + pylint) e Node (npm test) sao os blocos lentos e independentes
    # das demais checagens: rodam em jobs enquanto as outras 13 rodam in-process.
    # Antes de 18/11/2026 tudo era serial e o tempo de parede era a soma.
    $parallelChecks = @("Test-PythonGovernance.ps1", "Test-NodeCommunications.ps1")
    $allOk = $true

    $resolvedWorkDir = (Resolve-Path -LiteralPath $RootPath).Path
    $checkArgsFor = {
        param([string]$ScriptName)
        $checkArgs = @{ RootPath = $resolvedWorkDir }
        if ($TargetPaths.Count -gt 0) { $checkArgs["Paths"] = [string[]]$TargetPaths }
        if ($LintChangedOnly -and ($lintAwareChecks -contains $ScriptName)) {
            $checkArgs["LintScopePaths"] = [string[]]$LintScopePaths
            $checkArgs["LintChangedOnly"] = $true
        }
        return $checkArgs
    }

    $jobs = [ordered]@{}
    try {
        foreach ($script in $parallelChecks) {
            $path = Join-Path $resolvedWorkDir "Tools\$script"
            if (-not (Test-Path -LiteralPath $path)) { continue }
            $jobs[$script] = Start-Job -ScriptBlock {
                param([string]$ScriptPath, [string]$WorkDir, [hashtable]$CheckArgs)
                Set-Location -LiteralPath $WorkDir
                try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) }
                catch [System.IO.IOException] { Write-Verbose "Sem console no job: $($_.Exception.Message)" }
                $ErrorActionPreference = "Continue"
                $global:LASTEXITCODE = 0
                & $ScriptPath @CheckArgs *>&1 | ForEach-Object { "$_" }
                [pscustomobject]@{ GateExitCode = $LASTEXITCODE }
            } -ArgumentList $path, $resolvedWorkDir, (& $checkArgsFor $script)
        }

        foreach ($script in $checks) {
            $path = Join-Path $resolvedWorkDir "Tools\$script"
            if ($jobs.Contains($script)) {
                continue
            }
            if (Test-Path -LiteralPath $path) {
                Write-Host "--- Rodando: $script ---" -ForegroundColor Gray

                $checkArgs = & $checkArgsFor $script
                & $path @checkArgs | Out-Host

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

        foreach ($script in $jobs.Keys) {
            Write-Host "--- Rodando (em paralelo): $script ---" -ForegroundColor Gray
            $jobOutput = @(Receive-Job -Job $jobs[$script] -Wait -ErrorAction Continue)
            $exitRecord = @($jobOutput | Where-Object { $_ -isnot [string] -and $null -ne $_.PSObject.Properties["GateExitCode"] })
            $jobOutput | Where-Object { $_ -is [string] } | Out-Host
            # Sem o registro de saida o job morreu antes do fim: tratar como falha, nunca
            # como sucesso por omissao.
            if ($exitRecord.Count -ne 1 -or $exitRecord[0].GateExitCode -ne 0) {
                Write-Host "[FALHA] $script retornou erro." -ForegroundColor Red
                $allOk = $false
            }
        }
    }
    finally {
        foreach ($job in $jobs.Values) {
            if ($null -ne $job) {
                Stop-Job -Job $job -ErrorAction SilentlyContinue
                Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
            }
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
# Diff local (staged ou -Paths). So' e' usado para restringir pylint e
# PSScriptAnalyzer quando a promocao a full_scan zera $Paths; sem diff local (CI,
# execucao manual sem argumentos) os dois continuam sobre o repositorio inteiro.
$lintScopePaths = @()
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
        $targetSummary = Get-GovernanceTargetSummary -RootPath $BasePath -UseStagedFiles -SuppressCriticalPromotion:$NoCriticalPromotion
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
        $lintScopePaths = @($targetSummary.NormalizedPaths)

        Write-Host ("Arquivos staged encontrados para analise: " + $targetSummary.ChangedFileCount) -ForegroundColor Gray
        Write-Host ("Modo de selecao governada: " + $targetSummary.SelectionMode) -ForegroundColor Gray
        if ($targetSummary.HasCriticalPaths) {
            Write-Host "[AVISO] Alteracoes em arquivos centrais de infraestrutura/governanca detectadas." -ForegroundColor Yellow
            Write-Host "Forcando scan completo de governanca estatica no repositorio para seguranca de integridade." -ForegroundColor Yellow
        }
        elseif ($targetSummary.CriticalPathCount -gt 0) {
            Write-Host ("[AVISO] " + $targetSummary.CriticalPathCount + " caminho(s) critico(s) alterado(s), mas -NoCriticalPromotion suprimiu o scan completo.") -ForegroundColor Yellow
            Write-Host "Esta execucao NAO substitui o pre-commit nem o CI, que continuam promovendo a full_scan." -ForegroundColor Yellow
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
    $targetSummary = Get-GovernanceTargetSummary -RootPath $BasePath -InputPaths $Paths -SuppressCriticalPromotion:$NoCriticalPromotion
    $Paths = @($targetSummary.GovernancePaths)
    $logTargetPaths = @($targetSummary.LogTargetPaths)
    $lintScopePaths = @($targetSummary.NormalizedPaths)
    $selectionMode = [string]$targetSummary.SelectionMode
    $changedFileCount = [int]$targetSummary.ChangedFileCount
    $governancePathCount = @($targetSummary.GovernancePaths).Count
    $logTargetCount = [int]$targetSummary.LogTargetCount

    if ($targetSummary.HasCriticalPaths) {
        Write-Host "[AVISO] Alteracoes em arquivos centrais de infraestrutura/governanca detectadas." -ForegroundColor Yellow
        Write-Host "Forcando scan completo de governanca estatica no repositorio para seguranca de integridade." -ForegroundColor Yellow
    }
    elseif ($targetSummary.CriticalPathCount -gt 0) {
        Write-Host ("[AVISO] " + $targetSummary.CriticalPathCount + " caminho(s) critico(s) alterado(s), mas -NoCriticalPromotion suprimiu o scan completo.") -ForegroundColor Yellow
        Write-Host "Esta execucao NAO substitui o pre-commit nem o CI, que continuam promovendo a full_scan." -ForegroundColor Yellow
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
    $lintChangedOnly = ($selectionMode -eq "full_scan") -and ($lintScopePaths.Count -gt 0)
    if ($lintChangedOnly) {
        Write-Host "Varredura completa com pylint e PSScriptAnalyzer restritos ao diff (o CI roda os dois completos)." -ForegroundColor Gray
    }
    $res = Invoke-NativeGovernanceCheck -RootPath $BasePath -TargetPaths $Paths -LintScopePaths $lintScopePaths -LintChangedOnly:$lintChangedOnly
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
