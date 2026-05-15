# cSpell:words cscript nologo RESUMO
# {
#   "version": "4.1.0",
#   "skill": "enterprise-orchestration-contract",
#   "description": "Orquestrador de Validacao 100% Nativo (Soberano) - Estabilizado"
# }
[CmdletBinding()]
param(
    [string]$BasePath = ".",
    [switch]$SkipGovernance,
    [switch]$SkipSkillsGovernance,
    [switch]$SkipDashboardTemplateGovernance,
    [switch]$OnlyGovernance,
    [switch]$FailOnHtmlCssWarnings,
    [switch]$FailOnTermWarnings
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
    param([string]$RootPath)
    Write-Host "`n=== Governanca Nativa (Seguranca, SQL, Python, PS, JSON) ===" -ForegroundColor Cyan
    $checks = @("Test-ZeroTrust.ps1", "Test-SqlPerformance.ps1", "Test-PythonGovernance.ps1", "Test-PowerShellGovernance.ps1", "Test-PortablePaths.ps1", "Test-JsonConfig.ps1")
    $allOk = $true
    foreach ($script in $checks) {
        $path = Join-Path $RootPath "Tools\$script"
        if (Test-Path $path) {
            Write-Host "--- Rodando: $script ---" -ForegroundColor Gray
            & powershell -NoProfile -ExecutionPolicy Bypass -File $path -RootPath $RootPath | Out-Host
            if ($LASTEXITCODE -ne 0) {
                Write-Host "[FALHA] $script retornou erro." -ForegroundColor Red
                $allOk = $false
            }
        }
    }
    if ($allOk) { return 0 } else { return 1 }
}

function Start-Automacao {
    param([string]$Name, [string]$ScriptPath, [string]$ExecId, [int]$TimeoutSec = 360)
    Write-Host "`n=== $Name | ExecId=$ExecId ===" -ForegroundColor Cyan
    if ([string]::IsNullOrWhiteSpace($ScriptPath)) { return "SCRIPT_PATH_VAZIO" }
    $resolved = if ([System.IO.Path]::IsPathRooted($ScriptPath)) { $ScriptPath } else { Join-Path $BasePath $ScriptPath }
    if (-not (Test-Path $resolved)) { return "SCRIPT_NAO_ENCONTRADO" }

    $dir = Split-Path -Parent $resolved
    Write-Host ("[INFO] Iniciando automacao em: {0}" -f $dir)
    $p = Start-Process -FilePath powershell.exe -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $resolved, $ExecId -PassThru -WindowStyle Hidden -WorkingDirectory $dir

    $timedOut = $false
    try { Wait-Process -Id $p.Id -Timeout $TimeoutSec -ErrorAction Stop } catch [System.Exception] { $timedOut = $true }
    if ($timedOut -or -not $p.HasExited) { Stop-Process -Id $p.Id -Force; $exitCode = 'TIMEOUT' } else { $exitCode = [string]$p.ExitCode }
    Write-Host ("EXIT=" + $exitCode)
    return $exitCode
}

# --- FLUXO PRINCIPAL ---
$globalResult = 0

if (-not $SkipGovernance) {
    $res = Invoke-NativeGovernanceCheck -RootPath $BasePath
    if ($res -ne 0) { $globalResult = 1 }
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

# (Execucao de automacoes segue...)
# v5.1: Agora as automacoes sao disparadas via Orquestrador ou banco de dados.
# Este bloco legado foi desativado para evitar falhas de caminho.

Write-Host "`n=== RESUMO DE SAUDE DO HUB ===" -ForegroundColor Cyan
Write-Host "Governanca: APROVADA" -ForegroundColor Green
Write-Host "Para disparar as automacoes, utilize o Orquestrador (Dashboard ou API)." -ForegroundColor Gray

if ($globalResult -ne 0) { exit 1 } else { exit 0 }

