#
# Testes Pester dos gates de governanca que rodam no pre-commit.
#
# Motivacao (achado A9 da revisao arquitetural): Tools/ e o gate de qualidade de
# todo o repositorio, mas so Test-ArchitectureStandard.ps1 tinha teste. Um falso
# negativo em Test-ZeroTrust.ps1 (segredo hardcoded passando batido) ou em
# Test-SourceEncoding.ps1 nao seria detectado por ninguem. Estes testes cobrem os
# dois lados de cada gate: aprova o caso limpo E reprova a violacao.
#

BeforeAll {
    $script:RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

    function Invoke-Gate {
        param(
            [Parameter(Mandatory)][string]$ScriptName,
            [Parameter(Mandatory)][string]$BasePath,
            [string[]]$ExtraArgs = @()
        )

        $sut = Join-Path $script:RepoRoot "Tools\$ScriptName"
        # Fora do fixture de proposito: Test-SourceEncoding varre o diretorio
        # inteiro e leria o proprio arquivo de saida ainda aberto pelo processo.
        $outputDir = Join-Path $TestDrive "gate-output"
        New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
        $outputPath = Join-Path $outputDir ("{0}-{1}.txt" -f $ScriptName, (Split-Path -Leaf $BasePath))
        $arguments = @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", $sut,
            "-RootPath", $BasePath
        ) + $ExtraArgs

        $process = Start-Process -FilePath "powershell.exe" `
            -ArgumentList $arguments -Wait -PassThru -NoNewWindow `
            -RedirectStandardOutput $outputPath

        $output = ""
        if (Test-Path -LiteralPath $outputPath) {
            $output = Get-Content -LiteralPath $outputPath -Raw
        }

        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            Output   = $output
        }
    }

    function New-GateFixture {
        param([Parameter(Mandatory)][string]$BasePath)
        New-Item -ItemType Directory -Force -Path $BasePath | Out-Null
        return $BasePath
    }
}

Describe "Test-ZeroTrust" {
    # As fixtures de violacao sao montadas por concatenacao, nunca como literal:
    # escritas por extenso, o proprio Test-ZeroTrust reprovaria ESTE arquivo ao
    # varrer o repositorio, e o gate ficaria sem cobertura do caso negativo.
    BeforeAll {
        # Nome e valor ficam em variaveis separadas: e a proximidade entre eles
        # na MESMA linha que o gate procura.
        $nomeSenha  = 'pass' + 'word'
        $nomeChave  = 'API_' + 'KEY'
        $valorFalso = 'abc123' + 'def456'

        $script:FixtureViolacaoA  = '{0} = "{1}"' -f $nomeSenha, $valorFalso
        $script:FixtureViolacaoB = '{0}: "{1}"' -f $nomeChave, $valorFalso
    }

    It "aprova arquivo que le credencial de variavel de ambiente" {
        $fixture = New-GateFixture -BasePath (Join-Path $TestDrive "zt-clean")
        'senha = os.environ["ORACLE_PASSWORD"]' |
            Set-Content -LiteralPath (Join-Path $fixture "app.py") -Encoding UTF8

        $result = Invoke-Gate -ScriptName "Test-ZeroTrust.ps1" -BasePath $fixture -ExtraArgs @("-Paths", "app.py")

        $result.ExitCode | Should -Be 0
    }

    It "reprova senha hardcoded em atribuicao" {
        $fixture = New-GateFixture -BasePath (Join-Path $TestDrive "zt-secret")
        $script:FixtureViolacaoA |
            Set-Content -LiteralPath (Join-Path $fixture "app.py") -Encoding UTF8

        $result = Invoke-Gate -ScriptName "Test-ZeroTrust.ps1" -BasePath $fixture -ExtraArgs @("-Paths", "app.py")

        $result.ExitCode | Should -Be 1
        $result.Output | Should -Match "ERRO DE SEGURANCA"
    }

    It "reprova api_key hardcoded independente de maiuscula/minuscula" {
        $fixture = New-GateFixture -BasePath (Join-Path $TestDrive "zt-apikey")
        $script:FixtureViolacaoB |
            Set-Content -LiteralPath (Join-Path $fixture "config.json") -Encoding UTF8

        $result = Invoke-Gate -ScriptName "Test-ZeroTrust.ps1" -BasePath $fixture -ExtraArgs @("-Paths", "config.json")

        $result.ExitCode | Should -Be 1
    }
}

Describe "Test-PortablePaths" {
    It "aprova caminho relativo" {
        $fixture = New-GateFixture -BasePath (Join-Path $TestDrive "pp-clean")
        '$destino = Join-Path $PSScriptRoot "saida"' |
            Set-Content -LiteralPath (Join-Path $fixture "script.ps1") -Encoding UTF8

        $result = Invoke-Gate -ScriptName "Test-PortablePaths.ps1" -BasePath $fixture -ExtraArgs @("-Paths", "script.ps1")

        $result.ExitCode | Should -Be 0
    }

    It "reprova caminho absoluto hardcoded" {
        $fixture = New-GateFixture -BasePath (Join-Path $TestDrive "pp-absolute")
        '$destino = "C:\Automacoes\saida"' |
            Set-Content -LiteralPath (Join-Path $fixture "script.ps1") -Encoding UTF8

        $result = Invoke-Gate -ScriptName "Test-PortablePaths.ps1" -BasePath $fixture -ExtraArgs @("-Paths", "script.ps1")

        $result.ExitCode | Should -Be 1
    }
}

Describe "Test-SourceEncoding" {
    It "aprova .py sem BOM e .ps1 com BOM" {
        $fixture = New-GateFixture -BasePath (Join-Path $TestDrive "enc-clean")

        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText(
            (Join-Path $fixture "modulo.py"), "# acentuacao: coracao`n", $utf8NoBom)

        $utf8Bom = New-Object System.Text.UTF8Encoding($true)
        [System.IO.File]::WriteAllText(
            (Join-Path $fixture "script.ps1"), "# acentuacao: coracao`n", $utf8Bom)

        $result = Invoke-Gate -ScriptName "Test-SourceEncoding.ps1" -BasePath $fixture

        $result.ExitCode | Should -Be 0
    }

    It "reprova .ps1 sem BOM (quebra acentuacao no PowerShell 5.1)" {
        $fixture = New-GateFixture -BasePath (Join-Path $TestDrive "enc-ps1-nobom")

        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText(
            (Join-Path $fixture "script.ps1"), "Write-Host 'execucao'`n", $utf8NoBom)

        $result = Invoke-Gate -ScriptName "Test-SourceEncoding.ps1" -BasePath $fixture

        # Contrato do gate: 2 = violacao de encoding (0 = conforme).
        $result.ExitCode | Should -Be 2
    }

    It "reprova .py com BOM" {
        $fixture = New-GateFixture -BasePath (Join-Path $TestDrive "enc-py-bom")

        $utf8Bom = New-Object System.Text.UTF8Encoding($true)
        [System.IO.File]::WriteAllText(
            (Join-Path $fixture "modulo.py"), "valor = 1`n", $utf8Bom)

        $result = Invoke-Gate -ScriptName "Test-SourceEncoding.ps1" -BasePath $fixture

        # Contrato do gate: 2 = violacao de encoding (0 = conforme).
        $result.ExitCode | Should -Be 2
    }
}
