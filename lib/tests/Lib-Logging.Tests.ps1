$here = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($here)) {
    $here = Split-Path -Parent $PSCommandPath
}

$sut = (Split-Path -Parent $here) + "\Lib-Logging.psm1"

Import-Module $sut -Force

Describe "Lib-Logging Tests" {
    Context "Write-AutomacaoLog" {
        It "Should execute without errors" {
            $tempLog = Join-Path $here "test.log"
            { Write-AutomacaoLog -Message "Test message" -Level "INFO" -LogPath $tempLog } | Should Not Throw
            if (Test-Path $tempLog) { Remove-Item $tempLog -Force }
        }
    }
}
