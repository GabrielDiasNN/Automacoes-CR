# ==============================================================================
# ARQUIVO: Keep-WhatsApp-Open.ps1
# DESCRICAO: Abre o Chrome com a sessao WhatsApp em modo visivel e mantem aberto.
#            Use para enviar mensagens pendentes manualmente ou inspecionar a sessao.
# USO:
#   pwsh -File lib\Keep-WhatsApp-Open.ps1
#   pwsh -File lib\Keep-WhatsApp-Open.ps1 -ClientId "hub-global"
# ==============================================================================
[CmdletBinding()]
param(
    [string]$ClientId = "hub-global"
)

$ErrorActionPreference = "Stop"
$LibDir = $PSScriptRoot
$SessionScript = Join-Path $LibDir "open-whatsapp-session.js"

if (-not (Test-Path $SessionScript)) {
    Write-Error "open-whatsapp-session.js nao encontrado em: $SessionScript"
    exit 1
}

$NodeExe = "node"
if (-not (Get-Command $NodeExe -ErrorAction SilentlyContinue)) {
    $progFiles = [Environment]::GetFolderPath("ProgramFiles")
    $NodeExe = Join-Path $progFiles "nodejs\node.exe"
    if (-not (Test-Path $NodeExe)) {
        Write-Error "Node.js nao encontrado."
        exit 1
    }
}

$env:NODE_PATH = Join-Path $LibDir "..\Receitas Bloqueadas\node_modules"

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  Sessao WhatsApp em modo visivel (ClientId: $ClientId)" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  O Chrome sera aberto com a sessao ja autenticada." -ForegroundColor Gray
Write-Host "  Envie as mensagens pendentes manualmente no navegador." -ForegroundColor Gray
Write-Host "  Para encerrar: pressione Ctrl+C nesta janela." -ForegroundColor Gray
Write-Host ""

try {
    & $NodeExe $SessionScript $ClientId
} catch [System.Exception] {
    Write-Host "[ERRO] Falha ao iniciar sessao: $_" -ForegroundColor Red
    exit 1
}
