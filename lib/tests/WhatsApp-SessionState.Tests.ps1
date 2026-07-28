#
# Testes da deteccao de sessao ausente/zerada do WhatsApp (incidente de 27-28/07/2026).
#
# Este predicado decide se o motor ABORTA com ExitCode 21 (reautenticacao) ou tenta o
# bootstrap. Errar para um lado deixa a automacao gastando 3 tentativas contra um erro
# nao-transiente e reportando falha generica (ExitCode 24) — foi o que escondeu a causa
# das duas falhas da OBP-04. Errar para o outro aborta uma sessao valida sem motivo.
#
# A assinatura observada em producao apos o LOGOUT: o IndexedDB do WhatsApp Web fica
# apenas com CURRENT/LOG, sem MANIFEST-*, .ldb ou .log.
#

BeforeAll {
    $script:LibRoot = Split-Path -Parent $PSScriptRoot
    $script:ModuloJs = (Join-Path $script:LibRoot "whatsapp-session-state.js") -replace '\\', '/'
    $script:NodeDisponivel = [bool](Get-Command node -ErrorAction SilentlyContinue)
    # Base derivada do ambiente, nunca literal — o gate de portabilidade reprova
    # qualquer "C:\..." engessado no repositorio.
    $script:BaseTeste = Join-Path $env:TEMP "wa-session-state-tests"

    # Argumentos vao por argv, nunca interpolados no literal JS: um %TEMP% com aspas
    # quebraria o script e o teste falharia por sintaxe, nao por regressao.
    function Invoke-ModuloSessao {
        param(
            [string]$AuthPath,
            [string]$ClientId,
            [string]$Funcao = "sessaoPersistidaAusente"
        )
        $authJs = $AuthPath -replace '\\', '/'
        $codigo = "const m = require(process.argv[1]); process.stdout.write(String(m[process.argv[4]](process.argv[2], process.argv[3])))"
        return (& node -e $codigo $script:ModuloJs $authJs $ClientId $Funcao)
    }

    function Invoke-DeteccaoSessao {
        param([string]$AuthPath, [string]$ClientId)
        return Invoke-ModuloSessao -AuthPath $AuthPath -ClientId $ClientId -Funcao "sessaoPersistidaAusente"
    }

    function New-PerfilTeste {
        param([string]$ClientId, [string[]]$Arquivos)
        $idb = Join-Path $script:BaseTeste "session-$ClientId\Default\IndexedDB\https_web.whatsapp.com_0.indexeddb.leveldb"
        New-Item -ItemType Directory -Path $idb -Force | Out-Null
        foreach ($arquivo in $Arquivos) {
            $alvo = Join-Path $idb $arquivo
            if (-not (Test-Path $alvo)) { New-Item -ItemType File -Path $alvo | Out-Null }
        }
    }
}

