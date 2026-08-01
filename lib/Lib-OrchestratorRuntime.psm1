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
            $value = $parts[1].Trim()
            # Remove comentario inline, MESMA regra de ConvertFrom-EnvLine em
            # Lib-Config.psm1 (31/07/2026). Ate entao os parsers divergiam: esta
            # funcao — designada no CLAUDE.md como fonte unica para
            # Infrastructure/ — devolvia "5511999999999   # Nome Legivel"
            # INTEIRO, enquanto o parser das automacoes devolvia so o numero.
            # O `.env` atual ja contem as duas formas que fazem isso divergir.
            # A regex exige espaco antes do '#', entao valor com '#' colado
            # (senha) sobrevive intacto.
            $value = [regex]::Replace($value, '\s+#.*$', '').Trim()
            return $value.Trim('"').Trim("'")
        }
    }
    return $Default
}

function Request-OrchestratorGracefulStop {
    <#
    .SYNOPSIS
        Pede ao worker que encerre sozinho e aguarda ate o prazo.
    .DESCRIPTION
        No Windows, Stop-Process -Force e TerminateProcess: NAO entrega sinal.
        Todo o caminho de encerramento controlado do worker (handler de
        SIGINT/SIGTERM, shutdown_event, _terminate_active_processes,
        SHUTDOWN_GRACE_SECONDS, finalize_reboot_interrupted_task) era portanto
        inalcancavel pelo caminho canonico de restart/recover — os
        powershell.exe filhos ficavam orfaos rodando contra Oracle/WhatsApp sem
        supervisor, e a execucao seguia RUNNING ate o _cleanup_zombie_tasks do
        boot seguinte.

        Esta funcao cria o sentinela lido pelo laco principal do worker
        (SHUTDOWN_SENTINEL_PATH em worker.py) e espera. E DELIBERADAMENTE
        separada de Stop-OrchestratorProcesses: aquela permanece uma operacao
        pura de encerramento, sem espera embutida, e continua rapida de testar.
        O kill forcado segue como fallback para o worker que nao respeitar o
        prazo.
    .OUTPUTS
        [bool] $true se o worker encerrou sozinho dentro do prazo.
    #>
    param(
        [Parameter(Mandatory)][string]$ProjectRoot,
        # Alinhado ao SHUTDOWN_GRACE_SECONDS = 30 do worker, com folga.
        [int]$TimeoutSeconds = 35
    )

    $sentinel = Join-Path $ProjectRoot "Orchestrator\worker.shutdown"
    $workerAtivo = {
        $null -ne (Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match "python" -and $_.CommandLine -match "worker\.py" })
    }

    if (-not (& $workerAtivo)) { return $true }

    try {
        New-Item -ItemType File -Path $sentinel -Force -ErrorAction Stop | Out-Null
    }
    catch [System.Exception] {
        Write-Verbose "Nao foi possivel criar o sentinela de parada: $($_.Exception.Message)"
        return $false
    }

    try {
        $prazo = (Get-Date).AddSeconds($TimeoutSeconds)
        while ((Get-Date) -lt $prazo) {
            Start-Sleep -Milliseconds 500
            if (-not (& $workerAtivo)) { return $true }
        }
        return $false
    }
    finally {
        # O sentinela precisa sumir de qualquer forma, ou o proximo worker
        # encerraria assim que subisse.
        if (Test-Path $sentinel) { Remove-Item $sentinel -Force -ErrorAction SilentlyContinue }
    }
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
        if ($_.ProcessId -eq $currentPid -or $null -eq $_.CommandLine) { return $false }

        # ESCOPO OBRIGATÓRIO — o processo precisa pertencer a ESTE projeto.
        # Até 31/07/2026 os ramos "uvicorn" e "worker.py" eram alternativas
        # soltas de um -or, fora do escopo do $rootPattern: qualquer processo
        # Python da máquina com essas palavras na linha de comando era morto com
        # -Force, inclusive de outros projetos no mesmo servidor.
        # A CommandLine nem sempre cita o caminho do projeto (worker iniciado
        # com cwd relativo), mas o interpretador vem do .venv da RAIZ do
        # repositório — então ExecutablePath fecha essa lacuna sem reabrir o
        # escopo para processos de terceiros.
        $noProjeto = ($_.CommandLine -match $rootPattern) -or
                     ($null -ne $_.ExecutablePath -and $_.ExecutablePath -match $rootPattern)
        if (-not $noProjeto) { return $false }

        if ($_.Name -match "python") {
            # Somente os dois processos que o Orchestrator gerencia. Casar
            # qualquer Python do projeto mataria também o pytest e o language
            # server de quem estivesse desenvolvendo no repositório.
            return ($_.CommandLine -match "uvicorn") -or ($_.CommandLine -match "worker\.py")
        }
        if ($_.Name -match "powershell|pwsh") {
            return ($_.CommandLine -match "MonitorAutomacoes\.ps1") -or
                   ($IncludeStarter -and $_.CommandLine -match "Start-Orchestrator\.ps1")
        }
        return $false
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

Export-ModuleMember -Function Get-OrchestratorRuntimeVersion, Get-OrchestratorEnvValue, Stop-OrchestratorProcesses, Request-OrchestratorGracefulStop
