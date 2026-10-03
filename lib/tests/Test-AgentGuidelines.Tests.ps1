BeforeAll {
    $script:Sut = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "Tools/Test-AgentGuidelines.ps1"

    function script:New-Fixture {
        param([string]$Dir)
        New-Item -ItemType Directory -Path (Join-Path $Dir ".claude/agents") -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $Dir "CLAUDE.md") -Value "# Projeto`nTexto neutro."
        Set-Content -LiteralPath (Join-Path $Dir "AGENTS.md") -Value "# Agentes"
        Set-Content -LiteralPath (Join-Path $Dir ".gitignore") -Value "CLAUDE.local.md`nTASKS.md"
        Set-Content -LiteralPath (Join-Path $Dir ".claude/agents/rev.md") -Value "---`nname: rev`ntools: Read, Grep`n---`ncorpo"
    }

    function script:Invoke-Sut {
        param([string]$Dir)
        $out = & pwsh -NoProfile -ExecutionPolicy Bypass -File $script:Sut -RootPath $Dir 2>&1 | Out-String
        [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = $out }
    }
}

Describe "Test-AgentGuidelines" {
    It "aprova um repositorio conforme" {
        script:New-Fixture -Dir $TestDrive
        $r = script:Invoke-Sut -Dir $TestDrive
        $r.ExitCode | Should -Be 0
    }

    It "reprova CLAUDE.md acima de 200 linhas" {
        script:New-Fixture -Dir $TestDrive
        Set-Content -LiteralPath (Join-Path $TestDrive "CLAUDE.md") -Value ((1..205) | ForEach-Object { "linha $_" })
        $r = script:Invoke-Sut -Dir $TestDrive
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "GUIDELINE_TOO_LONG"
    }

    It "reprova pedido permanente de pensar mais" {
        script:New-Fixture -Dir $TestDrive
        Add-Content -LiteralPath (Join-Path $TestDrive "CLAUDE.md") -Value "- Always think step by step."
        $r = script:Invoke-Sut -Dir $TestDrive
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "GUIDELINE_THINK_PHRASE"
    }

    It "ignora a frase dentro de cerca de codigo" {
        script:New-Fixture -Dir $TestDrive
        Add-Content -LiteralPath (Join-Path $TestDrive "CLAUDE.md") -Value "``````text`nthink step by step`n``````"
        $r = script:Invoke-Sut -Dir $TestDrive
        $r.ExitCode | Should -Be 0
    }

    It "reprova effort e ultrathink em arquivo de contexto" {
        script:New-Fixture -Dir $TestDrive
        Add-Content -LiteralPath (Join-Path $TestDrive "AGENTS.md") -Value "Use ultrathink e effort alto."
        $r = script:Invoke-Sut -Dir $TestDrive
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "GUIDELINE_SESSION_SETTING"
    }

    It "reprova import @ que nao resolve e aceita o que resolve" {
        script:New-Fixture -Dir $TestDrive
        Set-Content -LiteralPath (Join-Path $TestDrive "existe.md") -Value "ok"
        Add-Content -LiteralPath (Join-Path $TestDrive "CLAUDE.md") -Value "Veja @existe.md e @docs/nao-existe.md"
        $r = script:Invoke-Sut -Dir $TestDrive
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "nao-existe.md"
        $r.Output | Should -Not -Match "@existe.md nao resolve"
    }

    It "reprova subagente sem tools" {
        script:New-Fixture -Dir $TestDrive
        Set-Content -LiteralPath (Join-Path $TestDrive ".claude/agents/solto.md") -Value "---`nname: solto`n---`ncorpo"
        $r = script:Invoke-Sut -Dir $TestDrive
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "SUBAGENT_TOOLS_MISSING"
    }

    It "reprova .gitignore sem CLAUDE.local.md" {
        script:New-Fixture -Dir $TestDrive
        Set-Content -LiteralPath (Join-Path $TestDrive ".gitignore") -Value "TASKS.md"
        $r = script:Invoke-Sut -Dir $TestDrive
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "GUIDELINE_GITIGNORE_ENTRY"
    }
}
