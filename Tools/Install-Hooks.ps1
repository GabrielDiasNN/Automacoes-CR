<#
.SYNOPSIS
    Configura o repositorio para usar os git hooks versionados em .githooks/.

.DESCRIPTION
    Aponta core.hooksPath para .githooks (relativo a raiz do repositorio), garantindo
    que o hook de pre-commit (governanca) seja executado em vez do hook padrao do
    .git/hooks. Idempotente: pode ser executado quantas vezes for necessario.

.EXAMPLE
    pwsh -File Tools\Install-Hooks.ps1
    Configura core.hooksPath=.githooks na raiz do repositorio.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

# -- Definir raiz do repositorio --
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path $RepoRoot)) {
    $RepoRoot = "."
}

try {
    Write-Host "Configurando core.hooksPath em $RepoRoot..." -ForegroundColor Cyan

    & git -C $RepoRoot config core.hooksPath ".githooks"
    if ($LASTEXITCODE -ne 0) {
        throw "git config core.hooksPath retornou codigo de saida $LASTEXITCODE."
    }

    $ConfiguredPath = (& git -C $RepoRoot config --get core.hooksPath).Trim()
    if ($LASTEXITCODE -ne 0 -or $ConfiguredPath -ne ".githooks") {
        throw "Falha ao confirmar core.hooksPath (valor lido: '$ConfiguredPath')."
    }

    Write-Host "Hooks configurados com sucesso: core.hooksPath=$ConfiguredPath" -ForegroundColor Green
}
catch [System.Exception] {
    Write-Host "Erro ao configurar git hooks: $_" -ForegroundColor Red
    exit 1
}
