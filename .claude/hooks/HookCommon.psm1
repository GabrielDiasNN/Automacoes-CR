#Requires -Version 5.1
<#
.SYNOPSIS
    Funcoes compartilhadas pelos hooks de .claude/hooks.

.NOTES
    Tools/Test-SourceEncoding.ps1 emite os achados via Write-Host e Out-Host,
    que escrevem no host e NAO no pipeline. Redirecionar com 2>&1 dentro do
    mesmo processo perde o detalhe. Por isso Invoke-EncodingCheck executa o
    verificador como processo filho, onde tudo converge para o stdout do
    processo e pode ser capturado integralmente.
#>

Set-StrictMode -Version Latest

# Fonte unica dos alvos sensiveis. Antes a lista vivia duplicada em dois lugares
# (guard inline de Edit|Write no settings.json e Assert-SensitiveWriteGuard.ps1)
# com predicados DIFERENTES — EndsWith('.env') de um lado, regex do outro — de
# modo que a cobertura efetiva dependia de qual ferramenta o agente escolheu.
# Manter aqui o padrao E o predicado elimina a divergencia por construcao.
#
# `.env`: `(?![\w])` impede casar `.environment`/`.envrc`; a alternancia seguinte
# libera apenas os arquivos-modelo (.env.example/.env.template/.env.sample).
# Bloquear `.env*` e abrir excecao nominal e' o inverso da versao anterior deste
# padrao (que liberava todo sufixo via `(?![\w.\-])`) e deixava passar
# `.env.local`/`.env.production` — arquivos de segredo reais. ".venv" nao casa
# (o ponto e seguido de 'v', nao de 'e').
#
# Extensoes de credencial: o ponto e' escapado e a fronteira exclui outro ponto
# alem de palavra (`(?![\w.])`), senao `cert.pem.md`/`notes.keystore.txt`
# seriam bloqueados por engano.
#
# `id_rsa` exige inicio de string, separador de caminho OU fronteira de token
# antes: sem essa ancora a alternativa casa como substring livre e bloqueia
# arquivos legitimos como `valid_rsa_settings.py` (contem "id_rsa" no meio de
# "valid_rsa..."). Numa LINHA DE COMANDO `^` e' o inicio do comando inteiro e
# espaco nao e' separador de caminho, entao `[\s\\/'"]` cobre `rm id_rsa` sem
# reabrir `valid_rsa` (precedido de `l`, que nao esta na classe).
$script:SensitiveTargetPattern = '(' +
    '\.env(?![\w])(?!\.(?:example|template|sample)(?![\w]))' +
    '|automacoes\.db|orchestrator\.db' +
    '|orchestrator\.pid|worker\.pid' +
    '|\.(?:pem|key|pfx|p12|crt|keystore)(?![\w.])' +
    '|(?:^|[\s\\/''"])id_rsa(?![\w])' +
')'

# Verbos de escrita/remocao em terminal — uniao dos dois guards que consomem
# este modulo (`.agents/hooks/PreToolUse-Guard.ps1` e
# `.claude/hooks/Assert-SensitiveWriteGuard.ps1`). Antes cada guard tinha copia
# propria e divergente: o do Antigravity cobria aliases nativos (`sc`, `ac`,
# `ni`...) e `[System.IO.File]::`, o do Claude Code cobria `shred`. Resultado:
# `sc .env x` passava no Claude Code e `shred .env` passava no Antigravity.
# Aqui a lista e' uma so'.
#
# Aliases e comandos curtos (`sc`, `ni`, `rm`, `cp`...) usam a fronteira
# `(?<![\w\\/]) ... (?![\w\\/])` em vez de `\b`: `\b` casa o componente `\sc\`
# de um CAMINHO (`\` e' non-word), entao `Get-Content .env "C:\dir\sc\x"` — um
# comando que so' le — batia em verbo e alvo no mesmo segmento e era bloqueado.
# Excluir `\` e `/` da fronteira mantem `sc .env`, `;sc .env` e `| sc .env`
# como escrita e libera o `sc` que e' pasta. `truncate`/`shred`/`sed` sao
# distintos o bastante para seguir com `\b`.
$script:SensitiveWriteVerbPattern = '(' +
    'Set-Content|Add-Content|Out-File|Tee-Object|Clear-Content' +
    '|Remove-Item|Move-Item|Copy-Item|New-Item|Rename-Item' +
    '|\[System\.IO\.File\]::(?:Write|Append|Delete|Copy|Move)' +
    '|(?<![\w\\/])(?:sc|ac|ni|ri|rni|cpi|mi|si|clc)(?![\w\\/])' +
    '|(?<![\w\\/])(?:rm|mv|cp|dd|tee|del|erase)(?![\w\\/])' +
    '|\btruncate\b|\bshred\b' +
    '|\bsed\b[^|;]*-i' +
