#Requires -Version 5.1
<#
.SYNOPSIS
    Hook PreToolUse (Bash|PowerShell): barra ESCRITA em arquivos sensiveis.

.DESCRIPTION
    O guard de Edit|Write que vive no settings.json cobre apenas as ferramentas
    de edicao. Um `Set-Content .env` ou `echo ... > .env` disparado pelo shell
    passava por fora dele. Este hook fecha essa lacuna.

    Bloqueia ESCRITA, nao LEITURA. Ler .env e operacao legitima e documentada
    (CLAUDE.md manda ler ORCHESTRATOR_API_KEY de la para validacao visual do
    dashboard); bloquear leitura quebraria o fluxo sem ganho de seguranca, ja
    que o agente pode ler o valor por outros caminhos.

    A deteccao exige verbo de escrita E alvo sensivel NO MESMO segmento do
    comando. Sem essa restricao de segmento, `Get-Content .env | Set-Content
    saida.txt` seria barrado por engano. Os segmentos sao separados por ; && ||
    | e quebra de linha.

    Dentro do segmento, `>` e `>>` sao tratados como FRONTEIRA entre fonte e
    alvo: o que esta a esquerda e leitura, o que esta a direita e o arquivo
    escrito. Sem isso `Get-Content .env > backup.txt` era barrado como se
    escrevesse em .env. Um alvo sensivel a direita bloqueia sozinho, sem exigir
    verbo (`echo x > .env`).

    Alvos protegidos vem de Test-SensitiveTarget (HookCommon.psm1), a mesma
    fonte consumida pelo guard inline de Edit|Write no settings.json.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'HookCommon.psm1') -Force -DisableNameChecking

# Verbos de escrita: cmdlets e utilitarios POSIX. O redirecionamento NAO entra
# aqui — ele e fronteira de segmento, tratado separadamente abaixo.
$writePattern = '(Set-Content|Add-Content|Out-File|Tee-Object|Clear-Content|Remove-Item|Move-Item|Copy-Item|New-Item|Rename-Item|\brm\b|\bmv\b|\bcp\b|\btee\b|\btruncate\b|\bshred\b|sed\s+-i)'

# Redirecionamento: > ou >> nao precedido de digito (exclui 2>&1) e nao seguido
# de & ou $ (exclui 2>&1 e >$null).
$redirectPattern = '(?<![0-9])>>?(?!\s*[&$])'

$payload = Get-HookPayload
if ($null -eq $payload) {
    exit 0
}

$command = Get-HookProperty -Payload $payload -Name 'command'
if ([string]::IsNullOrWhiteSpace($command)) {
    exit 0
}

# A alternativa mais longa vem primeiro: com '\|' antes, '\|\|' nunca seria
# alcancada. O resultado nao muda (|| acabava dividido em dois separadores),
# mas o regex passa a corresponder a intencao declarada acima.
$segments = $command -split '(\|\||&&|\||;|\r?\n)'

foreach ($segment in $segments) {
    if ([string]::IsNullOrWhiteSpace($segment)) { continue }

    # O conteudo de -Value e dado, nao alvo: `Set-Content nota.md -Value "cita
    # orchestrator.pid"` escreve em nota.md. Sem descartar esse trecho, uma
    # simples mencao ao nome no texto viraria bloqueio. Descartar apenas -Value
    # e seguro porque o alvo do cmdlet fica sempre fora dele.
    $inspecionado = [regex]::Replace($segment, '-(Value|Body)\s+("[^"]*"|''[^'']*''|\S+)', '-$1 <omitido>')

    # parts[0] e a fonte (leitura); tudo depois de > ou >> e alvo de escrita.
    $parts = $inspecionado -split $redirectPattern
    $fonte = $parts[0]
    $alvos = @($parts | Select-Object -Skip 1)

    $bloqueia = $false

    # Alvo de redirecionamento sensivel bloqueia sozinho: o proprio > e o verbo.
    foreach ($alvo in $alvos) {
        if (Test-SensitiveTarget -Value $alvo) { $bloqueia = $true }
    }

    # Na fonte, so bloqueia com verbo de escrita explicito — senao qualquer
    # leitura (`Get-Content .env`, `grep CHAVE .env`) viraria bloqueio.
    if (-not $bloqueia -and (Test-SensitiveTarget -Value $fonte) -and $fonte -match $writePattern) {
        $bloqueia = $true
    }

    if ($bloqueia) {
        $lines = @(
            'BLOQUEADO: escrita em arquivo sensivel via shell.',
            '',
            "  Segmento: $($segment.Trim())",
            '',
            '',
            'Arquivos protegidos: .env, automacoes.db, orchestrator.db,',
            'orchestrator.pid, worker.pid.',
            '',
            'Leitura continua liberada, inclusive com redirecionamento',
            '(ex.: Get-Content .env, grep CHAVE .env > saida.txt).',
            'Se a alteracao for mesmo necessaria, peca ao usuario que a faca.'
        )
        [Console]::Error.WriteLine(($lines -join [Environment]::NewLine))
        exit 2
    }
}

exit 0
