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

# Verificar se ha execucao de automacao em andamento que usa hub-global
$EnvFile = Join-Path $LibDir "..\\.env"
if (Test-Path $EnvFile) {
    try {
        $apiKey = ""
        Get-Content $EnvFile | Where-Object { $_ -match '=' -and $_ -notmatch '^#' } | ForEach-Object {
            $parts = $_.Split('=', 2)
            if ($parts[0].Trim() -eq "ORCHESTRATOR_API_KEY") { $apiKey = $parts[1].Trim() }
        }
        if ($apiKey) {
            $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/executions?status=RUNNING" `
                -Headers @{ "X-API-Key" = $apiKey } -ErrorAction SilentlyContinue
            $runningWhatsApp = $resp | Where-Object { $_.automation_name -match "OBs Paradas|Receitas Bloqueadas|Receitas Emitidas|Montagem" }
            if ($runningWhatsApp) {
                Write-Host ""
                Write-Host "[ATENCAO] Ha uma automacao WhatsApp em execucao agora:" -ForegroundColor Yellow
                foreach ($ex in $runningWhatsApp) {
                    Write-Host "  -> $($ex.automation_name) (iniciada $($ex.started_at))" -ForegroundColor Yellow
                }
                Write-Host ""
                Write-Host "  Abrir esta sessao vai desconectar a automacao em andamento." -ForegroundColor Yellow
                Write-Host "  Pressione Ctrl+C para cancelar ou aguarde e tente novamente." -ForegroundColor Yellow
                Write-Host ""
                $confirm = Read-Host "  Continuar mesmo assim? (s/N)"
                if ($confirm -ne "s" -and $confirm -ne "S") {
                    Write-Host "Operacao cancelada." -ForegroundColor Gray
                    exit 0
                }
            }
        }
    } catch [System.Exception] {
        # Orchestrator indisponivel — continua sem verificacao
    }
}

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
