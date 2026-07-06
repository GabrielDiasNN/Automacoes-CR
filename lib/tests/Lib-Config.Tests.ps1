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

    Context "ConvertFrom-EnvLine" {
        It "remove comentario inline apos o valor (ex.: '123 # Nome')" {
            InModuleScope Lib-Config {
                $resultado = ConvertFrom-EnvLine -Line "OBP_CONTATO_TESTE=5500000000000         # Nome Exemplo"
                $resultado.Key | Should -Be "OBP_CONTATO_TESTE"
                $resultado.Value | Should -Be "5500000000000"
            }
        }

        It "preserva valores sem comentario inline" {
            InModuleScope Lib-Config {
                $resultado = ConvertFrom-EnvLine -Line "OBP_WHATSAPP_TARGET=550000000000-0000000000@g.us"
                $resultado.Value | Should -Be "550000000000-0000000000@g.us"
            }
        }

        It "ignora linhas de comentario puro" {
            InModuleScope Lib-Config {
                ConvertFrom-EnvLine -Line "# isso e um comentario" | Should -BeNullOrEmpty
            }
        }
    }
}
