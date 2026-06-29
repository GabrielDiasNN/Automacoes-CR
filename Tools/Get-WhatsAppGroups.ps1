# ==============================================================================
# ARQUIVO: Get-WhatsAppGroups.ps1
# DESCRICAO: Usa sessao WhatsApp ja autenticada para listar grupos e seus IDs.
#            Executar uma vez para descobrir o ID do grupo destino.
# USO:
#   pwsh -File Tools\Get-WhatsAppGroups.ps1
#   pwsh -File Tools\Get-WhatsAppGroups.ps1 -ClientId "hub-global"
# ==============================================================================
[CmdletBinding()]
param(
    [string]$ClientId = "hub-global"
)

$ErrorActionPreference = "Stop"
$LibDir = Join-Path $PSScriptRoot "..\lib"
$CoreJs = Join-Path $LibDir "WhatsApp-Core.js"

if (-not (Test-Path $CoreJs)) {
    Write-Error "WhatsApp-Core.js nao encontrado em: $CoreJs"
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

# NODE_PATH aponta para node_modules compartilhados
$env:NODE_PATH = Join-Path $PSScriptRoot "..\Receitas Bloqueadas\node_modules"

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  Listando grupos WhatsApp (sessao: $ClientId)" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Aguarde — inicializando cliente Puppeteer..." -ForegroundColor Gray
Write-Host ""

& $NodeExe $CoreJs "list-grupos" "LIST_GROUPS" $ClientId

$exitCode = $LASTEXITCODE
if ($exitCode -eq 21) {
    Write-Host ""
    Write-Host "[AVISO] Sessao expirada. Execute primeiro uma automacao que usa WhatsApp para reautenticar." -ForegroundColor Yellow
} elseif ($exitCode -ne 0) {
    Write-Host ""
    Write-Host "[ERRO] Falha ao listar grupos. ExitCode: $exitCode" -ForegroundColor Red
}
