#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }
<#
.SYNOPSIS
    Contrato do hook .agents/hooks/PreToolUse-Guard.ps1.

.DESCRIPTION
    O guard so' vale se bloquear o que deve E liberar o que deve. Regressoes
    reais motivaram estes testes:

    1. `.key` com o ponto nao escapado casava "qualquer caractere + key" e
       bloqueava as fontes do gate de API Key do Dashboard.
    2. A checagem `verbo de escrita AND alvo sensivel` avaliava a linha
       inteira, entao qualquer comando composto que LESSE um arquivo sensivel
       e escrevesse em outro lugar era barrado — apesar de o CHANGELOG
       prometer que leitura permanece liberada.
    3. A deteccao de flag de forca em `git push`/`git clean` usava `.*` guloso
       sem ancorar o `-` a inicio de token: `git push origin feat/novo-fluxo`
       e `git push origin sync-from-main` eram bloqueados como `--force`
       porque o hifen de "novo-fluxo"/"sync-from" casava a mesma alternativa.
    4. Aliases nativos do PowerShell (`sc`, `ac`, `ni`, ...) nao estavam no
       padrao de verbo de escrita: `ac .env x` burlava o Zero-Trust.
    5. O lookbehind `(?<![0-9])` no padrao de redirecionamento excluia
       QUALQUER `>` precedido de digito, inclusive `1> .env`/`2> .env`
       (descritor explicito escrevendo em arquivo real) — nao so' `2>&1`.
    6. `id_rsa` sem borda de caminho casava como substring livre
       (`valid_rsa_settings.py` continha "id_rsa" no meio de "val-id_rsa-").
    7. As extensoes de credencial (`.pem`, `.key`, ...) aceitavam outro ponto
       depois: `cert.pem.md` era bloqueado como se fosse a chave em si.
    8. `$DestructiveGitPattern` exigia o subcomando COLADO no `git`: `git -C .
       push --force`, `git -c k=v reset --hard` e `git.exe push --force`
       escapavam da governanca Git.
    9. O padrao de verbo de escrita e o de redirecionamento eram COPIA local
       divergente de cada guard (Antigravity cobria aliases, Claude Code
       cobria `shred`). Agora os dois consomem Get-SensitiveWriteInCommand de
       HookCommon.psm1 e a decisao e' identica.
   10. `[regex]::Replace` do descarte de `-Value`/`-Body` era case-sensitive:
       `-value` minusculo nao era descartado e o texto escrito voltava a ser
       inspecionado como alvo.
   11. `id_rsa` como nome nu num comando (`rm id_rsa`) escapava: numa linha de
       comando `^` e' o inicio do comando e espaco nao e' separador de caminho.

    Falso positivo aqui nao e' incomodo cosmetico: e' o agente impedido de
    trabalhar em arquivo legitimo, com mensagem que culpa o Zero-Trust. Falso
    negativo e' pior: e' o Zero-Trust burlado sem ninguem notar.
#>

