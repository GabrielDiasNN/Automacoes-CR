$ErrorActionPreference = "Stop"

function Run-Automacao {
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

$results = [ordered]@{}
$results['RE'] = Run-Automacao -Name 'Receitas Emitidas' -Dir 'C:\Automacoes\Receitas Emitidas' -ExecId 'BATCH_FINAL_RE_20260329'
$results['RB'] = Run-Automacao -Name 'Receitas Bloqueadas' -Dir 'C:\Automacoes\Receitas Bloqueadas' -ExecId 'BATCH_FINAL_RB_20260329' -TimeoutSec 420
$results['MT'] = Run-Automacao -Name 'Montagem Terceirizados' -Dir 'C:\Automacoes\Montagem de Terceirizados' -ExecId 'BATCH_FINAL_MT_20260329'

Write-Host '=== RESUMO FINAL ==='
foreach ($kv in $results.GetEnumerator()) {
    Write-Host ($kv.Key + '=' + $kv.Value)
}
