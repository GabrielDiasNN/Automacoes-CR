# ==============================================================================
# ARQUIVO: Test-NodeCommunications.ps1
# VERSAO: 1.0.0
# DESCRICAO: Executa testes offline de comunicacoes Node.js sem depender de
#            sessao WhatsApp, Puppeteer, internet ou credenciais.
# ==============================================================================
[CmdletBinding()]
param(
    [string]$RootPath = ".",
    [string[]]$Paths = @()
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Write-Host "=== GOVERNANCA NODE.JS COMUNICACOES ===" -ForegroundColor Cyan

$base = (Resolve-Path -LiteralPath $RootPath).Path
$packagePath = Join-Path $base "Receitas Bloqueadas\package.json"

if (-not (Test-Path -LiteralPath $packagePath -PathType Leaf)) {
    Write-Host "[OK] Nenhum package.json de comunicacao Node.js encontrado." -ForegroundColor Green
    exit 0
}

$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npm) {
    Write-Host "[ERRO] npm nao encontrado para executar testes Node.js offline." -ForegroundColor Red
    exit 1
}

$workdir = Split-Path -Parent $packagePath
Push-Location $workdir
try {
    & npm test | Out-Host
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

if ($exitCode -ne 0) {
    Write-Host "[FALHA] Testes Node.js offline reprovaram." -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Testes Node.js offline aprovados." -ForegroundColor Green
exit 0
