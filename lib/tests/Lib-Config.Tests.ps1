$here = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($here)) {
    $here = Split-Path -Parent $PSCommandPath
}

$sut = (Split-Path -Parent $here) + "\Lib-Config.psm1"

Import-Module $sut -Force

Describe "Lib-Config Tests" {
    Context "Get-HubConfig" {
        It "returns default value when key is absent" {
            $key = "AUTOMACOES_TEST_KEY_AUSENTE"
            [System.Environment]::SetEnvironmentVariable($key, $null, "Process")

            Get-HubConfig -Key $key -Default "fallback" | Should -Be "fallback"
        }

        It "returns process value when key is present" {
            $key = "AUTOMACOES_TEST_KEY_PRESENTE"
            [System.Environment]::SetEnvironmentVariable($key, "valor-teste", "Process")

            try {
                Get-HubConfig -Key $key -Default "fallback" | Should -Be "valor-teste"
            }
            finally {
                [System.Environment]::SetEnvironmentVariable($key, $null, "Process")
            }
        }
    }
}
