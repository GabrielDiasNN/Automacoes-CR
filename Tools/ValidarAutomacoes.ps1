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

        if ($scriptPathRaw -notmatch "(?i)(Trigger_Automation\.vbs|run\.ps1)$") {
            continue
        }

        $scriptPathResolved = $scriptPathRaw
        if (-not [System.IO.Path]::IsPathRooted($scriptPathResolved)) {
            $scriptPathResolved = Join-Path $RootPath $scriptPathResolved
        }

        if (-not (Test-Path -LiteralPath $scriptPathResolved)) {
            Write-Host ("[WARN] Script nao encontrado para tarefa '{0}': {1}" -f [string]$task.name, $scriptPathResolved)
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
        [string]$ScriptPath,
        [string]$ExecId,
        [int]$TimeoutSec = 360
    )

    Write-Host "=== $Name | ExecId=$ExecId ==="

    $scriptPathResolved = $ScriptPath
    if ([string]::IsNullOrWhiteSpace($scriptPathResolved)) {
        Write-Host ("[ERRO] scriptPath vazio para tarefa '{0}'" -f $Name)
        Write-Host ""
        return "SCRIPT_PATH_VAZIO"
    }

    if (-not [System.IO.Path]::IsPathRooted($scriptPathResolved)) {
        $scriptPathResolved = Join-Path $BasePath $scriptPathResolved
    }

    if (-not (Test-Path -LiteralPath $scriptPathResolved)) {
        Write-Host ("[ERRO] Script nao encontrado para '{0}': {1}" -f $Name, $scriptPathResolved)
        Write-Host ""
        return "SCRIPT_NAO_ENCONTRADO"
    }

    $dir = Split-Path -Parent $scriptPathResolved
    $scriptExt = [System.IO.Path]::GetExtension($scriptPathResolved).ToLowerInvariant()

    Stop-Process -Name excel -Force -ErrorAction SilentlyContinue
    Set-Location $dir

    if ($scriptExt -eq ".vbs") {
        $p = Start-Process -FilePath cscript.exe -ArgumentList '//nologo', $scriptPathResolved, $ExecId -PassThru -WindowStyle Hidden
    }
    elseif ($scriptExt -eq ".ps1") {
        $p = Start-Process -FilePath powershell.exe -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $scriptPathResolved, $ExecId -PassThru -WindowStyle Hidden
    }
    else {
        Write-Host ("[ERRO] Extensao de script nao suportada para '{0}': {1}" -f $Name, $scriptExt)
        Write-Host ""
        return "EXT_NAO_SUPORTADA"
    }

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

    $logsDir = Join-Path $dir 'Logs'
    $candidateLogs = New-Object System.Collections.Generic.List[string]

    foreach ($knownLog in @(
            'Execution.log',
            ('log_' + (Get-Date -Format 'yyyy-MM-dd') + '.log'),
            'VBA_Internal.log',
            'Montagem.log',
            'ReceitasBloqueadas.log',
            'ReceitasEmitidas.log'
        )) {
        $candidateLogs.Add((Join-Path $logsDir $knownLog))
    }

    if (Test-Path -LiteralPath $logsDir) {
        $recentLogs = Get-ChildItem -LiteralPath $logsDir -File -Filter '*.log' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 5

        foreach ($log in $recentLogs) {
            $candidateLogs.Add([string]$log.FullName)
        }
    }

    $printedAnyLog = $false
    foreach ($logPath in ($candidateLogs | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $logPath)) {
            continue
        }

        $match = Select-String -Path $logPath -Pattern ([Regex]::Escape($ExecId)) -ErrorAction SilentlyContinue | Select-Object -Last 8
        if (-not $match) {
            continue
        }

        $printedAnyLog = $true
        Write-Host ("-- {0} (ultimas linhas do ExecId) --" -f (Split-Path -Leaf $logPath))
        foreach ($m in $match) { Write-Host $m.Line }
    }

    if (-not $printedAnyLog) {
        Write-Host '[WARN] Nenhuma linha do ExecId encontrada nos logs desta automacao.'
    }

    Write-Host ""
    return $exitCode
}

function Get-TaskScriptPath {
    param(
        [string]$RootPath,
        [object]$Config,
        [string]$TaskName
    )

    $task = @($Config.tasks | Where-Object { [string]$_.name -eq $TaskName }) | Select-Object -First 1
    if (-not $task) {
        throw "Tarefa '$TaskName' nao encontrada no config.json."
    }

    $scriptPath = [string]$task.scriptPath
    if ([string]::IsNullOrWhiteSpace($scriptPath)) {
        throw "Campo scriptPath vazio para a tarefa '$TaskName'."
    }

    if (-not [System.IO.Path]::IsPathRooted($scriptPath)) {
        $scriptPath = Join-Path $RootPath $scriptPath
    }

    return $scriptPath
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

$configPath = Join-Path $BasePath 'config.json'
if (-not (Test-Path -LiteralPath $configPath)) {
    throw "config.json nao encontrado: $configPath"
}

$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json

$results = [ordered]@{}
$results['RE'] = Start-Automacao -Name 'Receitas Emitidas' -ScriptPath (Get-TaskScriptPath -RootPath $BasePath -Config $config -TaskName 'Receitas Emitidas') -ExecId 'BATCH_FINAL_RE_20260329'
$results['RB'] = Start-Automacao -Name 'Receitas Bloqueadas' -ScriptPath (Get-TaskScriptPath -RootPath $BasePath -Config $config -TaskName 'Receitas Bloqueadas') -ExecId 'BATCH_FINAL_RB_20260329' -TimeoutSec 420
$results['MT'] = Start-Automacao -Name 'Montagem Terceirizados' -ScriptPath (Get-TaskScriptPath -RootPath $BasePath -Config $config -TaskName 'Montagem Terceirizados') -ExecId 'BATCH_FINAL_MT_20260329'

Write-Host '=== RESUMO FINAL ==='
foreach ($kv in $results.GetEnumerator()) {
    Write-Host ($kv.Key + '=' + $kv.Value)
}
