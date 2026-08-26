$here = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($here)) {
    $here = Split-Path -Parent $PSCommandPath
}

BeforeAll {
    # $PSScriptRoot aqui e lib\tests; dois niveis acima e a raiz do repositorio.
    $script:RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $script:CreatedJunctions = New-Object System.Collections.Generic.List[string]

    function Get-LongPath {
        param([string]$Path)

        # $TestDrive costuma cair sob %TEMP%, que nesta maquina responde em formato 8.3
        # (C:\Users\GABRIE~1.DIA\...). Test-SkillsGovernance compara o alvo do link com
        # Resolve-Path do diretorio fonte, e o alvo de uma junction sempre volta expandido:
        # sem normalizar aqui, o caminho feliz acusaria AGENTS_SKILL_MIRROR_TARGET_INVALID.
        try {
            $fso = New-Object -ComObject Scripting.FileSystemObject
            return $fso.GetFolder($Path).Path
        } catch [System.Exception] {
            # Sem COM disponivel (ou caminho inexistente) o formato curto nao e um
            # problema: o teste segue com o caminho como veio.
            return $Path
        }
    }

    function New-SkillsFixture {
        param([string]$Name)

        $basePath = Join-Path (Get-LongPath -Path $TestDrive) $Name
        New-Item -ItemType Directory -Force -Path (Join-Path $basePath ".github") | Out-Null
        New-Item -ItemType Directory -Force -Path (Join-Path $basePath ".claude") | Out-Null
        New-Item -ItemType Directory -Force -Path (Join-Path $basePath ".agents\skills") | Out-Null

        # As skills reais do repo sao a fixture: o script aborta cedo ("Nenhuma SKILL.md
        # encontrada em .github/skills") se a taxonomia canonica nao estiver presente, e
        # e' o conteudo de .claude/skills que define quais mirrors sao legitimos.
        Copy-Item -Recurse -Force (Join-Path $script:RepoRoot ".github\skills") (Join-Path $basePath ".github\skills")
        Copy-Item -Recurse -Force (Join-Path $script:RepoRoot ".claude\skills") (Join-Path $basePath ".claude\skills")

        return $basePath
    }

    function New-MirrorJunction {
        param(
            [string]$BasePath,
            [string]$MirrorName,
            [string]$SourceName = $MirrorName
        )

        $linkPath = Join-Path $BasePath ".agents\skills\$MirrorName"
        $targetPath = Join-Path $BasePath ".claude\skills\$SourceName"
        New-Item -ItemType Junction -Path $linkPath -Target $targetPath | Out-Null
        $script:CreatedJunctions.Add($linkPath)
    }

    function New-MirrorCopy {
        param(
            [string]$BasePath,
            [string]$MirrorName
        )

        Copy-Item -Recurse -Force `
            (Join-Path $BasePath ".claude\skills\$MirrorName") `
            (Join-Path $BasePath ".agents\skills\$MirrorName")
    }

    function Invoke-SkillsGovernance {
        param([string]$BasePath)

        $sut = Join-Path $script:RepoRoot "Tools\Test-SkillsGovernance.ps1"
        $outputPath = Join-Path $BasePath "skills-output.txt"
        $arguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $sut, "-BasePath", $BasePath)
        $process = Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -Wait -PassThru -NoNewWindow -RedirectStandardOutput $outputPath
        $output = Get-Content -LiteralPath $outputPath -Raw

        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            Output   = $output
        }
    }
}