AfterAll {
    if ($script:BaseTeste -and (Test-Path $script:BaseTeste)) {
        Remove-Item $script:BaseTeste -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Describe "sessaoPersistidaAusente" {

    It "considera ausente quando o perfil nem existe" {
        if (-not $script:NodeDisponivel) { Set-ItResult -Skipped -Because "node nao esta disponivel neste host"; return }
        Invoke-DeteccaoSessao -AuthPath $script:BaseTeste -ClientId "inexistente" | Should -Be "true"
    }

    It "considera ausente com o IndexedDB zerado pelo LOGOUT (so CURRENT/LOG)" {
        if (-not $script:NodeDisponivel) { Set-ItResult -Skipped -Because "node nao esta disponivel neste host"; return }
        New-PerfilTeste -ClientId "pos-logout" -Arquivos @("CURRENT", "LOG", "LOG.old")
        Invoke-DeteccaoSessao -AuthPath $script:BaseTeste -ClientId "pos-logout" | Should -Be "true" `
            -Because "esta e a assinatura exata observada apos o desvinculo do dispositivo"
    }

    It "considera presente com <Arquivo> no IndexedDB" -ForEach @(
        @{ Arquivo = "MANIFEST-000001" }
        @{ Arquivo = "001037.ldb" }
        @{ Arquivo = "001306.log" }
    ) {
        if (-not $script:NodeDisponivel) { Set-ItResult -Skipped -Because "node nao esta disponivel neste host"; return }
        $clientId = "com-dados-$($Arquivo -replace '[^a-zA-Z0-9]', '')"
        New-PerfilTeste -ClientId $clientId -Arquivos @("CURRENT", "LOG", $Arquivo)
        Invoke-DeteccaoSessao -AuthPath $script:BaseTeste -ClientId $clientId | Should -Be "false" `
            -Because "abortar com sessao valida em disco derruba a automacao sem motivo"
    }
}

Describe "Estado indeterminado (erro de leitura do perfil)" {
    # EPERM/ENOENT transitorio enquanto o Chrome ainda segura handles do perfil e
    # exatamente a janela que os drenos cobrem. Um booleano unico obrigaria as duas
    # perguntas a compartilhar a mesma resposta: "prossiga" viraria "sessao confirmada"
    # e o autenticador encerraria anunciando sucesso sobre uma gravacao nao confirmada.
    # Encena o erro trocando o diretorio do IndexedDB por um ARQUIVO: existsSync passa,
    # readdirSync estoura ENOTDIR.
    BeforeAll {
        $script:ClientIdIlegivel = "ilegivel"
        $idb = Join-Path $script:BaseTeste "session-$($script:ClientIdIlegivel)\Default\IndexedDB"
        New-Item -ItemType Directory -Path $idb -Force | Out-Null
        Set-Content -Path (Join-Path $idb "https_web.whatsapp.com_0.indexeddb.leveldb") -Value "nao sou um diretorio" -NoNewline
    }

    It "reporta INDETERMINADO em vez de AUSENTE ou PRESENTE" {
        if (-not $script:NodeDisponivel) { Set-ItResult -Skipped -Because "node nao esta disponivel neste host"; return }
        Invoke-ModuloSessao -AuthPath $script:BaseTeste -ClientId $script:ClientIdIlegivel `
            -Funcao "inspecionarSessaoPersistida" | Should -Be "INDETERMINADO"
    }

    It "abortar e confirmar-persistencia decidem de forma OPOSTA sobre o mesmo estado" {
        if (-not $script:NodeDisponivel) { Set-ItResult -Skipped -Because "node nao esta disponivel neste host"; return }

        Invoke-ModuloSessao -AuthPath $script:BaseTeste -ClientId $script:ClientIdIlegivel `
            -Funcao "sessaoPersistidaAusente" | Should -Be "false" `
            -Because "na duvida o bootstrap prossegue — nao se derruba automacao por erro de I/O"

        Invoke-ModuloSessao -AuthPath $script:BaseTeste -ClientId $script:ClientIdIlegivel `
            -Funcao "sessaoPersistidaConfirmada" | Should -Be "false" `
            -Because "na duvida a gravacao NAO esta confirmada — encerrar aqui exigiria novo QR"
    }
}

Describe "Consumidores usam o modulo compartilhado" {
    # A deteccao nasceu duplicada em WhatsApp-Core.js e open-whatsapp-session.js. Duas
    # copias divergentes significam um runtime abortando por sessao ausente enquanto o
    # outro tenta abrir — sem erro que denuncie a divergencia. Mesmo motivo que levou
    # whatsapp-auth-path.js a virar modulo unico (ver WhatsApp-AuthPath.Tests.ps1).
    It "<Fonte> requer whatsapp-session-state em vez de reimplementar" -ForEach @(
        @{ Fonte = "WhatsApp-Core.js" }
        @{ Fonte = "open-whatsapp-session.js" }
    ) {
        $conteudo = Get-Content (Join-Path $script:LibRoot $Fonte) -Raw
        $conteudo | Should -Match "require\('\./whatsapp-session-state'\)"
        $conteudo | Should -Not -Match "indexeddb\.leveldb" `
            -Because "o caminho do IndexedDB tem de existir num lugar so"
    }
}
