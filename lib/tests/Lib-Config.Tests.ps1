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

    Context "Test-WhatsAppConfigEnabled" {
        It "retorna true quando config ou propriedades enabled estao ausentes" {
            Test-WhatsAppConfigEnabled -Config $null | Should -BeTrue
            Test-WhatsAppConfigEnabled -Config ([pscustomobject]@{}) | Should -BeTrue
            Test-WhatsAppConfigEnabled -Config ([pscustomobject]@{
                app    = [pscustomobject]@{ name = "WA" }
                target = [pscustomobject]@{ contactIdEnv = "X" }
            }) | Should -BeTrue
        }

        It "retorna false quando app.enabled ou target.enabled e false booleano" {
            Test-WhatsAppConfigEnabled -Config ([pscustomobject]@{
                app    = [pscustomobject]@{ enabled = $false }
                target = [pscustomobject]@{ enabled = $true }
            }) | Should -BeFalse
            Test-WhatsAppConfigEnabled -Config ([pscustomobject]@{
                app    = [pscustomobject]@{ enabled = $true }
                target = [pscustomobject]@{ enabled = $false }
            }) | Should -BeFalse
        }

        It "retorna false para strings 'false', '0' e 'no' case-insensitive" {
            foreach ($val in @("false", "FALSE", " False ", "0", "no", "NO")) {
                Test-WhatsAppConfigEnabled -Config ([pscustomobject]@{
                    app    = [pscustomobject]@{ enabled = $val }
                    target = [pscustomobject]@{ enabled = $true }
                }) | Should -BeFalse
                Test-WhatsAppConfigEnabled -Config ([pscustomobject]@{
                    app    = [pscustomobject]@{ enabled = $true }
                    target = [pscustomobject]@{ enabled = $val }
                }) | Should -BeFalse
            }
        }

        It "retorna true quando ambos app.enabled e target.enabled estao ativos" {
                Test-WhatsAppConfigEnabled -Config ([pscustomobject]@{
                    app    = [pscustomobject]@{ enabled = $true }
                    target = [pscustomobject]@{ enabled = "true" }
                }) | Should -BeTrue
        }
    }

    Context "Leitura de .env com UTF-8 BOM na linha 1" {
        It "Get-EnvFileValue e Import-HubEnv leem a chave da primeira linha mesmo com BOM" {
            $tmpDir = Join-Path $TestDrive ("env_bom_" + [guid]::NewGuid().ToString("N"))
            New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
            $chaveTeste = "HUB_PESTER_BOM_KEY"
            [System.Environment]::SetEnvironmentVariable($chaveTeste, $null, "Process")

            try {
                $envPath = Join-Path $tmpDir ".env"
                $conteudo = "$chaveTeste=valor-com-acento-çãõ`r`nOUTRA_CHAVE=123`r`n"
                [System.IO.File]::WriteAllText($envPath, $conteudo, (New-Object System.Text.UTF8Encoding $true))

                $prev = InModuleScope Lib-Config -Parameters @{ NovoRoot = $tmpDir } {
                    param($NovoRoot)
                    $estado = @{
                        ProjectRoot = $script:ProjectRoot
                        EnvLoaded   = $script:EnvLoaded
                    }
                    $script:ProjectRoot = $NovoRoot
                    $script:EnvLoaded = $false
                    $estado
                }

                try {
                    Get-EnvFileValue -Key $chaveTeste | Should -Be "valor-com-acento-çãõ"
                    Import-HubEnv -Force
                    [System.Environment]::GetEnvironmentVariable($chaveTeste, "Process") | Should -Be "valor-com-acento-çãõ"
                }
                finally {
                    InModuleScope Lib-Config -Parameters @{ AntigoRoot = $prev.ProjectRoot; AntigoLoaded = $prev.EnvLoaded } {
                        param($AntigoRoot, $AntigoLoaded)
                        $script:ProjectRoot = $AntigoRoot
                        $script:EnvLoaded = $AntigoLoaded
                    }
                }
            }
            finally {
                [System.Environment]::SetEnvironmentVariable($chaveTeste, $null, "Process")
                Remove-Item -LiteralPath $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }
}