Describe "Test-SkillsGovernance — mirror .agents/skills" {
    AfterEach {
        # Directory.Delete remove a junction sem seguir o link. Deixar para o cleanup do
        # TestDrive arriscaria um Remove-Item -Recurse atravessando o link ate' a fonte.
        foreach ($junction in $script:CreatedJunctions) {
            if (Test-Path -LiteralPath $junction) {
                [System.IO.Directory]::Delete($junction, $true)
            }
        }
        $script:CreatedJunctions.Clear()
    }

    It "aprova mirror inteiro apontando por junction para .claude/skills" {
        $fixture = New-SkillsFixture -Name "mirror-valido"
        if ($fixture -match '~') {
            Set-ItResult -Skipped -Because "TestDrive resolveu para caminho 8.3 e o alvo da junction nao seria comparavel"
            return
        }

        foreach ($skill in @("ci-gates", "new-automation", "preflight", "quality-gate", "run-orchestrator", "run-tests")) {
            New-MirrorJunction -BasePath $fixture -MirrorName $skill
        }

        $resultado = Invoke-SkillsGovernance -BasePath $fixture

        # Sem esta primeira assercao, um script que nem chegou a rodar passaria no
        # "Should -Not -Match" por saida vazia.
        $resultado.Output | Should -Match "GOVERNANCA DE SKILLS"
        $resultado.Output | Should -Not -Match "AGENTS_SKILL_MIRROR"
    }

    It "nao gera achado quando .agents/skills nao existe (mirror e opcional)" {
        $fixture = New-SkillsFixture -Name "sem-mirror"
        Remove-Item -LiteralPath (Join-Path $fixture ".agents") -Recurse -Force

        $resultado = Invoke-SkillsGovernance -BasePath $fixture

        $resultado.Output | Should -Match "GOVERNANCA DE SKILLS"
        $resultado.Output | Should -Not -Match "AGENTS_SKILL_MIRROR"
    }

    It "avisa (WARN) sobre copia real no lugar do link — mesmo contrato do mirror .gemini/skills, mesma severidade" {
        # Item 6 da revisao de 26/08/2026: AGENTS_SKILL_MIRROR_NOT_LINKED e
        # GEMINI_SKILL_MIRROR_NOT_LINKED sao o mesmo achado (mirror virou copia
        # real) e o README afirma "mesmo contrato" — nao bloqueia commit, porque
        # o mirror e artefato local reconstruivel via Tools\New-SkillMirrors.ps1.
        # Demais skills viram junction (mirror completo) para isolar o achado:
        # sem isso, os outros mirrors ausentes disparariam AGENTS_SKILL_MIRROR_MISSING
        # (ERROR) e mascarariam o exit code que este teste verifica.
        $fixture = New-SkillsFixture -Name "copia-real"
        if ($fixture -match '~') {
            Set-ItResult -Skipped -Because "TestDrive resolveu para caminho 8.3 e o alvo da junction nao seria comparavel"
            return
        }

        foreach ($skill in @("ci-gates", "new-automation", "quality-gate", "run-orchestrator", "run-tests")) {
            New-MirrorJunction -BasePath $fixture -MirrorName $skill
        }
        New-MirrorCopy -BasePath $fixture -MirrorName "preflight"

        $resultado = Invoke-SkillsGovernance -BasePath $fixture

        $resultado.Output | Should -Match "AGENTS_SKILL_MIRROR_NOT_LINKED"
        $resultado.Output | Should -Match "WARNINGS"
        $resultado.ExitCode | Should -Be 0
    }

    It "reprova skill operacional sem espelho quando .agents/skills existe" {
        # Simetria com GEMINI_SKILL_MIRROR_MISSING: existindo o mirror, ele tem que
        # estar completo. Skill nova em .claude/skills passava em silencio.
        $fixture = New-SkillsFixture -Name "espelho-ausente"
        New-Item -ItemType Directory -Force -Path (Join-Path $fixture ".claude\skills\skill-nova") | Out-Null
        Set-Content -LiteralPath (Join-Path $fixture ".claude\skills\skill-nova\SKILL.md") -Value "# skill-nova" -Encoding UTF8

        $resultado = Invoke-SkillsGovernance -BasePath $fixture

        $resultado.Output | Should -Match "AGENTS_SKILL_MIRROR_MISSING"
        $resultado.Output | Should -Match "New-SkillMirrors.ps1"
        $resultado.ExitCode | Should -Not -Be 0
    }

    It "reprova mirror sem skill correspondente em .claude/skills" {
        $fixture = New-SkillsFixture -Name "mirror-orfao"
        New-Item -ItemType Directory -Force -Path (Join-Path $fixture ".agents\skills\skill-fantasma") | Out-Null

        $resultado = Invoke-SkillsGovernance -BasePath $fixture

        $resultado.Output | Should -Match "AGENTS_SKILL_MIRROR_ORPHAN"
        $resultado.ExitCode | Should -Not -Be 0
    }

    It "reprova junction apontando para outra skill que nao a homonima" {
        $fixture = New-SkillsFixture -Name "alvo-divergente"
        New-MirrorJunction -BasePath $fixture -MirrorName "preflight" -SourceName "quality-gate"

        $resultado = Invoke-SkillsGovernance -BasePath $fixture

        $resultado.Output | Should -Match "AGENTS_SKILL_MIRROR_TARGET_INVALID"
        $resultado.ExitCode | Should -Not -Be 0
    }

    It "nao reintroduz a regra LEGACY_SKILL_LOCATION, que mandava mover para .github/skills" {
        # Trava de regressao: as skills operacionais tem fonte unica em .claude/skills;
        # mandar move-las para a taxonomia canonica de padrao era o defeito da regra antiga.
        $sut = Join-Path $script:RepoRoot "Tools\Test-SkillsGovernance.ps1"
        $conteudo = Get-Content -LiteralPath $sut -Raw

        $conteudo | Should -Not -Match "LEGACY_SKILL_LOCATION"
        $conteudo | Should -Match "function Test-AgentsSkillMirrors"
    }
}
