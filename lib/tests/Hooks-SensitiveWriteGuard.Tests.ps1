#
# Testes Pester do hook Assert-SensitiveWriteGuard.ps1 e da fiacao que o invoca.
#
# Motivacao: a bateria original deste guard foi ad-hoc e sumiu com a sessao. Pior,
# o metodo de teste entao documentado alimentava o payload por
# $env:CLAUDE_TOOL_INPUT — que Get-HookPayload aceita, mas NAO e como o harness
# entrega o payload. Foi assim que tres hooks ficaram inertes sem ninguem notar.
# Aqui o payload vai por STDIN, que e o caminho real.
#
# O bloco "Fiacao" e o que protege contra a regressao mais cara: o script pode
# sair 2 corretamente e a invocacao do settings.json engolir o codigo. Rodar o
# script direto nao prova nada sobre o gate; os dois caminhos divergem.
#

BeforeAll {
    $script:RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $script:Guard = Join-Path $script:RepoRoot '.claude\hooks\Assert-SensitiveWriteGuard.ps1'
    $script:AntigravityGuard = Join-Path $script:RepoRoot '.agents\hooks\PreToolUse-Guard.ps1'
    $script:HookCommon = Join-Path $script:RepoRoot '.claude\hooks\HookCommon.psm1'
    $script:SettingsPath = Join-Path $script:RepoRoot '.claude\settings.json'

    $settings = Get-Content -LiteralPath $script:SettingsPath -Raw | ConvertFrom-Json
    $script:FiacaoComando = (
        $settings.hooks.PreToolUse | Where-Object { $_.matcher -eq 'Bash|PowerShell' }
    ).hooks[0].command

    $script:HostPath = (Get-Command -Name 'pwsh' -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1).Source
    if (-not $script:HostPath) {
        $script:HostPath = (Get-Command -Name 'powershell' -CommandType Application |
            Select-Object -First 1).Source
    }

    function New-Payload {
        param(
            [Parameter(Mandatory)][string]$Command,
            [string]$ToolName = 'Bash'
        )
        # Formato aninhado, identico ao que o harness entrega.
        return (@{ tool_name = $ToolName; tool_input = @{ command = $Command } } |
                ConvertTo-Json -Compress)
    }

    function Invoke-GuardPorStdin {
        <#
            Executa o SCRIPT diretamente (pwsh -File), com o payload por stdin.
            Mede o comportamento do guard, nao o da fiacao.
        #>
        param(
            [Parameter(Mandatory)][string]$Command,
            [string]$ToolName = 'Bash'
        )

        $anterior = $env:CLAUDE_TOOL_INPUT
        $env:CLAUDE_TOOL_INPUT = $null
        try {
            (New-Payload -Command $Command -ToolName $ToolName) |
                & $script:HostPath -NoProfile -NonInteractive -File $script:Guard 2>$null | Out-Null
            return $LASTEXITCODE
        }
        finally {
            $env:CLAUDE_TOOL_INPUT = $anterior
        }
    }

    function Invoke-AntigravityGuardDecision {
        <#
            Executa .agents/hooks/PreToolUse-Guard.ps1 (o guard do Antigravity)
            com payload por stdin no formato toolCall. Devolve "allow"/"deny".
            Serve para provar que os DOIS guards de shell decidem igual — a
            logica agora e' compartilhada (Get-SensitiveWriteInCommand).
        #>
        param([Parameter(Mandatory)][string]$Command)

        $payload = @{ toolCall = @{ name = 'run_command'; args = @{ CommandLine = $Command } } } |
            ConvertTo-Json -Compress
        $saida = $payload | & $script:HostPath -NoProfile -NonInteractive -File $script:AntigravityGuard 2>$null
        return ($saida | ConvertFrom-Json).decision
    }

    function Invoke-GuardPelaFiacao {
        <#
            Executa o comando LITERAL do settings.json, na mesma forma que o
            harness usa (shell powershell => -Command), com payload por stdin.
        #>
        param(
            [Parameter(Mandatory)][string]$Command,
            [string]$ProjectDir = $null
        )

        $anteriorInput = $env:CLAUDE_TOOL_INPUT
        $anteriorDir = $env:CLAUDE_PROJECT_DIR
        $env:CLAUDE_TOOL_INPUT = $null
        $env:CLAUDE_PROJECT_DIR = if ($ProjectDir) { $ProjectDir } else { $script:RepoRoot }
        try {
            (New-Payload -Command $Command) |
                & $script:HostPath -NoProfile -NonInteractive -Command $script:FiacaoComando 2>$null |
                Out-Null
            return $LASTEXITCODE
        }
        finally {
            $env:CLAUDE_TOOL_INPUT = $anteriorInput
            $env:CLAUDE_PROJECT_DIR = $anteriorDir
        }
    }
}

