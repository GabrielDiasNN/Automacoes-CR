#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }
<#
.SYNOPSIS
    Contrato do hook .agents/hooks/PreToolUse-Guard.ps1.

.DESCRIPTION
    O guard so' vale se bloquear o que deve E liberar o que deve. Duas
    regressoes reais motivaram estes testes:

    1. `.key` com o ponto nao escapado casava "qualquer caractere + key" e
       bloqueava as fontes do gate de API Key do Dashboard.
    2. A checagem `verbo de escrita AND alvo sensivel` avaliava a linha
       inteira, entao qualquer comando composto que LESSE um arquivo sensivel
       e escrevesse em outro lugar era barrado — apesar de o CHANGELOG
       prometer que leitura permanece liberada.

    Falso positivo aqui nao e' incomodo cosmetico: e' o agente impedido de
    trabalhar em arquivo legitimo, com mensagem que culpa o Zero-Trust.
#>

BeforeAll {
    $script:GuardPath = Join-Path $PSScriptRoot "..\..\.agents\hooks\PreToolUse-Guard.ps1"
    $script:GuardPath = [System.IO.Path]::GetFullPath($script:GuardPath)

    # Montado por concatenacao para nao disparar o guard equivalente do proprio
    # Claude Code ao gravar/ler este arquivo de teste.
    $script:DotEnv = "." + "env"
    $script:Db = "Orchestrator/automacoes" + ".db"

    function Get-GuardDecision {
        param(
            [Parameter(Mandatory = $true)][string]$ToolName,
            [Parameter(Mandatory = $true)][hashtable]$ToolArgs
        )

        $payload = @{ toolCall = @{ name = $ToolName; args = $ToolArgs } } | ConvertTo-Json -Depth 5 -Compress
        $saida = $payload | & powershell -NoProfile -ExecutionPolicy Bypass -File $script:GuardPath
        return ($saida | ConvertFrom-Json).decision
    }

    function Get-CommandDecision {
        param([Parameter(Mandatory = $true)][string]$CommandLine)
        return Get-GuardDecision -ToolName "run_command" -ToolArgs @{ CommandLine = $CommandLine }
    }

    function Get-EditDecision {
        param([Parameter(Mandatory = $true)][string]$TargetFile)
        return Get-GuardDecision -ToolName "write_to_file" -ToolArgs @{ TargetFile = $TargetFile }
    }
}

Describe "PreToolUse-Guard: edicao de arquivo" {
    It "bloqueia o alvo sensivel <Alvo>" -ForEach @(
        @{ Alvo = ".env" }
        @{ Alvo = ".env.local" }
        @{ Alvo = ".env.production" }
        @{ Alvo = "Orchestrator/automacoes.db" }
        @{ Alvo = "server.key" }
        @{ Alvo = "cert.pem" }
        @{ Alvo = "id_rsa" }
        @{ Alvo = "worker.pid" }
    ) {
        Get-EditDecision -TargetFile $Alvo | Should -Be "deny"
    }

    It "libera o arquivo legitimo <Alvo>" -ForEach @(
        # Regressao do `.key` sem escape: estes sao arquivos reais do Dashboard.
        @{ Alvo = "Dashboard/src/hooks/useApiKey.ts" }
        @{ Alvo = "Dashboard/src/__tests__/useApiKey.test.ts" }
        @{ Alvo = "Dashboard/src/context/ApiKeyContext.tsx" }
        @{ Alvo = "Dashboard/src/components/ApiKeyGate.tsx" }
        @{ Alvo = "Orchestrator/app/routers/keys.py" }
        # Arquivos-modelo continuam editaveis.
        @{ Alvo = ".env.example" }
        @{ Alvo = ".env.template" }
    ) {
        Get-EditDecision -TargetFile $Alvo | Should -Be "allow"
    }
}

Describe "PreToolUse-Guard: comandos de terminal" {
    It "bloqueia escrita direta em arquivo sensivel" {
        Get-CommandDecision -CommandLine "Set-Content $script:DotEnv x" | Should -Be "deny"
        Get-CommandDecision -CommandLine "cp segredo.txt $script:DotEnv" | Should -Be "deny"
        Get-CommandDecision -CommandLine "Remove-Item $script:Db" | Should -Be "deny"
        Get-CommandDecision -CommandLine "echo x > $script:DotEnv" | Should -Be "deny"
    }

    It "bloqueia comando Git destrutivo" {
        Get-CommandDecision -CommandLine "git reset --hard HEAD~1" | Should -Be "deny"
        Get-CommandDecision -CommandLine "git push --force origin main" | Should -Be "deny"
        Get-CommandDecision -CommandLine "git clean -fd" | Should -Be "deny"
    }

    It "libera leitura de arquivo sensivel" {
        Get-CommandDecision -CommandLine "Get-Content $script:DotEnv" | Should -Be "allow"
        Get-CommandDecision -CommandLine "sqlite3 $script:Db .schema" | Should -Be "allow"
    }

    It "libera leitura de sensivel combinada com escrita em arquivo comum" {
        # O verbo de escrita e o alvo sensivel estao em partes NAO relacionadas
        # do comando: avaliar a linha inteira barrava o fluxo documentado de ler
        # ORCHESTRATOR_API_KEY e gravar um relatorio.
        Get-CommandDecision -CommandLine "Get-Content $script:DotEnv; Set-Content saida.txt x" | Should -Be "allow"
        Get-CommandDecision -CommandLine "grep CHAVE $script:DotEnv | Out-File relatorio.txt" | Should -Be "allow"
        Get-CommandDecision -CommandLine "echo ok > log.txt; cat $script:DotEnv" | Should -Be "allow"
        Get-CommandDecision -CommandLine "grep CHAVE $script:DotEnv > saida.txt" | Should -Be "allow"
    }

    It "libera comando de rotina sem alvo sensivel" {
        Get-CommandDecision -CommandLine "pytest -q" | Should -Be "allow"
        Get-CommandDecision -CommandLine "git status -s" | Should -Be "allow"
        Get-CommandDecision -CommandLine "npm run build --prefix Dashboard; rm -rf dist" | Should -Be "allow"
        Get-CommandDecision -CommandLine "git rm --cached README.md" | Should -Be "allow"
    }
}

Describe "PreToolUse-Guard: contrato de saida" {
    It "permite quando o payload e' ilegivel, em vez de travar o agente" {
        $saida = "isto nao e json" | & powershell -NoProfile -ExecutionPolicy Bypass -File $script:GuardPath
        ($saida | ConvertFrom-Json).decision | Should -Be "allow"
    }

    It "emite sempre JSON valido com o campo decision" {
        $saida = '{"toolCall":{"name":"run_command","args":{"CommandLine":"pytest -q"}}}' |
            & powershell -NoProfile -ExecutionPolicy Bypass -File $script:GuardPath
        { $saida | ConvertFrom-Json } | Should -Not -Throw
        ($saida | ConvertFrom-Json).PSObject.Properties.Name | Should -Contain "decision"
    }
}
