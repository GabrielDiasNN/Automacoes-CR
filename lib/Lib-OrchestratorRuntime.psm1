<#
.SYNOPSIS
    Funções compartilhadas do ciclo de vida do Orchestrator (Infrastructure).
.DESCRIPTION
    Fonte única para: versão de runtime (lida de Orchestrator/app/constants.py),
    limpeza cirúrgica de processos (via CIM, pois Get-Process não expõe
    CommandLine no Windows PowerShell 5.1) e leitura de variáveis do .env.
#>

function Get-OrchestratorRuntimeVersion {
    param([Parameter(Mandatory)][string]$ProjectRoot)
    $constantsPath = Join-Path $ProjectRoot "Orchestrator\app\constants.py"
    try {
        $match = Select-String -Path $constantsPath -Pattern 'ORCHESTRATOR_VERSION\s*=\s*"([^"]+)"' -ErrorAction Stop | Select-Object -First 1
        if ($match) { return "v$($match.Matches[0].Groups[1].Value)" }
    } catch [System.Exception] {
        Write-Verbose "Não foi possível ler a versão em ${constantsPath}: $_"
    }
    return "v?"
}

function Get-OrchestratorEnvValue {
    param(
        [Parameter(Mandatory)][string]$ProjectRoot,
        [Parameter(Mandatory)][string]$Key,
        [string]$Default = ""
    )
    $envPath = Join-Path $ProjectRoot ".env"
    if (-not (Test-Path $envPath)) { return $Default }
    foreach ($line in (Get-Content $envPath)) {
        if ($line -notmatch '=' -or $line -match '^\s*#') { continue }
        $parts = $line.Split('=', 2)
        if ($parts[0].Trim() -eq $Key) {
            return $parts[1].Trim().Trim('"').Trim("'")
        }
    }
    return $Default
}

function Stop-OrchestratorProcesses {
    <#
    .SYNOPSIS
        Encerra processos Python/PowerShell do Orchestrator de forma cirúrgica.
    .DESCRIPTION
        Usa Get-CimInstance Win32_Process para inspecionar CommandLine —
        propriedade ausente nos objetos de Get-Process no PowerShell 5.1.
    #>
    param(
        [Parameter(Mandatory)][string]$ProjectRoot,
        [switch]$IncludeStarter
    )
    $rootPattern = [regex]::Escape($ProjectRoot)
    $currentPid = $PID
    $processes = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.ProcessId -ne $currentPid -and $null -ne $_.CommandLine -and (
            ($_.Name -match "python" -and (
                $_.CommandLine -match $rootPattern -or
                $_.CommandLine -match "uvicorn" -or
                $_.CommandLine -match "worker\.py"
            )) -or
            ($_.Name -match "powershell|pwsh" -and (
                $_.CommandLine -match "MonitorAutomacoes\.ps1" -or
                ($IncludeStarter -and $_.CommandLine -match "Start-Orchestrator\.ps1")
            ))
        )
    }
    foreach ($proc in $processes) {
        try {
            Write-Verbose ("Encerrando PID {0} ({1})" -f $proc.ProcessId, $proc.Name)
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
        } catch [System.Exception] {
            Write-Verbose ("Processo {0} já finalizado durante a limpeza." -f $proc.ProcessId)
        }
    }
    return @($processes).Count
}

Export-ModuleMember -Function Get-OrchestratorRuntimeVersion, Get-OrchestratorEnvValue, Stop-OrchestratorProcesses
