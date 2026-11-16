$here = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($here)) {
    $here = Split-Path -Parent $PSCommandPath
}

$sut = (Split-Path -Parent $here) + "\Lib-Logging.psm1"

Import-Module $sut -Force

Describe "Lib-Logging Tests" {
    Context "Write-AutomacaoLog" {
        It "Should execute without errors" {
            $tempLog = Join-Path $TestDrive "test.log"
            { Write-AutomacaoLog -Message "Test message" -Level "INFO" -LogPath $tempLog } | Should -Not -Throw
            if (Test-Path $tempLog) { Remove-Item $tempLog -Force }
        }
    }

    Context "Get-ForwardedLogLevel" {
        # Centralizada a partir de tres copias em run.ps1 (achado A1 da revisao
        # arquitetural). Os run.ps1 chamam com -Msg, por isso o alias e testado.
        It "Normaliza ERROR para ERRO" {
            Get-ForwardedLogLevel -Message "[ERROR] falha na extracao" | Should -Be "ERRO"
        }

        It "Aceita ERRO ja no padrao do hub" {
            Get-ForwardedLogLevel -Message "[ERRO] falha" | Should -Be "ERRO"
        }

        It "Detecta o marcador sem diferenciar maiuscula de minuscula" {
            Get-ForwardedLogLevel -Message "[warn] atencao" | Should -Be "WARN"
        }

        It "Preserva DEBUG" {
            Get-ForwardedLogLevel -Message "[DEBUG] detalhe" | Should -Be "DEBUG"
        }

        It "Usa o fallback quando a linha nao tem marcador" {
            Get-ForwardedLogLevel -Message "linha sem marcador" -Fallback "WARN" | Should -Be "WARN"
        }

        It "Usa INFO como fallback padrao em linha vazia" {
            Get-ForwardedLogLevel -Message "" | Should -Be "INFO"
        }

        It "Aceita o alias -Msg usado pelos run.ps1" {
            Get-ForwardedLogLevel -Msg "[ERROR] via alias" | Should -Be "ERRO"
        }
    }

    Context "Get-AutomationExitStatus" {
        # Extraida de Exit-AutomationWithCode, que centraliza a classificacao
        # que tinha divergido entre 4 run.ps1 (achado de qualidade da revisao
        # arquitetural): -eq 0, -eq 0 -or -eq 2, -in $NonFailureCodes.
        It "Codigo 0 sem NonFailureCodes explicito (padrao) e sucesso" {
            Get-AutomationExitStatus -Code 0 | Should -BeTrue
        }

        It "Codigo diferente de 0 sem NonFailureCodes explicito e falha" {
            Get-AutomationExitStatus -Code 1 | Should -BeFalse
        }

        It "Padrao de Receitas Bloqueadas/OBs Paradas Fase: 0 e 2 sao sucesso" {
            Get-AutomationExitStatus -Code 2 -NonFailureCodes @(0, 2) | Should -BeTrue
            Get-AutomationExitStatus -Code 9 -NonFailureCodes @(0, 2) | Should -BeFalse
        }

        It "Padrao de OBs Fluxo Sem Tingimento: 22 (canal pendente) e sucesso" {
            Get-AutomationExitStatus -Code 22 -NonFailureCodes @(0, 2, 22) | Should -BeTrue
        }

        It "Codigo fora da lista de NonFailureCodes e sempre falha" {
            Get-AutomationExitStatus -Code 22 -NonFailureCodes @(0, 2) | Should -BeFalse
        }
    }

    Context "Exit-AutomationWithCode (EndMessage)" {
        # Exit-AutomationWithCode chama `exit`, entao cada teste roda em processo
        # filho (powershell.exe) para nao encerrar o runner do Pester. Cobre o
        # achado de que a consolidacao (PR chore/consolida-exit-withcode-run-ps1)
        # hardcodeou "FIM - Finalizado. ExitCode=..." para os 4 run.ps1, mudando
        # silenciosamente o texto que OBs Fluxo Sem Tingimento/run.ps1 e OBs
        # Paradas Fase/run.ps1 usavam ("FIM - ExitCode=...", sem "Finalizado.").
        BeforeAll {
            $script:modulePathForExitTests = (Split-Path -Parent $PSScriptRoot) + "\Lib-Logging.psm1"

            function Invoke-ExitAutomationWithCode {
                param(
                    [Parameter(Mandatory)][int]$Code,
                    [string]$EndMessageArg = ""
                )
                $logPath = Join-Path $TestDrive ("exit-{0}.log" -f ([guid]::NewGuid()))
                $scriptPath = Join-Path $TestDrive ("invoke-{0}.ps1" -f ([guid]::NewGuid()))
                $moduleLiteral = $script:modulePathForExitTests -replace "'", "''"
                $logLiteral = $logPath -replace "'", "''"
                $scriptContent = @"
Import-Module '$moduleLiteral' -Force
Exit-AutomationWithCode -Code $Code -ExecId 'test' -LogPath '$logLiteral' $EndMessageArg
"@
                Set-Content -LiteralPath $scriptPath -Value $scriptContent -Encoding UTF8

                $process = Start-Process -FilePath "powershell.exe" `
                    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $scriptPath) `
                    -Wait -PassThru -NoNewWindow

                $logContent = if (Test-Path -LiteralPath $logPath) { Get-Content -LiteralPath $logPath -Raw } else { "" }

                return [pscustomobject]@{
                    ExitCode = $process.ExitCode
                    Log      = $logContent
                }
            }
        }

        It "Sem -EndMessage preserva o texto legado de Receitas Bloqueadas/Emitidas" {
            $result = Invoke-ExitAutomationWithCode -Code 0
            $result.ExitCode | Should -Be 0
            $result.Log | Should -Match ([regex]::Escape("FIM - Finalizado. ExitCode=0"))
        }

        It "Com -EndMessage restaura o texto original de OBs Fluxo Sem Tingimento/OBs Paradas Fase" {
            $result = Invoke-ExitAutomationWithCode -Code 2 -EndMessageArg "-EndMessage 'FIM - ExitCode=2'"
            $result.ExitCode | Should -Be 2
            $result.Log | Should -Match ([regex]::Escape("FIM - ExitCode=2"))
            $result.Log | Should -Not -Match ([regex]::Escape("FIM - Finalizado."))
        }
    }

    Context "Test-AutomationPreFlight (Oracle)" {
        BeforeEach {
            # Isola o teste do .env real e do ambiente: sem ORACLE_CONNECT_STRING no processo e
            # com driver direto (ORACLE_DRIVER_MODE=queue no .env pularia o teste de TCP).
            Remove-Item Env:\ORACLE_CONNECT_STRING -ErrorAction SilentlyContinue
            $script:driverModeAnterior = $env:ORACLE_DRIVER_MODE
            $env:ORACLE_DRIVER_MODE = "thin"
            $script:logPreflight = Join-Path $TestDrive ("preflight-" + [guid]::NewGuid().ToString("N") + ".log")
            Mock Test-OracleTcpEndpoint -ModuleName Lib-Logging { return $true }
        }

        AfterEach {
            Remove-Item Env:\ORACLE_CONNECT_STRING -ErrorAction SilentlyContinue
            if ($null -eq $script:driverModeAnterior) { Remove-Item Env:\ORACLE_DRIVER_MODE -ErrorAction SilentlyContinue }
            else { $env:ORACLE_DRIVER_MODE = $script:driverModeAnterior }
        }

        It "Com -OracleHost de host simples sem alias, testa o proprio host na porta 1521" {
            Mock Resolve-OracleEndpoint -ModuleName Lib-Logging { return $null }

            $null = Test-AutomationPreFlight -ExecId "teste" -LogPath $script:logPreflight -CheckOracle -OracleHost "srv-oracle-teste"

            Should -Invoke Test-OracleTcpEndpoint -ModuleName Lib-Logging -Times 1 -Exactly -ParameterFilter {
                $Servidor -eq "srv-oracle-teste" -and $Porta -eq 1521
            }
        }

        It "Com ORACLE_CONNECT_STRING //host:porta/servico, nao avisa host nao configurado e testa o host real" {
            $env:ORACLE_CONNECT_STRING = "//banco.exemplo.local:1521/SVC"

            $null = Test-AutomationPreFlight -ExecId "teste" -LogPath $script:logPreflight -CheckOracle

            Should -Invoke Test-OracleTcpEndpoint -ModuleName Lib-Logging -Times 1 -Exactly -ParameterFilter {
                $Servidor -eq "banco.exemplo.local" -and $Porta -eq 1521
            }
        }

        It "Le ORACLE_CONNECT_STRING do .env via Get-EnvFileValue quando nao ha variavel de ambiente" {
            Mock Get-EnvFileValue -ModuleName Lib-Logging { return "banco.exemplo.local:1600/SVC" }

            $null = Test-AutomationPreFlight -ExecId "teste" -LogPath $script:logPreflight -CheckOracle

            Should -Invoke Get-EnvFileValue -ModuleName Lib-Logging -Times 1 -Exactly -ParameterFilter {
                $Key -eq "ORACLE_CONNECT_STRING"
            }
            Should -Invoke Test-OracleTcpEndpoint -ModuleName Lib-Logging -Times 1 -Exactly -ParameterFilter {
                $Servidor -eq "banco.exemplo.local" -and $Porta -eq 1600
            }
        }

        It "Sem ORACLE_CONNECT_STRING em lugar nenhum, avisa host nao configurado e nao testa TCP" {
            Mock Get-EnvFileValue -ModuleName Lib-Logging { return $null }

            $null = Test-AutomationPreFlight -ExecId "teste" -LogPath $script:logPreflight -CheckOracle

            Should -Invoke Test-OracleTcpEndpoint -ModuleName Lib-Logging -Times 0 -Exactly
        }
    }

    Context "Enter-AutomationLock (-LockKey)" {
        It "Serializa execucoes com ExecIds distintos usando o mesmo LockKey" {
            $moduleLiteral = ((Split-Path -Parent $PSScriptRoot) + "\Lib-Logging.psm1") -replace "'", "''"
            $lockKey = "UNIT_LOCK_" + [guid]::NewGuid().ToString("N")
            $readyFlag = Join-Path $TestDrive ("lock-ready-" + [guid]::NewGuid().ToString("N") + ".txt")
            $releaseFlag = Join-Path $TestDrive ("lock-release-" + [guid]::NewGuid().ToString("N") + ".txt")

            $holderScript = Join-Path $TestDrive ("holder-" + [guid]::NewGuid().ToString("N") + ".ps1")
            $contenderScript = Join-Path $TestDrive ("contender-" + [guid]::NewGuid().ToString("N") + ".ps1")

            $holderCode = @"
Import-Module '$moduleLiteral' -Force
Enter-AutomationLock -ExecId 'exec-1' -LockKey '$lockKey' -TimeoutMs 2000 | Out-Null
Set-Content -LiteralPath '$($readyFlag -replace "'", "''")' -Value 'ready' -Encoding UTF8
try {
    `$deadline = (Get-Date).AddSeconds(10)
    while (-not (Test-Path -LiteralPath '$($releaseFlag -replace "'", "''")') -and (Get-Date) -lt `$deadline) {
        Start-Sleep -Milliseconds 100
    }
} finally {
    Exit-AutomationLock -ExecId 'exec-1' -LockKey '$lockKey'
}
"@
            Set-Content -LiteralPath $holderScript -Value $holderCode -Encoding UTF8

            $contenderCode = @"
Import-Module '$moduleLiteral' -Force
Enter-AutomationLock -ExecId 'exec-2' -LockKey '$lockKey' -TimeoutMs 150 | Out-Null
Exit-AutomationLock -ExecId 'exec-2' -LockKey '$lockKey'
"@
            Set-Content -LiteralPath $contenderScript -Value $contenderCode -Encoding UTF8

            $holderProc = Start-Process -FilePath "powershell.exe" `
                -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $holderScript) `
                -PassThru -NoNewWindow

            try {
                $waitDeadline = (Get-Date).AddSeconds(8)
                while (-not (Test-Path -LiteralPath $readyFlag) -and (Get-Date) -lt $waitDeadline) {
                    Start-Sleep -Milliseconds 50
                }
                (Test-Path -LiteralPath $readyFlag) | Should -BeTrue

                # Mesmo com ExecId diferente ('exec-2'), a mesma chave LockKey bloqueia
                $contenderSame = Start-Process -FilePath "powershell.exe" `
                    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $contenderScript) `
                    -Wait -PassThru -NoNewWindow
                $contenderSame.ExitCode | Should -Not -Be 0

                # Chave distinta nao sofre contencao
                Enter-AutomationLock -ExecId "exec-3" -LockKey ($lockKey + "_OUTRA") -TimeoutMs 500 | Should -BeTrue
                Exit-AutomationLock -ExecId "exec-3" -LockKey ($lockKey + "_OUTRA")
            } finally {
                Set-Content -LiteralPath $releaseFlag -Value "go" -Encoding UTF8
                if ($holderProc -and -not $holderProc.HasExited) {
                    $null = $holderProc.WaitForExit(10000)
                }
            }
        }
    }

    Context "Test-OracleQueueWorkerAlive e PreFlight em modo queue" {
        BeforeAll {
            Import-Module ((Split-Path -Parent $PSScriptRoot) + "\Lib-Oracle.psm1") -Force
        }

        It "identifica heartbeat fresco como ativo e stale/ausente como offline" {
            $queueDir = Join-Path $TestDrive "fila_pedidos"
            New-Item -ItemType Directory -Path $queueDir -Force | Out-Null
            $hbPath = Join-Path $queueDir "_worker_heartbeat.json"

            # Sem arquivo: offline
            $resAusente = Test-OracleQueueWorkerAlive -QueueDir $queueDir
            $resAusente.Alive | Should -BeFalse

            # Heartbeat fresco: alive
            '{"version":"2.6.1","state":"idle","oracle_ok":true}' | Set-Content -LiteralPath $hbPath -Encoding UTF8
            $resVivo = Test-OracleQueueWorkerAlive -QueueDir $queueDir
            $resVivo.Alive | Should -BeTrue
            $resVivo.Version | Should -Be "2.6.1"

            # Heartbeat vencido (> 45s): offline
            (Get-Item -LiteralPath $hbPath).LastWriteTime = (Get-Date).AddMinutes(-5)
            $resVelho = Test-OracleQueueWorkerAlive -QueueDir $queueDir -MaxAgeSeconds 45
            $resVelho.Alive | Should -BeFalse
        }

        It "marca heartbeat expirado como offline mesmo com req_*.proc orfao" {
            $queueDir = Join-Path $TestDrive "fila_orfao"
            New-Item -ItemType Directory -Path $queueDir -Force | Out-Null
            $hbPath = Join-Path $queueDir "_worker_heartbeat.json"
            $procPath = Join-Path $queueDir "req_orfao_001.proc"

            '{"version":"2.6.1","state":"busy","oracle_ok":true}' | Set-Content -LiteralPath $hbPath -Encoding UTF8
            '{"id":"req_orfao_001"}' | Set-Content -LiteralPath $procPath -Encoding UTF8

            # Dentro do BusyMaxAgeSeconds (120s <= 240s): ainda considerado ativo
            (Get-Item -LiteralPath $hbPath).LastWriteTime = (Get-Date).AddMinutes(-2)
            $resBusy = Test-OracleQueueWorkerAlive -QueueDir $queueDir -MaxAgeSeconds 45 -BusyMaxAgeSeconds 240
            $resBusy.Alive | Should -BeTrue

            # Acima do BusyMaxAgeSeconds (600s > 240s): offline mesmo com .proc orfao
            (Get-Item -LiteralPath $hbPath).LastWriteTime = (Get-Date).AddMinutes(-10)
            $resOrfao = Test-OracleQueueWorkerAlive -QueueDir $queueDir -MaxAgeSeconds 45 -BusyMaxAgeSeconds 240
            $resOrfao.Alive | Should -BeFalse
            $resOrfao.Reason | Should -Match "heartbeat expirado"
        }

        It "heartbeat ilegivel (regravacao em curso) usa a idade do arquivo, como o cliente Python" {
            $queueDir = Join-Path $TestDrive "fila_hb_corrompido"
            New-Item -ItemType Directory -Path $queueDir -Force | Out-Null
            $hbPath = Join-Path $queueDir "_worker_heartbeat.json"
            '{"version":"2.6.1","state":' | Set-Content -LiteralPath $hbPath -Encoding UTF8

            $res = Test-OracleQueueWorkerAlive -QueueDir $queueDir
            $res.Reachable | Should -BeTrue
            $res.Source | Should -Be "heartbeat"
            $res.Alive | Should -BeTrue
            $res.State | Should -BeNullOrEmpty

            (Get-Item -LiteralPath $hbPath).LastWriteTimeUtc = [DateTime]::UtcNow.AddSeconds(-600)
            $velho = Test-OracleQueueWorkerAlive -QueueDir $queueDir
            $velho.Alive | Should -BeFalse
            $velho.Reason | Should -Match "heartbeat expirado"
        }

        It "Test-AutomationPreFlight -CheckOracle em modo queue valida worker vivo e reprova offline" {
            $queueDir = Join-Path $TestDrive "fila_preflight"
            New-Item -ItemType Directory -Path $queueDir -Force | Out-Null
            $hbPath = Join-Path $queueDir "_worker_heartbeat.json"
            $logPf = Join-Path $TestDrive ("pf-queue-" + [guid]::NewGuid().ToString("N") + ".jsonl")

            $prevMode = $env:ORACLE_DRIVER_MODE
            $prevDir = $env:ORACLE_QUEUE_DIR
            try {
                $env:ORACLE_DRIVER_MODE = "queue"
                $env:ORACLE_QUEUE_DIR = $queueDir

                # Worker offline (sem heartbeat)
                (Test-AutomationPreFlight -ExecId "pf-q-off" -LogPath $logPf -CheckOracle) | Should -BeFalse

                # Worker vivo (heartbeat fresco)
                '{"version":"2.6.1","state":"idle","oracle_ok":true}' | Set-Content -LiteralPath $hbPath -Encoding UTF8
                (Test-AutomationPreFlight -ExecId "pf-q-on" -LogPath $logPf -CheckOracle) | Should -BeTrue
            }
            finally {
                if ($null -eq $prevMode) { Remove-Item Env:\ORACLE_DRIVER_MODE -ErrorAction SilentlyContinue } else { $env:ORACLE_DRIVER_MODE = $prevMode }
                if ($null -eq $prevDir) { Remove-Item Env:\ORACLE_QUEUE_DIR -ErrorAction SilentlyContinue } else { $env:ORACLE_QUEUE_DIR = $prevDir }
            }
        }

        It "Get-OraclePreFlightExitCode retorna 26 para queue offline e 9 para vivo ou outro driver" {
            $queueDir = Join-Path $TestDrive "fila_exitcode"
            New-Item -ItemType Directory -Path $queueDir -Force | Out-Null
            $hbPath = Join-Path $queueDir "_worker_heartbeat.json"

            $prevMode = $env:ORACLE_DRIVER_MODE
            $prevDir = $env:ORACLE_QUEUE_DIR
            try {
                $env:ORACLE_DRIVER_MODE = "queue"
                $env:ORACLE_QUEUE_DIR = $queueDir

                Get-OraclePreFlightExitCode | Should -Be 26

                '{"version":"2.6.1","state":"idle","oracle_ok":true}' | Set-Content -LiteralPath $hbPath -Encoding UTF8
                Get-OraclePreFlightExitCode | Should -Be 9

                $env:ORACLE_DRIVER_MODE = "thin"
                Get-OraclePreFlightExitCode | Should -Be 9
            }
            finally {
                if ($null -eq $prevMode) { Remove-Item Env:\ORACLE_DRIVER_MODE -ErrorAction SilentlyContinue } else { $env:ORACLE_DRIVER_MODE = $prevMode }
                if ($null -eq $prevDir) { Remove-Item Env:\ORACLE_QUEUE_DIR -ErrorAction SilentlyContinue } else { $env:ORACLE_QUEUE_DIR = $prevDir }
            }
        }
    }

    Context "Get-OracleQueueServerNowUtc (relogio do servidor da fila)" {
        It "devolve um instante UTC proximo do relogio local e apaga a sonda" {
            $fila = Join-Path $TestDrive "fila_relogio"
            New-Item -ItemType Directory -Path $fila -Force | Out-Null

            $agora = Get-OracleQueueServerNowUtc -QueueDir $fila

            $agora.Kind | Should -Be ([System.DateTimeKind]::Utc)
            [math]::Abs(([DateTime]::UtcNow - $agora).TotalMinutes) | Should -BeLessThan 5
            @(Get-ChildItem -LiteralPath $fila -Filter "_clock_probe_*" -ErrorAction SilentlyContinue).Count | Should -Be 0
        }

        It "cai para UtcNow quando a pasta da fila nao existe" {
            $inexistente = Join-Path $TestDrive "pasta_que_nao_existe"

            $agora = Get-OracleQueueServerNowUtc -QueueDir $inexistente

            $agora.Kind | Should -Be ([System.DateTimeKind]::Utc)
            [math]::Abs(([DateTime]::UtcNow - $agora).TotalMinutes) | Should -BeLessThan 5
        }
    }

    Context "Invoke-LogRotation" {
        It "remove registros expirados tanto com campo ts quanto com timestamp" {
            $rotLog = Join-Path $TestDrive ("rot-" + [guid]::NewGuid().ToString("N") + ".jsonl")
            $oldIso = (Get-Date).Date.AddDays(-20).AddHours(10).ToString("yyyy-MM-ddTHH:mm:ssZ")
            $newIso = (Get-Date).Date.AddHours(10).ToString("yyyy-MM-ddTHH:mm:ssZ")

            @(
                "{`"ts`":`"${oldIso}`",`"message`":`"antigo_ts`"}"
                "{`"timestamp`":`"${oldIso}`",`"message`":`"antigo_timestamp`"}"
                "{`"ts`":`"${newIso}`",`"message`":`"novo_ts`"}"
                "{`"timestamp`":`"${newIso}`",`"message`":`"novo_timestamp`"}"
            ) | Set-Content -LiteralPath $rotLog -Encoding UTF8

            Invoke-LogRotation -LogPath $rotLog -KeepDays 15

            $remaining = @(Get-Content -LiteralPath $rotLog | Where-Object { $_.Trim() })
            $remaining.Count | Should -Be 2
            ($remaining -join "`n") | Should -Match "novo_ts"
            ($remaining -join "`n") | Should -Match "novo_timestamp"
            ($remaining -join "`n") | Should -Not -Match "antigo_"
        }
    }
}
