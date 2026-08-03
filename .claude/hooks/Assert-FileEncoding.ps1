#Requires -Version 5.1
<#
.SYNOPSIS
    Hook PostToolUse (Edit|Write): valida o encoding do arquivo recem-escrito.

.DESCRIPTION
    Delega a verificacao para Tools/Test-SourceEncoding.ps1, fonte unica da
    regra de encoding do repositorio:
      .ps1 / .psm1                                  -> UTF-8 COM BOM
      .py .js .mjs .cjs .ts .tsx .json .md .txt
      .sql .html .css                               -> UTF-8 SEM BOM

    Sai com codigo 2 quando ha violacao, para que o stderr seja devolvido ao
    agente e a correcao aconteca no mesmo turno. Um gate de BOM nao pode viver
    no PreToolUse: naquele momento o arquivo ainda nao existe e o BOM nao esta
    no conteudo — ele e decisao de quem grava.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'HookCommon.psm1') -Force -DisableNameChecking

$payload = Get-HookPayload
if ($null -eq $payload) {
    exit 0
}

$filePath = Get-HookProperty -Payload $payload -Name 'file_path'
if ([string]::IsNullOrWhiteSpace($filePath)) {
    exit 0
}

if (-not (Test-Path -LiteralPath $filePath -PathType Leaf)) {
    exit 0
}

$repoRoot = Get-RepositoryRoot
$fullPath = (Resolve-Path -LiteralPath $filePath).Path

$rootPrefix = $repoRoot.TrimEnd([char[]]@('\', '/')) + [System.IO.Path]::DirectorySeparatorChar
if (-not $fullPath.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    # Arquivo fora do repositorio (ex.: scratchpad) nao e governado.
    exit 0
}

$relativePath = $fullPath.Substring($rootPrefix.Length)

$result = Invoke-EncodingCheck -RepositoryRoot $repoRoot -RelativePaths @($relativePath)

if ($result.ExitCode -eq 0 -or $result.ExitCode -eq -1) {
    exit 0
}

$lines = @(
    "ENCODING FORA DO PADRAO: $relativePath",
    '',
    'Regra do repositorio (CLAUDE.md):',
    '  .ps1 / .psm1 -> UTF-8 COM BOM (obrigatorio para PowerShell 5.1 com acentuacao PT-BR)',
    '  demais fontes (.py .js .ts .tsx .json .md .sql .html .css .txt) -> UTF-8 SEM BOM',
    '',
    'Saida de Tools/Test-SourceEncoding.ps1:',
    $result.Output
)

[Console]::Error.WriteLine(($lines -join [Environment]::NewLine))
exit 2