BeforeAll {
    $script:GuardPath = Join-Path $PSScriptRoot "..\..\.agents\hooks\PreToolUse-Guard.ps1"
    $script:GuardPath = [System.IO.Path]::GetFullPath($script:GuardPath)

    # Montado por concatenacao para nao disparar o guard equivalente do proprio
    # Claude Code ao gravar/ler este arquivo de teste.
    $script:DotEnv = "." + "env"
    $script:Db = "Orchestrator/automacoes" + ".db"

    # hooks.json invoca o guard com `pwsh` (PowerShell 7); testar so' com
    # `powershell` (5.1) valida um runtime diferente do que roda em producao.
    # Mesma escolha de host de lib/tests/Hooks-SensitiveWriteGuard.Tests.ps1.
    $script:HostPath = (Get-Command -Name 'pwsh' -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1).Source
    if (-not $script:HostPath) {
        $script:HostPath = (Get-Command -Name 'powershell' -CommandType Application |
            Select-Object -First 1).Source
    }

    function Get-GuardDecision {
        param(
            [Parameter(Mandatory = $true)][string]$ToolName,
            [Parameter(Mandatory = $true)][hashtable]$ToolArgs
        )

        $payload = @{ toolCall = @{ name = $ToolName; args = $ToolArgs } } | ConvertTo-Json -Depth 5 -Compress
        $saida = $payload | & $script:HostPath -NoProfile -ExecutionPolicy Bypass -File $script:GuardPath
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
        # `id_rsa` sem borda de caminho casava como substring livre: este nome
        # contem "id_rsa" no meio de "val-id_rsa-settings".
        @{ Alvo = "config/valid_rsa_settings.py" }
        # Extensao de credencial seguida de outro ponto: nao e' o arquivo de
        # chave em si, e' documentacao/fixture nomeada a partir dele.
        @{ Alvo = "Orchestrator/tests/fixtures/cert.pem.md" }
        @{ Alvo = "notes.keystore.txt" }
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
        Get-CommandDecision -CommandLine "git push -f origin main" | Should -Be "deny"
        Get-CommandDecision -CommandLine "git push origin main --force-with-lease" | Should -Be "deny"
        Get-CommandDecision -CommandLine "git clean -fd" | Should -Be "deny"
    }

    It "bloqueia Git destrutivo com opcao global antes do subcomando <Comando>" -ForEach @(
        # O padrao exigia o subcomando colado no `git`: qualquer opcao global
        # (`-C`, `-c`, `--no-pager`) ou o binario pelo nome completo desarmava.
        @{ Comando = "git -C . push --force" }
        @{ Comando = "git -c user.name=x reset --hard" }
        @{ Comando = "git --no-pager reset --hard HEAD~1" }
        @{ Comando = "git.exe push --force origin main" }
    ) {
        Get-CommandDecision -CommandLine $Comando | Should -Be "deny"
    }

    It "libera <Comando> (opcao global nao transforma subcomando benigno em destrutivo)" -ForEach @(
        # A relaxacao do padrao nao pode reintroduzir falso positivo: o grupo
        # de opcoes globais so' casa tokens que PARECEM opcao, nao texto livre.
        @{ Comando = 'git commit -m "corrige o fluxo de reset --hard nos docs"' }
        @{ Comando = "git -c core.pager=cat commit -m ajuste" }
        @{ Comando = "git -C . status -s" }
    ) {
        Get-CommandDecision -CommandLine $Comando | Should -Be "allow"
    }

    It "libera <Comando> (hifen de nome de branch nao e' flag de forca)" -ForEach @(
        # `.*` guloso sem ancora de token casava o hifen destas branches como
        # se fosse `-f`/`--force`: nenhuma delas passa flag de forca nenhuma.
        @{ Comando = "git push origin feat/novo-fluxo" }
        @{ Comando = "git push origin sync-from-main" }
        @{ Comando = "git push origin fix/hooks-antigravity-achados-revisao" }
    ) {
        Get-CommandDecision -CommandLine $Comando | Should -Be "allow"
    }

    It "bloqueia alias nativo <Alias> de escrita em arquivo sensivel" -ForEach @(
        # Aliases nativos do PowerShell nao estavam no padrao de verbo de
        # escrita: burlavam o Zero-Trust tao facilmente quanto o nome completo.
        # $script:DotEnv so' existe a partir de BeforeAll (fase Run), entao o
        # comando e' montado aqui dentro, nao no array -ForEach (fase Discovery,
        # que roda ANTES de BeforeAll — interpolar $script:DotEnv la' produz
        # string vazia e o teste vira falso positivo silencioso).
        @{ Alias = "sc"; Sufixo = "x" }
        @{ Alias = "ac"; Sufixo = "x" }
        @{ Alias = "ni"; Sufixo = "" }
        @{ Alias = "clc"; Sufixo = "" }
        @{ Alias = "ri"; Sufixo = "" }
        @{ Alias = "del"; Sufixo = "" }
    ) {
        $comando = "$Alias $script:DotEnv $Sufixo".TrimEnd()
        Get-CommandDecision -CommandLine $comando | Should -Be "deny"
    }

    It "bloqueia escrita sensivel via [System.IO.File]::" {
        $comando = "[System.IO.File]::WriteAllText('$script:DotEnv','x')"
        Get-CommandDecision -CommandLine $comando | Should -Be "deny"
    }

    It "bloqueia mesmo com -value em caixa baixa (descarte case-insensitive)" {
        # `[regex]::Replace` era case-sensitive: `-value` minusculo nao era
        # descartado e o texto voltava a ser inspecionado. Aqui o alvo real e'
        # $script:DotEnv, entao tem de bloquear independente da caixa da flag.
        $comando = "Set-Content $script:DotEnv -value 'qualquer'"
        Get-CommandDecision -CommandLine $comando | Should -Be "deny"
    }

    It "libera mencao a arquivo sensivel dentro de -value minusculo" {
        # A contrapartida: -value (minusculo) tem de ser descartado como dado,
        # senao citar orchestrator.pid num texto vira bloqueio.
        Get-CommandDecision -CommandLine "Set-Content nota.md -value 'cita orchestrator.pid'" |
            Should -Be "allow"
    }

    It "bloqueia id_rsa como nome nu no comando" {
        # `(?:^|[\\/])` nao cobria `rm id_rsa`: `^` e' o inicio do comando
        # inteiro e o espaco antes de `id_rsa` nao e' separador de caminho.
        Get-CommandDecision -CommandLine "rm id_rsa" | Should -Be "deny"
        Get-CommandDecision -CommandLine "Remove-Item ~/.ssh/id_rsa" | Should -Be "deny"
    }

    It "bloqueia redirecionamento com descritor numerico explicito (fd <Fd>)" -ForEach @(
        # O lookbehind `(?<![0-9])` excluia QUALQUER `>` precedido de digito,
        # nao so' a duplicacao de descritor (`2>&1`) que motivou a exclusao.
        # Mesmo cuidado de fase acima: comando montado dentro do It.
        @{ Fd = "1"; Prefixo = "echo x" }
        @{ Fd = "2"; Prefixo = "Get-Content a.txt" }
    ) {
        $comando = "$Prefixo $Fd> $script:DotEnv"
        Get-CommandDecision -CommandLine $comando | Should -Be "deny"
    }

    It "libera duplicacao de descritor (2>&1), que nao e' escrita em arquivo" {
        Get-CommandDecision -CommandLine "Get-Content $script:DotEnv 2>&1" | Should -Be "allow"
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
        $saida = "isto nao e json" | & $script:HostPath -NoProfile -ExecutionPolicy Bypass -File $script:GuardPath
        ($saida | ConvertFrom-Json).decision | Should -Be "allow"
    }

    It "emite sempre JSON valido com o campo decision" {
        $saida = '{"toolCall":{"name":"run_command","args":{"CommandLine":"pytest -q"}}}' |
            & $script:HostPath -NoProfile -ExecutionPolicy Bypass -File $script:GuardPath
        { $saida | ConvertFrom-Json } | Should -Not -Throw
        ($saida | ConvertFrom-Json).PSObject.Properties.Name | Should -Contain "decision"
    }
}