')'

# Redirecionamento: `>` ou `>>` NAO seguido de `&` ou `$` (exclui `2>&1` e
# `>$null`). O lookbehind `(?<![0-9])` que os guards traziam excluia QUALQUER
# `>` precedido de digito, inclusive `1> .env`/`2> .env` (descritor explicito
# escrevendo em arquivo real) — o proprio caso que o guard promete cobrir. O
# lookahead sozinho ja basta para `2>&1`.
$script:SensitiveRedirectPattern = '>>?(?!\s*[&$])'

# Lista legivel dos alvos protegidos, para a mensagem de bloqueio devolvida ao
# agente. Fonte unica: se um nome entra em $script:SensitiveTargetPattern, entra
# aqui tambem, senao a mensagem culpa o Zero-Trust por um arquivo que ela nao
# lista e o agente conclui (erradamente) que e' falso positivo.
$script:SensitiveTargetDescription = @(
    '.env (exceto .env.example/.env.template/.env.sample)',
    'bancos locais: automacoes.db, orchestrator.db',
    'PIDs: orchestrator.pid, worker.pid',
    'chaves/certificados: .pem, .key, .pfx, .p12, .crt, .keystore, id_rsa'
) -join '; '

function Get-SensitiveTargetPattern {
    <#
    .SYNOPSIS
        Devolve o padrao canonico de alvos sensiveis.
    #>
    [CmdletBinding()]
    param()

    return $script:SensitiveTargetPattern
}

function Test-SensitiveTarget {
    <#
    .SYNOPSIS
        Indica se o texto informado referencia um alvo sensivel.

    .DESCRIPTION
        Serve tanto para caminho de arquivo (guard de Edit|Write) quanto para
        trecho de linha de comando (guard de Bash|PowerShell): em ambos os casos
        a pergunta e a mesma — o nome protegido aparece aqui?
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [AllowNull()]
        [AllowEmptyString()]
        [string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) { return $false }

    return ($Value -match $script:SensitiveTargetPattern)
}

function Get-SensitiveTargetDescription {
    <#
    .SYNOPSIS
        Devolve a lista legivel dos alvos protegidos, para mensagens de bloqueio.
    #>
    [CmdletBinding()]
    param()

    return $script:SensitiveTargetDescription
}

