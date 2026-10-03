BeforeAll {
    $script:Sut = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "Tools/Test-AgentGuidelines.ps1"

    $script:HostPath = (Get-Process -Id $PID).Path

    # Cada teste monta o fixture num subdiretorio novo: o $TestDrive e compartilhado no Describe.
    function script:New-TestDir {
        $dir = Join-Path $TestDrive ([guid]::NewGuid().ToString())
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        return $dir
    }

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
        $out = & $script:HostPath -NoProfile -ExecutionPolicy Bypass -File $script:Sut -RootPath $Dir 2>&1 | Out-String
        [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = $out }
    }
}

Describe "Test-AgentGuidelines" {
    It "aprova um repositorio conforme" {
        $dir = script:New-TestDir
        script:New-Fixture -Dir $dir
        $r = script:Invoke-Sut -Dir $dir
        $r.ExitCode | Should -Be 0
    }

    It "reprova CLAUDE.md acima de 200 linhas" {
        $dir = script:New-TestDir
        script:New-Fixture -Dir $dir
        Set-Content -LiteralPath (Join-Path $dir "CLAUDE.md") -Value ((1..205) | ForEach-Object { "linha $_" })
        $r = script:Invoke-Sut -Dir $dir
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "GUIDELINE_TOO_LONG"
    }

    It "reprova pedido permanente de pensar mais" {
        $dir = script:New-TestDir
        script:New-Fixture -Dir $dir
        Add-Content -LiteralPath (Join-Path $dir "CLAUDE.md") -Value "- Always think step by step."
        $r = script:Invoke-Sut -Dir $dir
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "GUIDELINE_THINK_PHRASE"
    }

    It "ignora a frase dentro de cerca de codigo" {
        $dir = script:New-TestDir
        script:New-Fixture -Dir $dir
        Add-Content -LiteralPath (Join-Path $dir "CLAUDE.md") -Value "``````text`nthink step by step`n``````"
        $r = script:Invoke-Sut -Dir $dir
        $r.ExitCode | Should -Be 0
    }

    It "reprova effort e ultrathink em arquivo de contexto" {
        $dir = script:New-TestDir
        script:New-Fixture -Dir $dir
        Add-Content -LiteralPath (Join-Path $dir "AGENTS.md") -Value "Use ultrathink e effort alto."
        $r = script:Invoke-Sut -Dir $dir
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "GUIDELINE_SESSION_SETTING"
    }

    It "reprova import @ que nao resolve e aceita o que resolve" {
        $dir = script:New-TestDir
        script:New-Fixture -Dir $dir
        Set-Content -LiteralPath (Join-Path $dir "existe.md") -Value "ok"
        Add-Content -LiteralPath (Join-Path $dir "CLAUDE.md") -Value "Veja @existe.md e @docs/nao-existe.md"
        $r = script:Invoke-Sut -Dir $dir
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "nao-existe.md"
        $r.Output | Should -Not -Match "@existe.md nao resolve"
    }

    It "reprova subagente sem tools" {
        $dir = script:New-TestDir
        script:New-Fixture -Dir $dir
        Set-Content -LiteralPath (Join-Path $dir ".claude/agents/solto.md") -Value "---`nname: solto`n---`ncorpo"
        $r = script:Invoke-Sut -Dir $dir
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "SUBAGENT_TOOLS_MISSING"
    }

    It "reprova .gitignore sem CLAUDE.local.md" {
        $dir = script:New-TestDir
        script:New-Fixture -Dir $dir
        Set-Content -LiteralPath (Join-Path $dir ".gitignore") -Value "TASKS.md"
        $r = script:Invoke-Sut -Dir $dir
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "GUIDELINE_GITIGNORE_ENTRY"
    }

    It "nao reprova best-effort nem api/fast" {
        $dir = script:New-TestDir
        script:New-Fixture -Dir $dir
        Add-Content -LiteralPath (Join-Path $dir "CLAUDE.md") -Value "Melhor esforco: best-effort. Rota api/fast e /rapido."
        $r = script:Invoke-Sut -Dir $dir
        $r.ExitCode | Should -Be 0
    }

    It "reprova effort: e /fast isolado" {
        $dir = script:New-TestDir
        script:New-Fixture -Dir $dir
        Add-Content -LiteralPath (Join-Path $dir "CLAUDE.md") -Value "effort: high"
        Add-Content -LiteralPath (Join-Path $dir "AGENTS.md") -Value "Ative /fast antes."
        $r = script:Invoke-Sut -Dir $dir
        $r.ExitCode | Should -Be 1
        ([regex]::Matches($r.Output, "GUIDELINE_SESSION_SETTING")).Count | Should -Be 2
    }

    It "ignora pontuacao final no import e resolve o alvo" {
        $dir = script:New-TestDir
        script:New-Fixture -Dir $dir
        New-Item -ItemType Directory -Path (Join-Path $dir "docs") -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $dir "docs/x.md") -Value "ok"
        Add-Content -LiteralPath (Join-Path $dir "CLAUDE.md") -Value "Leia @docs/x.md."
        $r = script:Invoke-Sut -Dir $dir
        $r.ExitCode | Should -Be 0
    }

    It "nao trata @escopo/pacote sem extensao como import" {
        $dir = script:New-TestDir
        script:New-Fixture -Dir $dir
        Add-Content -LiteralPath (Join-Path $dir "CLAUDE.md") -Value "Tipos em @types/node e @vitejs/plugin-react."
        $r = script:Invoke-Sut -Dir $dir
        $r.ExitCode | Should -Be 0
    }

    It "ignora CLAUDE.md dentro de .claude/worktrees" {
        $dir = script:New-TestDir
        script:New-Fixture -Dir $dir
        $wt = Join-Path $dir ".claude/worktrees/x"
        New-Item -ItemType Directory -Path $wt -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $wt "CLAUDE.md") -Value "Always think step by step."
        $r = script:Invoke-Sut -Dir $dir
        $r.ExitCode | Should -Be 0
    }

    It "reprova subagente com tools vazio ou so no corpo" {
        $dir = script:New-TestDir
        script:New-Fixture -Dir $dir
        Set-Content -LiteralPath (Join-Path $dir ".claude/agents/vazio.md") -Value "---`nname: vazio`ntools:`n---`ncorpo"
        Set-Content -LiteralPath (Join-Path $dir ".claude/agents/corpo.md") -Value "---`nname: corpo`n---`ntools: Read"
        $r = script:Invoke-Sut -Dir $dir
        $r.ExitCode | Should -Be 1
        ([regex]::Matches($r.Output, "SUBAGENT_TOOLS_MISSING")).Count | Should -Be 2
    }
}
