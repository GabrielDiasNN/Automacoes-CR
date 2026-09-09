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

    A deteccao (segmentacao por ; && || | e quebra de linha, `>`/`>>` como
    fronteira fonte/alvo, verbo de escrita E alvo sensivel no mesmo segmento)
    vive em Get-SensitiveWriteInCommand (HookCommon.psm1) — a MESMA rotina
    consumida pelo guard do Antigravity (.agents/hooks/PreToolUse-Guard.ps1).
    Antes cada guard reimplementava a rotina com divergencias sutis.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'HookCommon.psm1') -Force -DisableNameChecking

$payload = Get-HookPayload
if ($null -eq $payload) {
    exit 0
}

$command = Get-HookProperty -Payload $payload -Name 'command'
if ([string]::IsNullOrWhiteSpace($command)) {
    exit 0
}

$segmentoOfensor = Get-SensitiveWriteInCommand -CommandLine $command

if (-not [string]::IsNullOrEmpty($segmentoOfensor)) {
    $lines = @(
        'BLOQUEADO: escrita em arquivo sensivel via shell.',
        '',
        "  Segmento: $segmentoOfensor",
        '',
        '',
        "Arquivos protegidos: $(Get-SensitiveTargetDescription)",
        '',
        'Leitura continua liberada, inclusive com redirecionamento',
        '(ex.: Get-Content .env, grep CHAVE .env > saida.txt).',
        'Se a alteracao for mesmo necessaria, peca ao usuario que a faca.'
    )
    [Console]::Error.WriteLine(($lines -join [Environment]::NewLine))
    exit 2
}

exit 0
