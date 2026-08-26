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

        # $TestDrive cai sob %TEMP%, que responde em formato 8.3 nesta maquina
        # (C:\Users\GABRIE~1.DIA\...). O alvo de uma junction sempre volta expandido,
        # entao sem normalizar aqui a comparacao mirror-vs-fonte daria falso negativo.
        try {
            $fso = New-Object -ComObject Scripting.FileSystemObject
            return $fso.GetFolder($Path).Path
        } catch [System.Exception] {
            # Sem COM disponivel (ou caminho inexistente) o formato curto nao e um
            # problema: o teste segue com o caminho como veio.
            return $Path
        }
    }

    function New-MirrorFixture {
        param([string]$Name)

        $basePath = Join-Path (Get-LongPath -Path $TestDrive) $Name
        New-Item -ItemType Directory -Force -Path (Join-Path $basePath ".github") | Out-Null
        New-Item -ItemType Directory -Force -Path (Join-Path $basePath ".claude") | Out-Null
        Copy-Item -Recurse -Force (Join-Path $script:RepoRoot ".github\skills") (Join-Path $basePath ".github\skills")
        Copy-Item -Recurse -Force (Join-Path $script:RepoRoot ".claude\skills") (Join-Path $basePath ".claude\skills")

        return $basePath
    }

    function Invoke-NewSkillMirrors {
        param(
            [string]$BasePath,
            [string[]]$ExtraArgs = @()
        )

        $sut = Join-Path $script:RepoRoot "Tools\New-SkillMirrors.ps1"
        $outputPath = Join-Path $BasePath "mirrors-output.txt"
        $errorPath = Join-Path $BasePath "mirrors-error.txt"
        $arguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $sut, "-BasePath", $BasePath) + $ExtraArgs
        $process = Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -Wait -PassThru -NoNewWindow `
            -RedirectStandardOutput $outputPath -RedirectStandardError $errorPath
        $saida = (Get-Content -LiteralPath $outputPath -Raw) + (Get-Content -LiteralPath $errorPath -Raw)

        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            Output   = $saida
        }
    }

    function Get-MirrorTarget {
        param([string]$Path)

        $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
        if ($null -eq $item) { return $null }
        return $item.Target
    }

    function Register-Junction {
        param([string]$Path)

        $script:CreatedJunctions.Add($Path)
    }
}

Describe "New-SkillMirrors" {
    AfterEach {
        # Directory.Delete remove a junction sem seguir o link; deixar para o cleanup do
        # TestDrive arriscaria um Remove-Item -Recurse atravessando ate' a fonte.
        foreach ($junction in $script:CreatedJunctions) {
            if (Test-Path -LiteralPath $junction) {
                [System.IO.Directory]::Delete($junction, $true)
            }
        }
        $script:CreatedJunctions.Clear()
    }

    It "cria os dois mirrors do zero, como num clone limpo" {
        $fixture = New-MirrorFixture -Name "clone-limpo"

        $resultado = Invoke-NewSkillMirrors -BasePath $fixture

        $resultado.ExitCode | Should -Be 0

        $geminiMirror = Join-Path $fixture ".gemini\skills\nodejs-communications"
        $agentsMirror = Join-Path $fixture ".agents\skills\run-tests"
        Register-Junction -Path $geminiMirror
        Register-Junction -Path $agentsMirror

        Get-MirrorTarget -Path $geminiMirror | Should -Be (Join-Path $fixture ".github\skills\nodejs-communications")
        Get-MirrorTarget -Path $agentsMirror | Should -Be (Join-Path $fixture ".claude\skills\run-tests")

        foreach ($skill in @("ci-gates", "new-automation", "preflight", "quality-gate", "run-orchestrator", "run-tests")) {
            $link = Join-Path $fixture ".agents\skills\$skill"
            Register-Junction -Path $link
            (Get-Item -LiteralPath $link -Force).LinkType | Should -Be "Junction"
        }
    }

    It "e idempotente: segunda execucao preserva os links e nao reporta divergencia" {
        $fixture = New-MirrorFixture -Name "idempotente"
        Invoke-NewSkillMirrors -BasePath $fixture | Out-Null

        $link = Join-Path $fixture ".agents\skills\preflight"
        Register-Junction -Path $link
        $alvoAntes = Get-MirrorTarget -Path $link

        $resultado = Invoke-NewSkillMirrors -BasePath $fixture

        $resultado.ExitCode | Should -Be 0
        $resultado.Output | Should -Match "\[ok\]"
        Get-MirrorTarget -Path $link | Should -Be $alvoAntes
    }

    It "preserva copia real sem -Force e sinaliza a divergencia" {
        $fixture = New-MirrorFixture -Name "copia-preservada"
        New-Item -ItemType Directory -Force -Path (Join-Path $fixture ".agents\skills") | Out-Null
        Copy-Item -Recurse -Force `
            (Join-Path $fixture ".claude\skills\preflight") `
            (Join-Path $fixture ".agents\skills\preflight")

        $resultado = Invoke-NewSkillMirrors -BasePath $fixture

        $resultado.ExitCode | Should -Not -Be 0
        $resultado.Output | Should -Match "copia real"
        # A copia continua sendo copia: sobrescrever sem pedir esconderia edicao
        # feita no lugar errado.
        (Get-Item -LiteralPath (Join-Path $fixture ".agents\skills\preflight") -Force).LinkType | Should -BeNullOrEmpty
    }

    It "substitui copia real por junction quando -Force e informado" {
        $fixture = New-MirrorFixture -Name "copia-substituida"
        New-Item -ItemType Directory -Force -Path (Join-Path $fixture ".agents\skills") | Out-Null
        Copy-Item -Recurse -Force `
            (Join-Path $fixture ".claude\skills\preflight") `
            (Join-Path $fixture ".agents\skills\preflight")

        $resultado = Invoke-NewSkillMirrors -BasePath $fixture -ExtraArgs @("-Force")

        $link = Join-Path $fixture ".agents\skills\preflight"
        Register-Junction -Path $link

        $resultado.ExitCode | Should -Be 0
        (Get-Item -LiteralPath $link -Force).LinkType | Should -Be "Junction"
        Get-MirrorTarget -Path $link | Should -Be (Join-Path $fixture ".claude\skills\preflight")
    }

    It "avisa sobre mirror orfao, que a governanca reprovaria como ORPHAN" {
        $fixture = New-MirrorFixture -Name "orfao"
        New-Item -ItemType Directory -Force -Path (Join-Path $fixture ".agents\skills\skill-fantasma") | Out-Null

        $resultado = Invoke-NewSkillMirrors -BasePath $fixture

        $resultado.Output | Should -Match "orfao"
        $resultado.ExitCode | Should -Not -Be 0
    }

    It "deixa a governanca de skills verde apos rodar num clone limpo" {
        $fixture = New-MirrorFixture -Name "governanca-verde"
        if ($fixture -match '~') {
            Set-ItResult -Skipped -Because "TestDrive resolveu para caminho 8.3 e o alvo da junction nao seria comparavel"
            return
        }

        Invoke-NewSkillMirrors -BasePath $fixture | Out-Null
        foreach ($skill in @(Get-ChildItem -LiteralPath (Join-Path $fixture ".github\skills") -Directory)) {
            Register-Junction -Path (Join-Path $fixture ".gemini\skills\$($skill.Name)")
        }
        foreach ($skill in @(Get-ChildItem -LiteralPath (Join-Path $fixture ".claude\skills") -Directory)) {
            Register-Junction -Path (Join-Path $fixture ".agents\skills\$($skill.Name)")
        }

        $governanca = Join-Path $script:RepoRoot "Tools\Test-SkillsGovernance.ps1"
        $outputPath = Join-Path $fixture "governanca-output.txt"
        $arguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $governanca, "-BasePath", $fixture)
        Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -Wait -NoNewWindow -RedirectStandardOutput $outputPath | Out-Null
        $saida = Get-Content -LiteralPath $outputPath -Raw

        $saida | Should -Match "GOVERNANCA DE SKILLS"
        $saida | Should -Not -Match "MIRROR_MISSING"
        $saida | Should -Not -Match "AGENTS_SKILL_MIRROR"
    }
}