Describe "Assert-SensitiveWriteGuard - bloqueia escrita" {
    It "bloqueia <Comando>" -ForEach @(
        @{ Comando = "Set-Content .env -Value 'x'" }
        @{ Comando = 'echo x > .env' }
        @{ Comando = "Add-Content .env 'x'" }
        @{ Comando = 'Remove-Item orchestrator.pid' }
        @{ Comando = 'rm worker.pid' }
        @{ Comando = 'Out-File -FilePath automacoes.db' }
        @{ Comando = 'Get-Content a.txt > orchestrator.db' }
        @{ Comando = "Get-ChildItem; Set-Content .env -Value 'y'" }
        @{ Comando = 'sed -i s/a/b/ .env' }
        @{ Comando = 'New-Item -Path worker.pid -ItemType File' }
        # Conservador de proposito: fonte e destino de Copy-Item nao sao
        # distinguiveis por posicao sem parser. Documentado no README.
        @{ Comando = 'Copy-Item .env .env.bak' }
    ) {
        Invoke-GuardPorStdin -Command $Comando | Should -Be 2
    }
}

Describe "Assert-SensitiveWriteGuard - nao bloqueia leitura nem vizinhanca" {
    It "libera <Comando>" -ForEach @(
        @{ Comando = 'Get-Content .env' }
        @{ Comando = 'grep CHAVE .env' }
        # Redirecionamento e fronteira: o alvo e backup.txt, nao .env.
        @{ Comando = 'Get-Content .env > backup.txt' }
        @{ Comando = 'grep CHAVE .env > /tmp/out.txt' }
        @{ Comando = 'Get-Content .env | Set-Content saida.txt' }
        @{ Comando = "Set-Content .env.example -Value 'x'" }
        @{ Comando = 'Remove-Item .venv -Recurse -Force' }
        @{ Comando = 'Get-Content .env 2>&1' }
        @{ Comando = 'Get-Content .env > $null' }
        @{ Comando = 'Set-Content nota.md -Value "cita orchestrator.pid"' }
        @{ Comando = 'pytest -q' }
    ) {
        Invoke-GuardPorStdin -Command $Comando | Should -Be 0
    }
}

Describe "Assert-SensitiveWriteGuard - ferramenta PowerShell" {
    It "le o comando do payload da ferramenta PowerShell, nao so da Bash" {
        Invoke-GuardPorStdin -Command "Set-Content .env -Value 'x'" -ToolName 'PowerShell' |
            Should -Be 2
    }
}

