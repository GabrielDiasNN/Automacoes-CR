$here = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($here)) {
    $here = Split-Path -Parent $PSCommandPath
}

$libRoot = Split-Path -Parent $here
Import-Module (Join-Path $libRoot "Lib-Logging.psm1") -Force
Import-Module (Join-Path $libRoot "Lib-LogEvent.psm1") -Force

Describe "Lib-LogEvent" {

    BeforeAll {
        function Get-JsonlEvents {
            param([string]$Path)
            Get-Content -LiteralPath $Path | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json }
        }
    }

    BeforeEach {
        $env:HUB_TRACE_ID = $null
        $env:HUB_STEP = $null
    }

    AfterEach {
        Clear-HubLogContext
    }

    Context "New-HubTraceId / Resolve-HubTraceId" {
        It "gera trace_id no formato <slug>-<ISO8601Z>-<hex4>" {
            New-HubTraceId -Slug "orb" | Should -Match '^orb-\d{8}T\d{6}Z-[0-9a-f]{4}$'
        }

        It "Resolve-HubTraceId herda HUB_TRACE_ID quando presente" {
            $env:HUB_TRACE_ID = "herdado-abc"
            Resolve-HubTraceId -Slug "orb" | Should -Be "herdado-abc"
        }

        It "Resolve-HubTraceId cria novo quando a env esta ausente" {
            $env:HUB_TRACE_ID = $null
            Resolve-HubTraceId -Slug "orb" | Should -Match '^orb-'
        }
    }

    Context "Ciclo de vida completo" {
        It "emite execution.start/step.start/step.end/retry.attempt/execution.end validos" {
            $log = Join-Path $TestDrive "lifecycle.jsonl"
            Initialize-HubLogContext -Automation "OBs Restrição Branco" -ExecId "T1" `
                -TraceId "orb-20260827T070140Z-a4f2" -LogPath $log -Component "ps_script"

            Write-HubExecutionStart -Message "inicio"
            Write-HubStepStart -Step "extract" -Message "extraindo"
            Write-HubRetryAttempt -Step "extract" -Attempt 1 -MaxAttempts 3 -Message "tentativa 1"
            Write-HubStepEnd -Step "extract" -Ok $true -DurationMs 8300 -Message "120 lidas"
            Write-HubExecutionEnd -OutcomeCode 2 -OutcomeReason "idempotente" `
                -RecordCounts @{ read = 120; notified = 0 } -Message "fim"

            # ConvertFrom-Json coage strings ISO-8601 para [DateTime]; a checagem
            # de formato do 'ts' e feita no texto cru do arquivo.
            $rawLines = Get-Content -LiteralPath $log | Where-Object { $_.Trim() }
            foreach ($raw in $rawLines) {
                $raw | Should -Match '"ts":"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"'
            }

            $events = Get-JsonlEvents $log
            $events.Count | Should -Be 5
            $events[0].event | Should -Be "execution.start"
            $events[1].event | Should -Be "step.start"
            $events[2].event | Should -Be "retry.attempt"
            $events[2].attempt | Should -Be 1
            $events[2].max_attempts | Should -Be 3
            $events[3].event | Should -Be "step.end"
            $events[3].ok | Should -Be $true
            $events[3].duration_ms | Should -Be 8300
            $events[4].event | Should -Be "execution.end"
            $events[4].outcome_code | Should -Be 2
            $events[4].record_counts.read | Should -Be 120
            $events[4].steps.Count | Should -Be 1

            foreach ($e in $events) {
                $e.trace_id | Should -Be "orb-20260827T070140Z-a4f2"
                $e.automation | Should -Be "OBs Restrição Branco"
            }
        }

        It "execution.end deriva o nivel do outcome_code" {
            $log = Join-Path $TestDrive "levels.jsonl"
            Initialize-HubLogContext -Automation "A" -ExecId "T" -TraceId "t" -LogPath $log
            Write-HubExecutionEnd -OutcomeCode 4 -OutcomeReason "falhou"
            (Get-JsonlEvents $log)[-1].level | Should -Be "ERRO"
        }
    }

    Context "Mascaramento" {
        It "aplica Protect-SensitiveData na mensagem do evento" {
            $log = Join-Path $TestDrive "mask.jsonl"
            Initialize-HubLogContext -Automation "A" -ExecId "T" -TraceId "t" -LogPath $log
            Write-HubLogEvent -Event "log" -Level "WARN" -Message "conectar password=supersecret"
            $msg = (Get-JsonlEvents $log)[-1].message
            $msg | Should -Not -Match "supersecret"
            $msg | Should -Match "\[REDACTED\]"
        }
    }

    Context "Test-HubLogEnvelope / Write-HubForwardedLine" {
        BeforeEach {
            $script:log = Join-Path $TestDrive "forward.jsonl"
            Initialize-HubLogContext -Automation "A" -ExecId "T" -TraceId "t" -LogPath $script:log
        }

        It "reconhece um envelope completo" {
            $line = '{"ts":"2026-08-27T07:01:51Z","level":"INFO","component":"python_domain","event":"log","automation":"A","exec_id":"E","trace_id":"T","message":"m"}'
            Test-HubLogEnvelope -Line $line | Should -Be $true
        }

        It "rejeita texto avulso e JSON sem as chaves do envelope" {
            Test-HubLogEnvelope -Line "linha de texto" | Should -Be $false
            Test-HubLogEnvelope -Line '{"foo":1}' | Should -Be $false
        }

        It "encaminha o envelope verbatim (preservando ts/component do filho)" {
            $line = '{"ts":"2026-08-27T07:01:00Z","level":"INFO","component":"python_domain","event":"step.end","step":"extract","ok":true,"duration_ms":10,"automation":"A","exec_id":"E","trace_id":"T","message":"m"}'
            Write-HubForwardedLine -Line $line
            $ev = (Get-JsonlEvents $script:log)[-1]
            # component do FILHO preservado => encaminhamento verbatim (um
            # re-embrulho marcaria component=ps_script).
            $ev.component | Should -Be "python_domain"
            $ev.event | Should -Be "step.end"
        }

        It "embrulha texto avulso como evento log com nivel derivado" {
            Write-HubForwardedLine -Line "[WARN] barulho de lib" -Step "extract"
            $ev = (Get-JsonlEvents $script:log)[-1]
            $ev.event | Should -Be "log"
            $ev.level | Should -Be "WARN"
            $ev.step | Should -Be "extract"
        }
    }

    Context "Start-HubStep / Complete-HubStep" {
        It "mede a duracao e acumula o passo no execution.end" {
            $log = Join-Path $TestDrive "hubstep.jsonl"
            Initialize-HubLogContext -Automation "A" -ExecId "T" -TraceId "t" -LogPath $log
            Write-HubExecutionStart

            Start-HubStep -Step "extract" -Message "extraindo"
            $env:HUB_STEP | Should -Be "extract"
            Start-Sleep -Milliseconds 20
            Complete-HubStep -Ok $true -Message "ok"
            $env:HUB_STEP | Should -BeNullOrEmpty

            Write-HubExecutionEnd -OutcomeCode 0 -OutcomeReason "ok"

            $events = Get-JsonlEvents $log
            $end = $events | Where-Object { $_.event -eq "execution.end" }
            $end.steps.Count | Should -Be 1
            $end.steps[0].step | Should -Be "extract"
            $end.steps[0].duration_ms | Should -BeGreaterThan 0
        }

        It "Complete-HubStep sem passo ativo e no-op" {
            $log = Join-Path $TestDrive "hubstep-noop.jsonl"
            Initialize-HubLogContext -Automation "A" -ExecId "T" -TraceId "t" -LogPath $log
            { Complete-HubStep } | Should -Not -Throw
        }
    }

    Context "Get-HubRecordCounts" {
        It "le e coage record_counts de um result.json" {
            $rj = Join-Path $TestDrive "r.json"
            '{"rows":[],"record_counts":{"read":"120","notified":0,"skipped":118}}' | Set-Content -LiteralPath $rj -Encoding UTF8
            $c = Get-HubRecordCounts -Path $rj
            $c["read"] | Should -Be 120
            $c["notified"] | Should -Be 0
            $c["skipped"] | Should -Be 118
        }

        It "devolve null quando o arquivo nao existe ou nao tem o bloco" {
            Get-HubRecordCounts -Path (Join-Path $TestDrive "inexistente.json") | Should -BeNullOrEmpty
            $rj2 = Join-Path $TestDrive "r2.json"
            '{"rows":[]}' | Set-Content -LiteralPath $rj2 -Encoding UTF8
            Get-HubRecordCounts -Path $rj2 | Should -BeNullOrEmpty
        }
    }

    Context "Roteamento de Write-AutomacaoLog" {
        It "roteia para evento estruturado quando ha contexto ativo" {
            $log = Join-Path $TestDrive "route.jsonl"
            Initialize-HubLogContext -Automation "A" -ExecId "T" -TraceId "t" -LogPath $log
            Write-AutomacaoLog -Message "Etapa 1/3" -Level "INFO" -ExecId "T" -LogPath $log -Step "extract"
            $ev = (Get-JsonlEvents $log)[-1]
            $ev.event | Should -Be "log"
            $ev.step | Should -Be "extract"
            $ev.component | Should -Be "ps_script"
        }
    }

    Context "Etapa aberta no encerramento da execucao" {
        It "fecha a etapa pendente e a inclui em steps[] quando a execucao falha" {
            # Cenario real: um throw entre Start-HubStep e Complete-HubStep cai no
            # catch do run.ps1, que emite execution.end direto. A etapa em que a
            # execucao morreu nao podia sumir do rastro.
            $log = Join-Path $TestDrive "aberta-falha.jsonl"
            Initialize-HubLogContext -Automation "A" -ExecId "T" -TraceId "t" -LogPath $log
            Write-HubExecutionStart
            Start-HubStep -Step "extract"
            Complete-HubStep -Ok $true
            Start-HubStep -Step "dispatch" -Message "Envio de e-mail"
            # Sem Complete-HubStep: simula a excecao no meio do envio.
            Write-HubExecutionEnd -OutcomeCode 1 -OutcomeReason "ERRO FATAL"

            $eventos = @(Get-JsonlEvents $log)
            $fim = $eventos[-1]
            $fim.event | Should -Be "execution.end"
            @($fim.steps).Count | Should -Be 2
            @($fim.steps)[-1].step | Should -Be "dispatch"
            @($fim.steps)[-1].ok | Should -Be $false

            # O step.end da etapa interrompida precisa preceder o execution.end.
            $eventos[-2].event | Should -Be "step.end"
            $eventos[-2].step | Should -Be "dispatch"
        }

        It "fecha como bem-sucedida a etapa pendente quando o outcome e de sucesso" {
            $log = Join-Path $TestDrive "aberta-ok.jsonl"
            Initialize-HubLogContext -Automation "A" -ExecId "T" -TraceId "t" -LogPath $log
            Write-HubExecutionStart
            Start-HubStep -Step "commit"
            Write-HubExecutionEnd -OutcomeCode 0 -OutcomeReason "concluido"

            $fim = @(Get-JsonlEvents $log)[-1]
            @($fim.steps)[-1].step | Should -Be "commit"
            @($fim.steps)[-1].ok | Should -Be $true
        }

        It "nao altera steps[] quando nao ha etapa aberta" {
            $log = Join-Path $TestDrive "sem-aberta.jsonl"
            Initialize-HubLogContext -Automation "A" -ExecId "T" -TraceId "t" -LogPath $log
            Write-HubExecutionStart
            Start-HubStep -Step "extract"
            Complete-HubStep -Ok $true
            Write-HubExecutionEnd -OutcomeCode 0 -OutcomeReason "concluido"

            $fim = @(Get-JsonlEvents $log)[-1]
            @($fim.steps).Count | Should -Be 1
            @($fim.steps)[0].step | Should -Be "extract"
        }
    }
}
