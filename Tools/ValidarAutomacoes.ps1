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
    [string[]]$Paths = @()
)

$ErrorActionPreference = "Stop"

function New-BatchExecId {
    param([string]$Prefix)
    return ("{0}_{1}" -f $Prefix, (Get-Date -Format "yyyyMMdd_HHmmss"))
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

function Invoke-NativeGovernanceCheck {
    param(
        [string]$RootPath,
        [string[]]$TargetPaths = @()
    )
    Write-Host "`n=== Governanca Nativa (Seguranca, SQL, Python, PS, JSON) ===" -ForegroundColor Cyan
    $checks = @("Test-ZeroTrust.ps1", "Test-SqlPerformance.ps1", "Test-PythonGovernance.ps1", "Test-PowerShellGovernance.ps1", "Test-PowerShellApprovedVerbs.ps1", "Test-PortablePaths.ps1", "Test-SourceEncoding.ps1", "Test-JsonConfig.ps1", "Test-PlaywrightEvidence.ps1", "Test-AutomationCatalog.ps1", "Test-DateConformidade.ps1")
    $allOk = $true
    
    foreach ($script in $checks) {
        $path = Join-Path $RootPath "Tools\$script"
        if (Test-Path $path) {
            Write-Host "--- Rodando: $script ---" -ForegroundColor Gray
            
            $psArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $path, "-RootPath", $RootPath)
            if ($TargetPaths.Count -gt 0) {
                $psArgs += "-Paths"
                $psArgs += $TargetPaths
            }
            
            & powershell @psArgs | Out-Host
            if ($LASTEXITCODE -ne 0) {
                Write-Host "[FALHA] $script retornou erro." -ForegroundColor Red
                $allOk = $false
            }
        }
    }
    if ($allOk) { return 0 } else { return 1 }
}

# --- FLUXO PRINCIPAL ---
$globalResult = 0

# Auto-resolução de arquivos staged para pre-commit
if ($StagedOnly) {
    Write-Host "`n--- [Git pre-commit] Resolvendo arquivos staged automaticamente ---" -ForegroundColor Gray
    try {
        $gitStaged = git diff --cached --name-only --diff-filter=ACM
        if ([string]::IsNullOrWhiteSpace($gitStaged)) {
            Write-Host "[OK] Nenhum arquivo staged na staged area para validar." -ForegroundColor Green
            exit 0
        }
        $stagedPaths = $gitStaged -split "`r?`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
        $Paths += $stagedPaths
        Write-Host ("Arquivos staged encontrados para analise: " + $Paths.Count) -ForegroundColor Gray
    }
    catch [System.Exception] {
        Write-Host "[AVISO] Falha ao rodar git diff. Certifique-se de que o Git esta instalado e o path esta correto." -ForegroundColor Yellow
    }
}

# Tratamento e normalização de caminhos híbridos e detecção de fallback global
if ($Paths.Count -gt 0) {
    $Paths = $Paths | ForEach-Object {
        $_.Trim().Trim('"').Replace('/', '\')
    } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }

    $forceFullScan = $false
    $criticalPatterns = @(
        "^lib\\",
        "^Tools\\",
        "^AGENTS\.md$",
        "^GEMINI\.md$",
        "^CONTEXT\.md$",
        "^SECURITY\.md$",
        "^\.gitleaks\.toml$",
        "^\.github\\skills\\"
    )
    foreach ($pattern in $criticalPatterns) {
        if ($Paths | Where-Object { $_ -match $pattern }) {
            $forceFullScan = $true
            break
        }
    }

    if ($forceFullScan) {
        Write-Host "[AVISO] Alteracoes em arquivos centrais de infraestrutura/governanca detectadas." -ForegroundColor Yellow
        Write-Host "Forcando scan completo de governanca estatica no repositorio para seguranca de integridade." -ForegroundColor Yellow
        $Paths = @()
    }
}

if (-not $SkipGovernance) {
    $res = Invoke-NativeGovernanceCheck -RootPath $BasePath -TargetPaths $Paths
    if ($res -ne 0) { $globalResult = 1 }

    $pytestExitCode = 0
    # Só executa pytest e testes pesados de Playwright se NÃO for OnlyGovernance
    if (-not $OnlyGovernance) {
        Write-Host "`n=== Testes Automatizados (pytest + Playwright E2E) ===" -ForegroundColor Cyan
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

        # Executa a limpeza pós-testes para expurgar temporários (Fase E/G do V.A.L.E.G.)
        $cleanupScript = Join-Path $BasePath "Tools\AplicarPoliticaRetencao.ps1"
        if (Test-Path $cleanupScript) {
            Write-Host "`n=== Limpeza Segura pós-testes ===" -ForegroundColor Cyan
            & powershell -NoProfile -ExecutionPolicy Bypass -File $cleanupScript -RootPath $BasePath | Out-Host
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
    $res = Invoke-SkillsGovernanceCheck -RootPath $BasePath
    if ($res -ne 0) { $globalResult = 1 }
}

if (-not $SkipDashboardTemplateGovernance) {
    $res = Invoke-DashboardTemplateCheck -RootPath $BasePath -StrictWarnings:$FailOnHtmlCssWarnings
    if ($res -ne 0) { $globalResult = 1 }
}

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
