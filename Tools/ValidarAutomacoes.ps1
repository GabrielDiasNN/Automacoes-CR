# cSpell:words cscript nologo RESUMO
[CmdletBinding()]
param(
    [string]$BasePath = "C:\Automacoes",
    [switch]$SkipGovernance,
    [switch]$SkipVbaComponentTypes,
    [switch]$OnlyGovernance,
    [switch]$FailOnTermWarnings
)

$ErrorActionPreference = "Stop"

function Invoke-GovernanceChecks {
    param(
        [string]$RootPath,
        [switch]$StrictTerms
    )

    $scannerPath = Join-Path $RootPath "Tools\Test-VbaPtBrGovernance.ps1"
    if (-not (Test-Path $scannerPath)) {
        Write-Host "[WARN] Scanner de governanca nao encontrado: $scannerPath"
        return 0
    }

    Write-Host "=== Governanca PT-BR VBA ==="

    $pwshArgs = @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        $scannerPath,
        "-BasePath",
        $RootPath
    )

    if ($StrictTerms) {
        $pwshArgs += "-FailOnTermWarnings"
    }

    & pwsh @pwshArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host ("[ERRO] Governanca reprovada. Exit=" + $exitCode)
    }

    Write-Host ""
    return $exitCode
}

function Invoke-VbaComponentTypeChecks {
    param(
        [string]$RootPath
    )

    $checkerPath = Join-Path $RootPath "Tools\Test-VbaComponentTypes.ps1"
    if (-not (Test-Path $checkerPath)) {
        Write-Host "[WARN] Validador de tipagem VBA nao encontrado: $checkerPath"
        return 0
    }

    $configPath = Join-Path $RootPath "config.json"
    if (-not (Test-Path $configPath)) {
        Write-Host "[WARN] config.json nao encontrado para descoberta de automacoes: $configPath"
        return 0
    }

    $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $targets = New-Object System.Collections.Generic.List[object]
    $seen = @{}

    foreach ($task in @($config.tasks)) {
        $scriptPathRaw = [string]$task.scriptPath
        if ([string]::IsNullOrWhiteSpace($scriptPathRaw)) {
            continue
        }

        if ($scriptPathRaw -notmatch "(?i)Trigger_Automation\.vbs$") {
            continue
        }

        $scriptPathResolved = $scriptPathRaw
        if (-not [System.IO.Path]::IsPathRooted($scriptPathResolved)) {
            $scriptPathResolved = Join-Path $RootPath $scriptPathResolved
        }

        if (-not (Test-Path -LiteralPath $scriptPathResolved)) {
            Write-Host ("[WARN] Trigger nao encontrado para tarefa '{0}': {1}" -f [string]$task.name, $scriptPathResolved)
            continue
        }

        $sourceFolder = Split-Path -Parent $scriptPathResolved
        $workbooks = Get-ChildItem -LiteralPath $sourceFolder -File -Filter "*.xlsm" -ErrorAction SilentlyContinue
        if (-not $workbooks -or $workbooks.Count -eq 0) {
            Write-Host ("[WARN] Nenhum .xlsm encontrado em: {0}" -f $sourceFolder)
            continue
        }

        foreach ($wb in $workbooks) {
            $key = [string]$wb.FullName
            if ($seen.ContainsKey($key)) {
                continue
            }

            $seen[$key] = $true
            $targets.Add([PSCustomObject]@{
                    Name         = [string]$task.name
                    WorkbookPath = [string]$wb.FullName
                    SourceFolder = [string]$sourceFolder
                })
        }
    }

    if ($targets.Count -eq 0) {
        Write-Host "[WARN] Nenhum alvo de tipagem VBA encontrado nas automacoes do config.json"
        return 0
    }

    Write-Host "=== Tipagem VBA (Todas as Automacoes) ==="

    $hasFailure = $false
    foreach ($target in $targets) {
        Write-Host ("--- {0} | {1} ---" -f $target.Name, $target.WorkbookPath)

        $pwshArgs = @(
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            $checkerPath,
            "-WorkbookPath",
            $target.WorkbookPath,
            "-SourceFolder",
            $target.SourceFolder
        )

        & pwsh @pwshArgs
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            $hasFailure = $true
            Write-Host ("[ERRO] Tipagem VBA reprovada para '{0}'. Exit={1}" -f $target.Name, $exitCode)
        }

        Write-Host ""
    }

    if ($hasFailure) {
        return 1
    }

    return 0
}

