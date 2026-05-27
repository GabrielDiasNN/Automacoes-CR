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

            $result | Should -BeTrue
            Test-Path $tempLog | Should -BeTrue
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

            $result | Should -BeFalse
            $content = Get-Content -LiteralPath $tempLog -Raw
            $content | Should -Match "RETRY_ESGOTADO"
        }
    }
}
