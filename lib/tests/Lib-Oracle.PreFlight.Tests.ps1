Describe "Get-OraclePreFlightExitCode" {
    BeforeAll {
        $libDir = Split-Path -Parent $PSScriptRoot
        Import-Module (Join-Path $libDir "Lib-Logging.psm1") -Force
        Import-Module (Join-Path $libDir "Lib-Config.psm1") -Force
        Import-Module (Join-Path $libDir "Lib-Oracle.psm1") -Force
    }

    BeforeEach {
        # Preserva o ambiente do processo para restaurar em AfterEach.
        $script:envOriginal = @{
            ORACLE_DRIVER_MODE = [System.Environment]::GetEnvironmentVariable("ORACLE_DRIVER_MODE", "Process")
            ORACLE_QUEUE_DIR   = [System.Environment]::GetEnvironmentVariable("ORACLE_QUEUE_DIR", "Process")
        }
    }

    AfterEach {
        foreach ($nome in $script:envOriginal.Keys) {
            [System.Environment]::SetEnvironmentVariable($nome, $script:envOriginal[$nome], "Process")
        }
    }

    Context "modo queue" {
        It "retorna 9 (erro de configuracao) quando nenhuma pasta da fila foi resolvida" {
            [System.Environment]::SetEnvironmentVariable("ORACLE_DRIVER_MODE", "queue", "Process")
            Mock -ModuleName Lib-Oracle Test-OracleQueueWorkerAlive {
                return [pscustomobject]@{ Alive = $false; QueueDir = ""; Reason = "ORACLE_QUEUE_DIR nao configurado" }
            }

            Get-OraclePreFlightExitCode | Should -Be 9
        }

        It "retorna 26 sem ORACLE_QUEUE_DIR explicito quando a pasta vem do DEFAULT_QUEUE_DIR (cenario de producao)" {
            [System.Environment]::SetEnvironmentVariable("ORACLE_DRIVER_MODE", "queue", "Process")
            [System.Environment]::SetEnvironmentVariable("ORACLE_QUEUE_DIR", $null, "Process")
            Mock -ModuleName Lib-Oracle Get-EnvFileValue { return "" }
            Mock -ModuleName Lib-Oracle Test-OracleQueueWorkerAlive {
                return [pscustomobject]@{ Alive = $false; QueueDir = "\\servidor\fila_default"; Reason = "heartbeat expirado ha 300s (limite 45s)" }
            }

            Get-OraclePreFlightExitCode | Should -Be 26
            Assert-MockCalled -ModuleName Lib-Oracle Test-OracleQueueWorkerAlive -Times 1 -Exactly
        }

        It "retorna 26 (ORACLE_WORKER_OFFLINE) com pasta resolvida e worker morto" {
            [System.Environment]::SetEnvironmentVariable("ORACLE_DRIVER_MODE", "queue", "Process")
            Mock -ModuleName Lib-Oracle Test-OracleQueueWorkerAlive {
                return [pscustomobject]@{ Alive = $false; QueueDir = (Join-Path ([System.IO.Path]::GetTempPath()) "fila_teste_inexistente"); Reason = "pasta inacessivel (fila_teste_inexistente)" }
            }

            Get-OraclePreFlightExitCode | Should -Be 26
        }

        It "retorna 9 quando o worker esta vivo (a falha do pre-flight e outra)" {
            [System.Environment]::SetEnvironmentVariable("ORACLE_DRIVER_MODE", "queue", "Process")
            Mock -ModuleName Lib-Oracle Test-OracleQueueWorkerAlive {
                return [pscustomobject]@{ Alive = $true; QueueDir = (Join-Path ([System.IO.Path]::GetTempPath()) "fila"); Reason = "heartbeat ativo" }
            }

            Get-OraclePreFlightExitCode | Should -Be 9
        }

        It "le ORACLE_DRIVER_MODE do .env quando a variavel de processo esta vazia" {
            [System.Environment]::SetEnvironmentVariable("ORACLE_DRIVER_MODE", $null, "Process")
            Mock -ModuleName Lib-Oracle Get-EnvFileValue {
                if ($Key -eq "ORACLE_DRIVER_MODE") { return "queue" }
                return ""
            }
            Mock -ModuleName Lib-Oracle Test-OracleQueueWorkerAlive {
                return [pscustomobject]@{ Alive = $false; QueueDir = (Join-Path ([System.IO.Path]::GetTempPath()) "fila"); Reason = "sem heartbeat nem sinal do worker na fila" }
            }

            Get-OraclePreFlightExitCode | Should -Be 26
        }
    }

    Context "modo nao-queue" {
        It "retorna 9 para o modo '<modo>' sem consultar o worker" -ForEach @(
            @{ modo = "thick" }
            @{ modo = "bridge" }
            @{ modo = "auto" }
            @{ modo = "thin" }
        ) {
            [System.Environment]::SetEnvironmentVariable("ORACLE_DRIVER_MODE", $modo, "Process")
            [System.Environment]::SetEnvironmentVariable("ORACLE_QUEUE_DIR", (Join-Path ([System.IO.Path]::GetTempPath()) "fila_teste_inexistente"), "Process")
            Mock -ModuleName Lib-Oracle Test-OracleQueueWorkerAlive {
                return [pscustomobject]@{ Alive = $false; Reason = "worker offline" }
            }

            Get-OraclePreFlightExitCode | Should -Be 9
            Assert-MockCalled -ModuleName Lib-Oracle Test-OracleQueueWorkerAlive -Times 0 -Exactly
        }
    }
    Context "outros checks reprovados junto com o worker offline (OutrosChecks)" {
        BeforeEach {
            [System.Environment]::SetEnvironmentVariable("ORACLE_DRIVER_MODE", "queue", "Process")
            Mock -ModuleName Lib-Oracle Test-OracleQueueWorkerAlive {
                return [pscustomobject]@{ Alive = $false; QueueDir = "C:ila_teste"; Reason = "heartbeat expirado" }
            }
        }

        It "retorna 9 quando o worker esta offline e outro check reprovou (falha deterministica nao reenfileira)" {
            Get-OraclePreFlightExitCode -OutrosChecks { $false } | Should -Be 9
        }

        It "retorna 26 quando o worker esta offline e so o check do worker reprovou" {
            Get-OraclePreFlightExitCode -OutrosChecks { $true } | Should -Be 26
        }

        It "nao avalia OutrosChecks quando o worker esta vivo" {
            Mock -ModuleName Lib-Oracle Test-OracleQueueWorkerAlive {
                return [pscustomobject]@{ Alive = $true; QueueDir = "C:ila_teste"; Reason = "heartbeat ativo" }
            }
            $marcador = @{ chamadas = 0 }
            Get-OraclePreFlightExitCode -OutrosChecks { $marcador.chamadas++; $true } | Should -Be 9
            $marcador.chamadas | Should -Be 0
        }

        It "avalia OutrosChecks so uma vez quando o worker esta offline" {
            $marcador = @{ chamadas = 0 }
            Get-OraclePreFlightExitCode -OutrosChecks { $marcador.chamadas++; $true } | Should -Be 26
            $marcador.chamadas | Should -Be 1
        }

        It "trata excecao no bloco como reprovacao (9)" {
            Get-OraclePreFlightExitCode -OutrosChecks { throw "falha no check" } | Should -Be 9
        }

        It "bloco sem saida booleana conta como reprovacao (9)" {
            Get-OraclePreFlightExitCode -OutrosChecks { } | Should -Be 9
        }

        It "usa o ultimo valor booleano produzido pelo bloco" {
            Get-OraclePreFlightExitCode -OutrosChecks { "log qualquer"; $true } | Should -Be 26
        }

        It "sem o parametro mantem 26 com worker offline (compatibilidade)" {
            Get-OraclePreFlightExitCode | Should -Be 26
        }
    }
}
