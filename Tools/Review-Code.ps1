# cSpell:words RESUMO
# {
#   "version": "1.0.0",
#   "skill": "powershell-automation-monitor",
#   "description": "Utilitario de Revisao Estatica Local e Relatorio de Governanca - Agente de Revisao"
# }
[CmdletBinding()]
param(
    [string]$BasePath
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($BasePath)) {
    $BasePath = if ($PSScriptRoot) { $PSScriptRoot } else { Get-Location }
    if ($BasePath -match '\\Tools$') {
        $BasePath = Split-Path -Parent $BasePath
    }
}

$resolvedRoot = (Resolve-Path -LiteralPath $BasePath).Path
$validarAutoPath = Join-Path $resolvedRoot "Tools\ValidarAutomacoes.ps1"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "      🔍 AGENTE DE REVISAO DE CODIGO: AUDITORIA E GOVERNANCA LOCAL     " -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "Iniciando checagem estatica de governanca nos arquivos staged..." -ForegroundColor Gray

if (-not (Test-Path -LiteralPath $validarAutoPath)) {
    Write-Host "[ERRO] Orquestrador de validacao nao encontrado em $validarAutoPath" -ForegroundColor Red
    exit 1
}

# Inicializa variavel de captura de saida
$tempLog = [System.IO.Path]::GetTempFileName()

try {
    # Chama o orquestrador capturando a saida e o status
    $psArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $validarAutoPath, "-BasePath", $resolvedRoot, "-OnlyGovernance", "-StagedOnly")
    
    # Executa e grava saida no arquivo temporario
    & powershell @psArgs > $tempLog
    $exitCode = $LASTEXITCODE
    $rawOutput = Get-Content -Path $tempLog -Raw
}
finally {
    if (Test-Path $tempLog) { Remove-Item $tempLog -ErrorAction SilentlyContinue }
}

# Emite o relatorio Markdown de acordo com o resultado
Write-Host "`n=== RELATORIO DE REVISAO DE CODIGO ===" -ForegroundColor Cyan

if ($exitCode -eq 0) {
    Write-Host "`n[OK] STATUS: HEALTHY (APROVADO) ✨" -ForegroundColor Green
    Write-Host "------------------------------------------------------------" -ForegroundColor Gray
    Write-Host "Todas as mudancas na staged area estao em perfeita conformidade." -ForegroundColor Green
    Write-Host "Os mandatos de encoding, datas brasileiras (DD/MM/YYYY) e Zero Trust" -ForegroundColor Green
    Write-Host "foram validados com sucesso." -ForegroundColor Green
    Write-Host "------------------------------------------------------------" -ForegroundColor Gray
    Write-Host "Pronto para fazer o commit com seguranca!`n" -ForegroundColor Gray
    exit 0
} else {
    Write-Host "`n[ERRO] STATUS: ATENCAO / INCIDENTE (MUDANCAS REPROVADAS) 🚨" -ForegroundColor Red
    Write-Host "------------------------------------------------------------" -ForegroundColor Gray
    Write-Host "Foram detectadas inconformidades com as regras de governanca técnica" -ForegroundColor Red
    Write-Host "do repositório. O commit foi bloqueado preventivamente." -ForegroundColor Red
    Write-Host "------------------------------------------------------------" -ForegroundColor Gray
    Write-Host "`nDetalhes das Falhas Encontradas:" -ForegroundColor Yellow
    
    # Exibe a saida capturada filtrando as linhas de falha para dar visibilidade limpa
    $lines = $rawOutput -split "`r?`n"
    $showDetails = $false
    foreach ($line in $lines) {
        if ($line -match "=== GOVERNANCA" -or $line -match "\[FALHA\]" -or $line -match "--- Rodando" -or $line -match "Erros:") {
            $showDetails = $true
        }
        
        if ($showDetails -and -not [string]::IsNullOrWhiteSpace($line)) {
            if ($line -match "\[FALHA\]" -or $line -match "Erro") {
                Write-Host "  $line" -ForegroundColor Red
            } elseif ($line -match "\[OK\]" -or $line -match "conformidade") {
                Write-Host "  $line" -ForegroundColor Green
            } else {
                Write-Host "  $line" -ForegroundColor Gray
            }
        }
    }
    
    Write-Host "`nAcao Recomendada:" -ForegroundColor Cyan
    Write-Host "1. Revise as regras descritas em: [.agents/agents/code-review-agent/agent.json]" -ForegroundColor Gray
    Write-Host "2. Corrija os arquivos apontados acima (encodings, formatos de datas ou catalogacao)." -ForegroundColor Gray
    Write-Host "3. Rode este validador novamente antes de tentar commitar.`n" -ForegroundColor Gray
    exit 1
}