function Start-Automacao {
    param(
        [string]$Name,
        [string]$Dir,
        [string]$ExecId,
        [int]$TimeoutSec = 360
    )

    Write-Host "=== $Name | ExecId=$ExecId ==="
    Stop-Process -Name excel -Force -ErrorAction SilentlyContinue
    Set-Location $Dir

    $p = Start-Process -FilePath cscript.exe -ArgumentList '//nologo', 'Trigger_Automation.vbs', $ExecId -PassThru -WindowStyle Hidden
    $timedOut = $false

    try {
        Wait-Process -Id $p.Id -Timeout $TimeoutSec -ErrorAction Stop
    }
    catch {
        $timedOut = $true
    }

    if ($timedOut -or -not $p.HasExited) {
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        $exitCode = 'TIMEOUT'
    }
    else {
        $exitCode = [string]$p.ExitCode
    }

    Write-Host ("EXIT=" + $exitCode)

    $execLog = Join-Path $Dir 'Logs\Execution.log'
    if (Test-Path $execLog) {
        $match = Select-String -Path $execLog -Pattern ([Regex]::Escape($ExecId)) | Select-Object -Last 6
        if ($match) {
            Write-Host '-- Execution.log (ultimas linhas do ExecId) --'
            foreach ($m in $match) { Write-Host $m.Line }
        }
    }

    $vbaDaily = Join-Path $Dir ('Logs\log_' + (Get-Date -Format 'yyyy-MM-dd') + '.log')
    $vbaInternal = Join-Path $Dir 'Logs\VBA_Internal.log'

    if (Test-Path $vbaDaily) {
        $vbaMatch = Select-String -Path $vbaDaily -Pattern ([Regex]::Escape($ExecId)) | Select-Object -Last 8
        if ($vbaMatch) {
            Write-Host '-- VBA log diario (ultimas linhas do ExecId) --'
            foreach ($m in $vbaMatch) { Write-Host $m.Line }
        }
    }
    elseif (Test-Path $vbaInternal) {
        $vbaMatch = Select-String -Path $vbaInternal -Pattern ([Regex]::Escape($ExecId)) | Select-Object -Last 8
        if ($vbaMatch) {
            Write-Host '-- VBA_Internal.log (ultimas linhas do ExecId) --'
            foreach ($m in $vbaMatch) { Write-Host $m.Line }
        }
    }

    Write-Host ""
    return $exitCode
}

if (-not $SkipGovernance) {
    $govExitCode = Invoke-GovernanceChecks -RootPath $BasePath -StrictTerms:$FailOnTermWarnings
    if ($govExitCode -ne 0) {
        exit $govExitCode
    }
}

if (-not $SkipVbaComponentTypes) {
    $typeExitCode = Invoke-VbaComponentTypeChecks -RootPath $BasePath
    if ($typeExitCode -ne 0) {
        exit $typeExitCode
    }
}

if ($OnlyGovernance) {
    Write-Host "Somente governanca executada com sucesso."
    exit 0
}

$results = [ordered]@{}
$results['RE'] = Start-Automacao -Name 'Receitas Emitidas' -Dir (Join-Path $BasePath 'Receitas Emitidas') -ExecId 'BATCH_FINAL_RE_20260329'
$results['RB'] = Start-Automacao -Name 'Receitas Bloqueadas' -Dir (Join-Path $BasePath 'Receitas Bloqueadas') -ExecId 'BATCH_FINAL_RB_20260329' -TimeoutSec 420
$results['MT'] = Start-Automacao -Name 'Montagem Terceirizados' -Dir (Join-Path $BasePath 'Montagem de Terceirizados') -ExecId 'BATCH_FINAL_MT_20260329'

Write-Host '=== RESUMO FINAL ==='
foreach ($kv in $results.GetEnumerator()) {
    Write-Host ($kv.Key + '=' + $kv.Value)
}