function Get-SensitiveWriteInCommand {
    <#
    .SYNOPSIS
        Se a linha de comando ESCREVE ou REMOVE um alvo sensivel, devolve o
        segmento ofensor (para a mensagem de bloqueio). Senao, devolve $null.

    .DESCRIPTION
        Logica unica dos dois guards de terminal (Antigravity e Claude Code).
        Antes cada um reimplementava esta rotina com pequenas divergencias
        (separador nao normalizado de um lado, `[regex]::Replace` sensivel a
        caixa do outro, padrao de verbo/redirecionamento copiado). Aqui e' uma.

        1. Normaliza `/` -> `\` para que `Orchestrator/automacoes.db` e a forma
           com barra invertida sejam avaliados igual.
        2. Divide em segmentos por `;` `&&` `||` `|` e quebra de linha: verbo de
           escrita e alvo sensivel precisam estar NO MESMO segmento, senao
           `Get-Content .env; Set-Content saida.txt x` seria barrado por engano.
        3. Descarta o conteudo de `-Value`/`-Body` (case-insensitive): e' dado
           escrito, nao alvo — uma mencao ao nome do arquivo la' dentro nao deve
           disparar bloqueio.
        4. Trata `>`/`>>` como fronteira entre fonte (leitura) e alvo (escrita).
           Alvo de redirecionamento sensivel bloqueia sozinho; na fonte so'
           bloqueia com verbo de escrita explicito no mesmo segmento.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [AllowNull()]
        [AllowEmptyString()]
        [string]$CommandLine
    )

    if ([string]::IsNullOrWhiteSpace($CommandLine)) { return $null }

    $normalized = $CommandLine.Replace('/', '\')
    $segments = $normalized -split '(\|\||&&|\||;|\r?\n)'

    foreach ($segment in $segments) {
        if ([string]::IsNullOrWhiteSpace($segment)) { continue }

        $inspecionado = [regex]::Replace(
            $segment,
            '-(Value|Body)\s+("[^"]*"|''[^'']*''|\S+)',
            '-$1 <omitido>',
            [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)

        $parts = $inspecionado -split $script:SensitiveRedirectPattern
        $fonte = $parts[0]
        $alvos = @($parts | Select-Object -Skip 1)

        foreach ($alvo in $alvos) {
            if ($alvo -match $script:SensitiveTargetPattern) { return $segment.Trim() }
        }

        if (($fonte -match $script:SensitiveTargetPattern) -and
            ($fonte -match $script:SensitiveWriteVerbPattern)) {
            return $segment.Trim()
        }
    }

    return $null
}

function Get-HookPayload {
    <#
    .SYNOPSIS
        Le e desserializa o payload do hook (variavel de ambiente ou stdin).
    #>
    [CmdletBinding()]
    param()

    $raw = $null
    if (-not [string]::IsNullOrWhiteSpace($env:CLAUDE_TOOL_INPUT)) {
        $raw = $env:CLAUDE_TOOL_INPUT
    }
    elseif ([Console]::IsInputRedirected) {
        $raw = [Console]::In.ReadToEnd()
    }

    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $null
    }

    try {
        return $raw | ConvertFrom-Json
    }
    catch [System.Exception] {
        return $null
    }
}

function Get-HookProperty {
    <#
    .SYNOPSIS
        Le uma propriedade do payload, aceitando tanto o formato achatado
        (CLAUDE_TOOL_INPUT contem o proprio tool_input) quanto o aninhado.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        $Payload,

        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if ($null -eq $Payload) { return $null }

    $names = $Payload.PSObject.Properties.Name

    if ($names -contains $Name) {
        return $Payload.$Name
    }

    if ($names -contains 'tool_input') {
        $inner = $Payload.tool_input
        if ($null -ne $inner -and ($inner.PSObject.Properties.Name -contains $Name)) {
            return $inner.$Name
        }
    }

    return $null
}

function Get-RepositoryRoot {
    [CmdletBinding()]
    param()

    if (-not [string]::IsNullOrWhiteSpace($env:CLAUDE_PROJECT_DIR)) {
        return (Resolve-Path -LiteralPath $env:CLAUDE_PROJECT_DIR).Path
    }

    return (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
}

function Get-PowerShellHostPath {
    [CmdletBinding()]
    param()

    $pwsh = Get-Command -Name 'pwsh' -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($pwsh) { return $pwsh.Source }

    $windowsPowerShell = Get-Command -Name 'powershell' -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($windowsPowerShell) { return $windowsPowerShell.Source }

    return $null
}

function Invoke-EncodingCheck {
    <#
    .SYNOPSIS
        Roda Tools/Test-SourceEncoding.ps1 sobre os caminhos informados.

    .OUTPUTS
        PSCustomObject com ExitCode (int) e Output (string). ExitCode -1 indica
        que a verificacao nao pode ser executada e deve ser tratada como
        inconclusiva (nao bloqueante).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot,

        [Parameter(Mandatory = $true)]
        [string[]]$RelativePaths
    )

    $inconclusive = [pscustomobject]@{ ExitCode = -1; Output = '' }

    $checker = Join-Path $RepositoryRoot 'Tools\Test-SourceEncoding.ps1'
    if (-not (Test-Path -LiteralPath $checker -PathType Leaf)) {
        return $inconclusive
    }

    return Invoke-GovernedScript `
        -ScriptPath $checker `
        -RootParameterName 'RootPath' `
        -RepositoryRoot $RepositoryRoot `
        -RelativePaths $RelativePaths
}

function Invoke-GovernanceGate {
    <#
    .SYNOPSIS
        Roda Tools/ValidarAutomacoes.ps1 -OnlyGovernance em modo direcionado.

    .DESCRIPTION
        Sem -Paths o script cai em full_scan (340 s, medido em 01/09/2026),
        inviavel em hook. Com -Paths ele roda os 15 checks apenas sobre os alvos
        informados: ~7 s sem Python e ~18 s com dois .py (o mypy domina o custo).

        -NoCriticalPromotion e obrigatorio aqui. Passar -Paths NAO bastava: se
        um unico alvo batesse em caminho critico (lib\, Tools\, AGENTS.md,
        workflows, skills), Get-GovernanceTargetSummary zerava GovernancePaths e
        o gate caia em full_scan assim mesmo — 340 s contra o timeout de 240 s
        do hook Stop, que por isso estourava em 100% das execucoes entre
        27/08/2026 e 01/09/2026. O modo direcionado nao afrouxa nada: o
        pre-commit e o CI continuam promovendo a full_scan.

    .OUTPUTS
        Mesmo contrato de Invoke-EncodingCheck: ExitCode (-1 = inconclusivo,
        nao bloqueante) e Output.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot,

        [Parameter(Mandatory = $true)]
        [string[]]$RelativePaths
    )

    $gate = Join-Path $RepositoryRoot 'Tools\ValidarAutomacoes.ps1'
    if (-not (Test-Path -LiteralPath $gate -PathType Leaf)) {
        return [pscustomobject]@{ ExitCode = -1; Output = '' }
    }

    return Invoke-GovernedScript `
        -ScriptPath $gate `
        -RootParameterName 'BasePath' `
        -RepositoryRoot $RepositoryRoot `
        -RelativePaths $RelativePaths `
        -ExtraArguments '-OnlyGovernance -NoCriticalPromotion'
}

