$here = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($here)) {
    $here = Split-Path -Parent $PSCommandPath
}

$libRoot = Split-Path -Parent $here
Import-Module (Join-Path $libRoot "Lib-Logging.psm1") -Force
Import-Module (Join-Path $libRoot "Lib-Retry.psm1") -Force

Describe "Lib-Retry Tests" {
    Context "Invoke-WithRetry" {
        It "returns true when action succeeds" {
            $tempLog = Join-Path $TestDrive "retry-success.jsonl"

            $result = Invoke-WithRetry `
                -Action { $true } `
                -MaxAttempts 1 `
                -BackoffSeconds @(0) `
                -OperationName "Teste sucesso" `
                -ExecId "TEST_RETRY_OK" `
                -LogPath $tempLog

            $result | Should -Be $true
            Test-Path $tempLog | Should -Be $true
        }

        It "returns false after final failed attempt" {
            $tempLog = Join-Path $TestDrive "retry-failure.jsonl"

            $result = Invoke-WithRetry `
                -Action { throw "falha controlada" } `
                -MaxAttempts 1 `
                -BackoffSeconds @(0) `
                -OperationName "Teste falha" `
                -ExecId "TEST_RETRY_FAIL" `
                -LogPath $tempLog

            $result | Should -Be $false
            $content = Get-Content -LiteralPath $tempLog -Raw
            $content | Should -Match "RETRY_ESGOTADO"
        }

        It "nao usa mais o encoder Base64 em mensagens com acento (UTF-8 ponta a ponta)" {
            $tempLog = Join-Path $TestDrive "retry-acento.jsonl"

            Invoke-WithRetry `
                -Action { $true } `
                -MaxAttempts 1 -BackoffSeconds @(0) `
                -OperationName "Extração OBs Restrição Branco" `
                -ExecId "TEST_RETRY_UTF8" `
                -LogPath $tempLog | Out-Null

            $content = Get-Content -LiteralPath $tempLog -Raw
            $content | Should -Not -Match "B64:"
            $content | Should -Match "Restri"
        }
    }

    Context "Integracao com Lib-LogEvent" {
        BeforeAll {
            Import-Module (Join-Path (Split-Path -Parent $PSScriptRoot) "Lib-LogEvent.psm1") -Force
        }
        AfterEach {
            if (Get-Command Clear-HubLogContext -ErrorAction SilentlyContinue) { Clear-HubLogContext }
        }

        It "emite retry.attempt na retentativa quando ha contexto de LogEvent ativo" {
            $tempLog = Join-Path $TestDrive "retry-evento.jsonl"
            Initialize-HubLogContext -Automation "A" -ExecId "T" -TraceId "t" -LogPath $tempLog

            $script:tentativas = 0
            Invoke-WithRetry `
                -Action { $script:tentativas++; if ($script:tentativas -lt 2) { throw "falha 1" }; $true } `
                -MaxAttempts 3 -BackoffSeconds @(0) `
                -OperationName "Extracao" -Step "extract" `
                -ExecId "T" -LogPath $tempLog | Out-Null

            $events = Get-Content -LiteralPath $tempLog | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json }
            $retry = @($events | Where-Object { $_.event -eq "retry.attempt" })
            $retry.Count | Should -BeGreaterOrEqual 1
            $retry[0].step | Should -Be "extract"
            $retry[0].max_attempts | Should -Be 3
            # a 1a tentativa (que falhou) gera evento; a 2a (sucesso) tambem.
            ($retry | Where-Object { $_.message -match "sucesso apos 2" }) | Should -Not -BeNullOrEmpty
        }

        It "primeira tentativa bem-sucedida NAO gera retry.attempt (happy path limpo)" {
            $tempLog = Join-Path $TestDrive "retry-happy.jsonl"
            Initialize-HubLogContext -Automation "A" -ExecId "T" -TraceId "t" -LogPath $tempLog

            Invoke-WithRetry -Action { $true } -MaxAttempts 3 -BackoffSeconds @(0) `
                -OperationName "Extracao" -Step "extract" -ExecId "T" -LogPath $tempLog | Out-Null

            $retry = @()
            if (Test-Path $tempLog) {
                $retry = @(Get-Content -LiteralPath $tempLog | Where-Object { $_.Trim() } |
                    ForEach-Object { $_ | ConvertFrom-Json } | Where-Object { $_.event -eq "retry.attempt" })
            }
            $retry.Count | Should -Be 0
        }
    }
}
