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

    Alvos protegidos sao os mesmos do guard de Edit|Write, mantidos em sincronia
    manual: se um mudar, o outro precisa mudar junto.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'HookCommon.psm1') -Force -DisableNameChecking

# .env nao pode ser seguido de palavra, ponto ou hifen: protege .env mas libera
# .env.example. ".venv" nao casa (o ponto e seguido de 'v', nao de 'e').
$sensitivePattern = '(\.env(?![\w.\-])|automacoes\.db|orchestrator\.db|orchestrator\.pid|worker\.pid)'

# Redirecionamento: > ou >> nao precedido de digito (exclui 2>&1) e nao seguido
# de & ou $ (exclui 2>&1 e >$null). Demais verbos: cmdlets e utilitarios POSIX.
$writePattern = '((?<![0-9])>>?\s*(?![&$])|Set-Content|Add-Content|Out-File|Tee-Object|Clear-Content|Remove-Item|Move-Item|Copy-Item|New-Item|Rename-Item|\brm\b|\bmv\b|\bcp\b|\btee\b|\btruncate\b|\bshred\b|sed\s+-i)'

$payload = Get-HookPayload
if ($null -eq $payload) {
    exit 0
}

$command = Get-HookProperty -Payload $payload -Name 'command'
if ([string]::IsNullOrWhiteSpace($command)) {
    exit 0
}

$segments = $command -split '(\||&&|\|\||;|\r?\n)'

foreach ($segment in $segments) {
    if ([string]::IsNullOrWhiteSpace($segment)) { continue }

    # O conteudo de -Value e dado, nao alvo: `Set-Content nota.md -Value "cita
    # orchestrator.pid"` escreve em nota.md. Sem descartar esse trecho, uma
    # simples mencao ao nome no texto viraria bloqueio. Descartar apenas -Value
    # e seguro porque o alvo do cmdlet fica sempre fora dele.
    $inspecionado = [regex]::Replace($segment, '-(Value|Body)\s+("[^"]*"|''[^'']*''|\S+)', '-$1 <omitido>')

    if ($inspecionado -match $sensitivePattern -and $inspecionado -match $writePattern) {
        $lines = @(
            'BLOQUEADO: escrita em arquivo sensivel via shell.',
            '',
            "  Segmento: $($segment.Trim())",
            '',
            '',
            'Arquivos protegidos: .env, automacoes.db, orchestrator.db,',
            'orchestrator.pid, worker.pid.',
            '',
            'Leitura continua liberada (ex.: Get-Content .env, grep CHAVE .env).',
            'Se a alteracao for mesmo necessaria, peca ao usuario que a faca.'
        )
        [Console]::Error.WriteLine(($lines -join [Environment]::NewLine))
        exit 2
    }
}

exit 0