Describe "Fiacao do settings.json" {
    # Sem estes casos os testes acima nao protegem nada: o guard pode sair 2 e a
    # invocacao do settings.json devolver 1 (que o harness descarta) ou 0.

    It "propaga o exit 2 do guard pela invocacao real do settings.json" {
        Invoke-GuardPelaFiacao -Command "Set-Content .env -Value 'x'" | Should -Be 2
    }

    It "propaga o exit 0 do guard pela invocacao real do settings.json" {
        Invoke-GuardPelaFiacao -Command 'Get-Content .env' | Should -Be 0
    }

    It "falha FECHADO quando o modulo compartilhado quebra antes da decisao" {
        # Reproduz o cenario em que HookCommon.psm1 some, tem erro de parse ou
        # dispara sob Set-StrictMode: a excecao terminante encerra o pwsh ANTES
        # do exit do script. Sem try/catch na fiacao isso devolvia 1 (gate
        # inerte) ou 0 (aprovado) — falha silenciosa identica a que o commit
        # original corrigiu, deslocada uma casa.
        $raizFalsa = Join-Path $TestDrive 'raiz-quebrada'
        $hooksFalsos = Join-Path $raizFalsa '.claude\hooks'
        New-Item -ItemType Directory -Force -Path $hooksFalsos | Out-Null

        Copy-Item -LiteralPath $script:Guard -Destination $hooksFalsos
        Set-Content -LiteralPath (Join-Path $hooksFalsos 'HookCommon.psm1') `
            -Value "throw 'falha simulada de carga do modulo'" -Encoding utf8

        Invoke-GuardPelaFiacao -Command 'Get-ChildItem' -ProjectDir $raizFalsa |
            Should -Be 2
    }
}

Describe "Test-SensitiveTarget - alvos canonicos (fonte unica)" {
    # Espelha a cobertura de alvo de lib/tests/PreToolUse-Guard.Tests.ps1: o
    # padrao canonico ganhou .env.local/.env.production, .pem/.key/.pfx/.p12/
    # .crt/.keystore e id_rsa, mas a suite deste lado nao exercitava nada disso
    # — passava justamente por nao tocar no que mudou.
    BeforeAll {
        Import-Module $script:HookCommon -Force -DisableNameChecking
    }

    It "reconhece como sensivel: <Alvo>" -ForEach @(
        @{ Alvo = '.env' }
        @{ Alvo = '.env.local' }
        @{ Alvo = '.env.production' }
        @{ Alvo = 'Orchestrator/automacoes.db' }
        @{ Alvo = 'server.key' }
        @{ Alvo = 'cert.pem' }
        @{ Alvo = 'client.pfx' }
        @{ Alvo = 'store.keystore' }
        @{ Alvo = 'id_rsa' }
        @{ Alvo = '.ssh/id_rsa' }
        @{ Alvo = 'worker.pid' }
    ) {
        Test-SensitiveTarget -Value $Alvo | Should -BeTrue
    }

    It "NAO reconhece como sensivel: <Alvo>" -ForEach @(
        @{ Alvo = '.env.example' }
        @{ Alvo = '.env.template' }
        @{ Alvo = '.env.sample' }
        @{ Alvo = 'Dashboard/src/hooks/useApiKey.ts' }
        @{ Alvo = 'Dashboard/src/context/ApiKeyContext.tsx' }
        @{ Alvo = 'config/valid_rsa_settings.py' }
        @{ Alvo = 'Orchestrator/tests/fixtures/cert.pem.md' }
        @{ Alvo = 'notes.keystore.txt' }
        @{ Alvo = '.venv/Scripts/python.exe' }
    ) {
        Test-SensitiveTarget -Value $Alvo | Should -BeFalse
    }
}

Describe "Convergencia dos dois guards de shell" {
    # A logica de deteccao de escrita sensivel em comando agora vive em
    # Get-SensitiveWriteInCommand (HookCommon.psm1). Este bloco prova que o
    # guard do Claude Code (exit 2/0) e o do Antigravity (deny/allow) decidem
    # IGUAL para o mesmo comando — antes divergiam (aliases num, `shred` no
    # outro, lookbehind de digito so' num).
    It "decidem igual para: <Comando>" -ForEach @(
        @{ Comando = 'sc .env x' }
        @{ Comando = 'ac .env x' }
        @{ Comando = 'ni .env' }
        @{ Comando = 'del .env' }
        @{ Comando = 'clc .env' }
        @{ Comando = 'echo x 1> .env' }
        @{ Comando = 'Get-Content a.txt 2> .env' }
        @{ Comando = 'shred .env' }
        @{ Comando = 'Set-Content .env x' }
        @{ Comando = 'Get-Content .env' }
        @{ Comando = 'grep CHAVE .env > saida.txt' }
        @{ Comando = 'Get-Content .env; Set-Content saida.txt x' }
        @{ Comando = 'Set-Content nota.md -Value "cita orchestrator.pid"' }
    ) {
        $claude = if ((Invoke-GuardPorStdin -Command $Comando) -eq 2) { 'deny' } else { 'allow' }
        $antigravity = Invoke-AntigravityGuardDecision -Command $Comando
        $antigravity | Should -Be $claude
    }
}
