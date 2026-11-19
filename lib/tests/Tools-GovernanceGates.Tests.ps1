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
        $nomeSenha = 'pass' + 'word'
        $nomeChave = 'API_' + 'KEY'
        $valorFalso = 'abc123' + 'def456'

        $script:FixtureViolacaoA = '{0} = "{1}"' -f $nomeSenha, $valorFalso
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

Describe "Test-PythonGovernance - escopo de pylint com -LintChangedOnly" {
    BeforeAll {
        $script:FakeBinDir = Join-Path $TestDrive "fake-py-bin"
        New-Item -ItemType Directory -Force -Path $script:FakeBinDir | Out-Null
        $ascii = [System.Text.Encoding]::ASCII
        [System.IO.File]::WriteAllText((Join-Path $script:FakeBinDir "mypy.cmd"), "@echo off`r`nexit /b 0`r`n", $ascii)
        [System.IO.File]::WriteAllText(
            (Join-Path $script:FakeBinDir "pylint.cmd"),
            "@echo off`r`necho PYLINT_ARGS: %*`r`necho %* | findstr /I `"consumidor.py`" >nul && (`r`n  echo consumidor.py:1:0: W0612: Unused variable 'nao_usada' ^(unused-variable^)`r`n  exit /b 1`r`n)`r`nexit /b 0`r`n",
            $ascii
        )
        $script:OriginalPath = $env:PATH
        $env:PATH = "$($script:FakeBinDir);$($env:PATH)"
    }

    AfterAll {
        $env:PATH = $script:OriginalPath
    }

    It "inclui dependente que usa import relativo (from .modulo import ...)" {
        $fixture = New-GateFixture -BasePath (Join-Path $TestDrive "pygov-rel")
        $pkgDir = New-GateFixture -BasePath (Join-Path $fixture "pkg")
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)

        [System.IO.File]::WriteAllText((Join-Path $pkgDir "__init__.py"), "", $utf8NoBom)
        [System.IO.File]::WriteAllText((Join-Path $pkgDir "modulo.py"), "def saudar() -> str:`n    return 'ok'`n", $utf8NoBom)
        [System.IO.File]::WriteAllText((Join-Path $pkgDir "consumidor.py"), "from .modulo import saudar`n`n`ndef usar() -> str:`n    nao_usada = saudar()`n    return 'ok'`n", $utf8NoBom)

        $result = Invoke-Gate -ScriptName "Test-PythonGovernance.ps1" -BasePath $fixture -ExtraArgs @(
            "-Paths", "pkg/__init__.py,pkg/modulo.py,pkg/consumidor.py",
            "-LintChangedOnly",
            "-LintScopePaths", "pkg/modulo.py"
        )

        $result.ExitCode | Should -Be 1
        $result.Output | Should -Match "Pylint restrito ao diff: 2 arquivo\(s\)"
        $result.Output | Should -Match "W0612|unused-variable"
    }

    It "inclui dependente quando o modulo em -LintScopePaths foi removido" {
        $fixture = New-GateFixture -BasePath (Join-Path $TestDrive "pygov-del")
        $pkgDir = New-GateFixture -BasePath (Join-Path $fixture "pkg")
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)

        [System.IO.File]::WriteAllText((Join-Path $pkgDir "__init__.py"), "", $utf8NoBom)
        [System.IO.File]::WriteAllText((Join-Path $pkgDir "consumidor.py"), "from . import modulo_removido  # type: ignore[attr-defined]`n`n`ndef usar() -> str:`n    return str(modulo_removido)`n", $utf8NoBom)

        $result = Invoke-Gate -ScriptName "Test-PythonGovernance.ps1" -BasePath $fixture -ExtraArgs @(
            "-Paths", "pkg/__init__.py,pkg/consumidor.py",
            "-LintChangedOnly",
            "-LintScopePaths", "pkg/modulo_removido.py"
        )

        $result.ExitCode | Should -Be 1
        $result.Output | Should -Match "Pylint restrito ao diff: 1 arquivo\(s\)"
        $result.Output | Should -Match "consumidor\.py"
    }

    It "inclui dependente com multi-import e alias na mesma linha (import os as _os, modulo as m)" {
        $fixture = New-GateFixture -BasePath (Join-Path $TestDrive "pygov-multi")
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)

        [System.IO.File]::WriteAllText((Join-Path $fixture "modulo.py"), "def ok() -> str:`n    return 'ok'`n", $utf8NoBom)
        [System.IO.File]::WriteAllText((Join-Path $fixture "consumidor.py"), "import os as _os, modulo as m`n`n`ndef usar() -> str:`n    nao_usada = (m.ok(), _os.name)`n    return str(nao_usada)`n", $utf8NoBom)

        $result = Invoke-Gate -ScriptName "Test-PythonGovernance.ps1" -BasePath $fixture -ExtraArgs @(
            "-Paths", "modulo.py,consumidor.py",
            "-LintChangedOnly",
            "-LintScopePaths", "modulo.py"
        )

        $result.ExitCode | Should -Be 1
        $result.Output | Should -Match "Pylint restrito ao diff: 2 arquivo\(s\)"
        $result.Output | Should -Match "consumidor\.py"
    }
}