function Select-FailureLines {
    <#
    .SYNOPSIS
        Reduz a saida de um gate as linhas que descrevem falha.

    .DESCRIPTION
        O gate emite 60+ linhas de [OK] mesmo quando reprova. Devolver tudo ao
        agente gasta contexto sem informar. Esta funcao mantem cada linha de
        erro e as linhas de detalhe indentadas que a seguem.

        Se nenhum marcador de falha for reconhecido, devolve a saida integral —
        e melhor pecar por excesso do que esconder o motivo da reprovacao.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Output,

        [int]$ContextLines = 3
    )

    if ([string]::IsNullOrWhiteSpace($Output)) {
        return ''
    }

    $lines = $Output -split "`r?`n"
    $keep = New-Object 'System.Collections.Generic.HashSet[int]'

    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -notmatch '\[(ERRO|FALHA|AVISO)') { continue }

        [void]$keep.Add($i)

        # Detalhe do achado vem indentado logo abaixo da linha de erro.
        for ($j = $i + 1; $j -lt [Math]::Min($i + 1 + $ContextLines, $lines.Count); $j++) {
            if ($lines[$j] -match '^\s+\S' -or $lines[$j] -match '\[(ERRO|FALHA)') {
                [void]$keep.Add($j)
            }
            else {
                break
            }
        }
    }

    if ($keep.Count -eq 0) {
        return $Output
    }

    $selected = @($keep) | Sort-Object | ForEach-Object { $lines[$_] }
    return ($selected -join [Environment]::NewLine)
}

function Invoke-GovernedScript {
    <#
    .SYNOPSIS
        Executa um script de Tools/ como processo filho e captura tudo.

    .DESCRIPTION
        Write-Host e Out-Host escrevem no host, nao no pipeline: redirecionar
        com 2>&1 dentro do mesmo processo perde o detalhe dos achados. Como
        processo filho, tudo converge para o stdout e pode ser lido.

        Os caminhos trafegam por arquivo, nunca interpolados na linha de
        comando: nome com aspas ou espaco nao vira injecao de argumento.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,

        [Parameter(Mandatory = $true)]
        [string]$RootParameterName,

        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot,

        [Parameter(Mandatory = $true)]
        [string[]]$RelativePaths,

        [string]$ExtraArguments = ''
    )

    $inconclusive = [pscustomobject]@{ ExitCode = -1; Output = '' }

    $hostPath = Get-PowerShellHostPath
    if (-not $hostPath) {
        return $inconclusive
    }

    $listFile = Join-Path ([System.IO.Path]::GetTempPath()) ("hook-paths-{0}.txt" -f ([guid]::NewGuid().ToString('N')))
    try {
        Set-Content -LiteralPath $listFile -Value $RelativePaths -Encoding utf8

        $escape = { param([string]$Value) $Value.Replace("'", "''") }
        $script = "& '{0}' -{1} '{2}' {3} -Paths @(Get-Content -LiteralPath '{4}')" -f `
        (& $escape $ScriptPath), $RootParameterName, (& $escape $RepositoryRoot), `
            $ExtraArguments, (& $escape $listFile)

        $output = & $hostPath -NoProfile -NonInteractive -Command $script 2>&1
        $exitCode = $LASTEXITCODE

        return [pscustomobject]@{
            ExitCode = $exitCode
            Output   = (($output | Out-String).Trim())
        }
    }
    catch [System.Exception] {
        return $inconclusive
    }
    finally {
        Remove-Item -LiteralPath $listFile -Force -ErrorAction SilentlyContinue
    }
}

Export-ModuleMember -Function Get-SensitiveTargetPattern, Test-SensitiveTarget, Get-SensitiveTargetDescription, Get-SensitiveWriteInCommand, Get-HookPayload, Get-HookProperty, Get-RepositoryRoot, Invoke-EncodingCheck, Invoke-GovernanceGate, Select-FailureLines
