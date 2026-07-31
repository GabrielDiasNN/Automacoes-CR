$here = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($here)) {
    $here = Split-Path -Parent $PSCommandPath
}

$sut = (Split-Path -Parent $here) + "\Lib-OrchestratorRuntime.psm1"

Import-Module $sut -Force

# Regressao de 31/07/2026: o filtro de Stop-OrchestratorProcesses tinha os ramos
# "uvicorn" e "worker.py" FORA do escopo do $rootPattern (alternativas soltas de
# um -or). Qualquer processo Python da maquina com essas palavras na linha de
# comando era encerrado com -Force, inclusive de outros projetos no mesmo
# servidor — o oposto do que o comentario em Start-Orchestrator.ps1 promete.

function New-FakeProcess {
    param(
        [int]$ProcessId,
        [string]$Name,
        [string]$CommandLine,
        [string]$ExecutablePath
    )
    [PSCustomObject]@{
        ProcessId      = $ProcessId
        Name           = $Name
        CommandLine    = $CommandLine
        ExecutablePath = $ExecutablePath
    }
}

Describe "Get-OrchestratorEnvValue" {
    # Regressao de 31/07/2026: o mesmo .env era lido por parsers com regras
    # incompativeis. Esta funcao — designada no CLAUDE.md como fonte unica para
    # Infrastructure/ — NAO removia comentario inline, enquanto
    # ConvertFrom-EnvLine (Lib-Config.psm1) removia. O .env do projeto ja contem
    # as duas formas que fazem os parsers divergirem.
    BeforeAll {
        $script:EnvDir = Join-Path ([System.IO.Path]::GetTempPath()) ("envtest-" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Path $script:EnvDir | Out-Null
        @(
            'CONTATO=5511999999999         # Nome Legivel'
            'SENHA=abc#123'
            'CITADO="valor entre aspas"'
            '   # comentario indentado'
            'SIMPLES=valor'
        ) | Set-Content -Path (Join-Path $script:EnvDir ".env") -Encoding UTF8
    }

    AfterAll {
        if (Test-Path $script:EnvDir) { Remove-Item $script:EnvDir -Recurse -Force }
    }

    It "remove comentario inline apos o valor" {
        Get-OrchestratorEnvValue -ProjectRoot $script:EnvDir -Key "CONTATO" | Should -Be "5511999999999"
    }

    It "preserva '#' colado ao valor (senha)" {
        Get-OrchestratorEnvValue -ProjectRoot $script:EnvDir -Key "SENHA" | Should -Be "abc#123"
    }

    It "remove aspas das pontas" {
        Get-OrchestratorEnvValue -ProjectRoot $script:EnvDir -Key "CITADO" | Should -Be "valor entre aspas"
    }

    It "devolve o default para chave ausente" {
        Get-OrchestratorEnvValue -ProjectRoot $script:EnvDir -Key "NAO_EXISTE" -Default "fallback" | Should -Be "fallback"
    }

    It "le valor simples" {
        Get-OrchestratorEnvValue -ProjectRoot $script:EnvDir -Key "SIMPLES" | Should -Be "valor"
    }
}

Describe "Stop-OrchestratorProcesses" {
    BeforeAll {
        # Raizes sinteticas montadas em runtime — o gate de portabilidade proibe
        # caminho absoluto literal, e o teste precisa comparar caminhos absolutos.
        $script:Drive = (Split-Path -Qualifier ([System.IO.Path]::GetTempPath()))
        $script:ProjectRoot = Join-Path $script:Drive "Projeto"
        $script:OutroProjeto = Join-Path $script:Drive "OutroProjeto"
        $script:PythonSistema = Join-Path $script:Drive "PythonSistema"
    }

    Context "Escopo do projeto" {
        It "NAO encerra uvicorn de outro projeto" {
            InModuleScope Lib-OrchestratorRuntime -Parameters @{ Root = $script:ProjectRoot; Outro = $script:OutroProjeto; PySis = $script:PythonSistema } {
                param($Root, $Outro, $PySis)
                Mock Get-CimInstance {
                    @([PSCustomObject]@{
                            ProcessId      = 4321
                            Name           = "python.exe"
                            CommandLine    = "$(Join-Path $Outro '.venv\Scripts\python.exe') -m uvicorn app.main:app"
                            ExecutablePath = (Join-Path $Outro ".venv\Scripts\python.exe")
                        })
                }
                Mock Stop-Process {}

                Stop-OrchestratorProcesses -ProjectRoot $Root | Should -Be 0
                Should -Invoke Stop-Process -Times 0 -Exactly
            }
        }

        It "NAO encerra worker.py de outro projeto" {
            InModuleScope Lib-OrchestratorRuntime -Parameters @{ Root = $script:ProjectRoot; Outro = $script:OutroProjeto; PySis = $script:PythonSistema } {
                param($Root, $Outro, $PySis)
                Mock Get-CimInstance {
                    @([PSCustomObject]@{
                            ProcessId      = 4322
                            Name           = "python.exe"
                            CommandLine    = "python worker.py"
                            ExecutablePath = (Join-Path $PySis "python.exe")
                        })
                }
                Mock Stop-Process {}

                Stop-OrchestratorProcesses -ProjectRoot $Root | Should -Be 0
                Should -Invoke Stop-Process -Times 0 -Exactly
            }
        }

        It "encerra uvicorn DESTE projeto" {
            InModuleScope Lib-OrchestratorRuntime -Parameters @{ Root = $script:ProjectRoot; Outro = $script:OutroProjeto; PySis = $script:PythonSistema } {
                param($Root, $Outro, $PySis)
                Mock Get-CimInstance {
                    @([PSCustomObject]@{
                            ProcessId      = 100
                            Name           = "python.exe"
                            CommandLine    = "$(Join-Path $Root '.venv\Scripts\python.exe') -m uvicorn app.main:app --port 8000"
                            ExecutablePath = (Join-Path $Root ".venv\Scripts\python.exe")
                        })
                }
                Mock Stop-Process {}

                Stop-OrchestratorProcesses -ProjectRoot $Root | Should -Be 1
                Should -Invoke Stop-Process -Times 1 -Exactly
            }
        }

        It "encerra worker.py iniciado com caminho relativo (escopo pelo ExecutablePath do venv)" {
            InModuleScope Lib-OrchestratorRuntime -Parameters @{ Root = $script:ProjectRoot; Outro = $script:OutroProjeto; PySis = $script:PythonSistema } {
                param($Root, $Outro, $PySis)
                Mock Get-CimInstance {
                    @([PSCustomObject]@{
                            ProcessId      = 101
                            Name           = "python.exe"
                            CommandLine    = "python.exe worker.py"
                            ExecutablePath = (Join-Path $Root ".venv\Scripts\python.exe")
                        })
                }
                Mock Stop-Process {}

                Stop-OrchestratorProcesses -ProjectRoot $Root | Should -Be 1
                Should -Invoke Stop-Process -Times 1 -Exactly
            }
        }
    }

    Context "Alvo dentro do projeto" {
        It "NAO encerra pytest do desenvolvedor rodando sobre o repositorio" {
            InModuleScope Lib-OrchestratorRuntime -Parameters @{ Root = $script:ProjectRoot; Outro = $script:OutroProjeto; PySis = $script:PythonSistema } {
                param($Root, $Outro, $PySis)
                Mock Get-CimInstance {
                    @([PSCustomObject]@{
                            ProcessId      = 200
                            Name           = "python.exe"
                            CommandLine    = "$(Join-Path $Root '.venv\Scripts\python.exe') -m pytest tests/"
                            ExecutablePath = (Join-Path $Root ".venv\Scripts\python.exe")
                        })
                }
                Mock Stop-Process {}

                Stop-OrchestratorProcesses -ProjectRoot $Root | Should -Be 0
                Should -Invoke Stop-Process -Times 0 -Exactly
            }
        }
    }

    Context "Ramo PowerShell" {
        It "encerra MonitorAutomacoes.ps1 deste projeto" {
            InModuleScope Lib-OrchestratorRuntime -Parameters @{ Root = $script:ProjectRoot; Outro = $script:OutroProjeto; PySis = $script:PythonSistema } {
                param($Root, $Outro, $PySis)
                Mock Get-CimInstance {
                    @([PSCustomObject]@{
                            ProcessId      = 300
                            Name           = "powershell.exe"
                            CommandLine    = "powershell -File $(Join-Path $Root 'Infrastructure\MonitorAutomacoes.ps1')"
                            ExecutablePath = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
                        })
                }
                Mock Stop-Process {}

                Stop-OrchestratorProcesses -ProjectRoot $Root | Should -Be 1
                Should -Invoke Stop-Process -Times 1 -Exactly
            }
        }

        It "so encerra Start-Orchestrator.ps1 com -IncludeStarter" {
            InModuleScope Lib-OrchestratorRuntime -Parameters @{ Root = $script:ProjectRoot; Outro = $script:OutroProjeto; PySis = $script:PythonSistema } {
                param($Root, $Outro, $PySis)
                Mock Get-CimInstance {
                    @([PSCustomObject]@{
                            ProcessId      = 301
                            Name           = "powershell.exe"
                            CommandLine    = "powershell -File $(Join-Path $Root 'Infrastructure\Start-Orchestrator.ps1')"
                            ExecutablePath = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
                        })
                }
                Mock Stop-Process {}

                Stop-OrchestratorProcesses -ProjectRoot $Root | Should -Be 0
                Stop-OrchestratorProcesses -ProjectRoot $Root -IncludeStarter | Should -Be 1
            }
        }
    }
}