Describe "Resolucao padrao de -RootPath nos gates (sem passar -RootPath)" {
    It "resolve para a raiz do repositorio pai de Tools e detecta violacoes em arquivos relativos" {
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        # Valores montados por concatenacao para este arquivo de teste nao acionar ZeroTrust nem PortablePaths.
        $segredo = "pass" + "word = `"segredo123`"`n"
        $caminhoAbs = '$p = "' + 'C:' + '\ProjetoTeste\saida"' + "`n"
        $sqlWildcard = "SELECT " + "* FROM DUAL;`n"
        $catchGenerico = "try { 1 } " + "catch" + " { }`n"

        $casos = @(
            @{ Script = "Test-ZeroTrust.ps1"; File = "alvo_zt.py"; Content = $segredo },
            @{ Script = "Test-PortablePaths.ps1"; File = "alvo_pp.ps1"; Content = $caminhoAbs },
            @{ Script = "Test-SqlPerformance.ps1"; File = "alvo_sql.sql"; Content = $sqlWildcard },
            @{ Script = "Test-PowerShellGovernance.ps1"; File = "alvo_ps.ps1"; Content = $catchGenerico }
        )

        foreach ($caso in $casos) {
            $subRoot = Join-Path $TestDrive ("default-root-" + [guid]::NewGuid().ToString("N"))
            $toolsDir = Join-Path $subRoot "Tools"
            New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null
            Copy-Item -LiteralPath (Join-Path $script:RepoRoot "Tools\$($caso.Script)") -Destination (Join-Path $toolsDir $caso.Script) -Force
            [System.IO.File]::WriteAllText((Join-Path $subRoot $caso.File), $caso.Content, $utf8NoBom)

            $proc = Start-Process -FilePath "powershell.exe" `
                -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $toolsDir $caso.Script), "-Paths", $caso.File) `
                -Wait -PassThru -NoNewWindow

            $proc.ExitCode | Should -Be 1 -Because "$($caso.Script) sem -RootPath deve resolver para o pai de Tools"
        }
    }
}

Describe "Get-GovernanceTargetSummary - --no-renames em git mv" {
    It "inclui caminho antigo e novo em NormalizedPaths ao renomear arquivo via git mv" {
        $gitRepo = Join-Path $TestDrive ("git-mv-" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Force -Path $gitRepo | Out-Null
        git -C $gitRepo init -q
        git -C $gitRepo config user.name "Teste"
        git -C $gitRepo config user.email "teste@exemplo.local"

        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText((Join-Path $gitRepo "mod_antigo.py"), "X = 1`n", $utf8NoBom)
        git -C $gitRepo add mod_antigo.py
        git -C $gitRepo commit -m "inicial" -q
        git -C $gitRepo mv mod_antigo.py mod_novo.py

        $summary = & (Join-Path $script:RepoRoot "Tools\Get-GovernanceTargetSummary.ps1") -BasePath $gitRepo -StagedOnly
        $norm = @($summary.NormalizedPaths)
        $norm | Should -Contain "mod_antigo.py"
        $norm | Should -Contain "mod_novo.py"
    }
}

Describe "ValidarAutomacoes - caminho relativo com jobs paralelos" {
    It "propaga raiz resolvida para jobs paralelos quando -BasePath e '.'" {
        $outPath = Join-Path $TestDrive "validar-rel.txt"
        $proc = Start-Process -FilePath "powershell.exe" `
            -WorkingDirectory $script:RepoRoot `
            -ArgumentList @(
                "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", "Tools\ValidarAutomacoes.ps1",
                "-BasePath", ".",
                "-OnlyGovernance",
                "-Paths", "Orchestrator/app/constants.py",
                "-NoCriticalPromotion",
                "-SkipSkillsGovernance",
                "-SkipDashboardTemplateGovernance"
            ) `
            -Wait -PassThru -NoNewWindow -RedirectStandardOutput $outPath

        $outText = if (Test-Path -LiteralPath $outPath) { Get-Content -LiteralPath $outPath -Raw } else { "" }
        $proc.ExitCode | Should -Be 0 -Because "ValidarAutomacoes com -BasePath '.' deve passar. Saida:`n$outText"
    }
}
