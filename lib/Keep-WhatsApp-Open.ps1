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

# Write-Error sob $ErrorActionPreference='Stop' e terminante: o 'exit 1' seguinte nunca
# executaria. Write-Host + exit deixa o codigo de saida explicito e alcancavel.
if (-not (Test-Path $SessionScript)) {
    Write-Host "[ERRO] open-whatsapp-session.js nao encontrado em: $SessionScript" -ForegroundColor Red
    exit 1
}

$NodeExe = "node"
if (-not (Get-Command $NodeExe -ErrorAction SilentlyContinue)) {
    $progFiles = [Environment]::GetFolderPath("ProgramFiles")
    $NodeExe = Join-Path $progFiles "nodejs\node.exe"
    if (-not (Test-Path $NodeExe)) {
        Write-Host "[ERRO] Node.js nao encontrado." -ForegroundColor Red
        exit 1
    }
}

$env:NODE_PATH = Join-Path $LibDir "node_modules"

# Deriva do repositorio quais automacoes usam ESTE clientId, em vez de uma lista fixa que
# apodrece em silencio quando uma quarta automacao passar a usar o mesmo canal.
function Get-AutomacoesDoCanal {
    param([string]$ClientId, [string]$RepoRoot)
    $nomes = @()
    $padrao = '"clientId"\s*:\s*"' + [regex]::Escape($ClientId) + '"'
    foreach ($dir in (Get-ChildItem -Path $RepoRoot -Directory -ErrorAction SilentlyContinue)) {
        $cfg = Join-Path $dir.FullName "whatsapp-config.json"
        $manifesto = Join-Path $dir.FullName "automation.manifest.json"
        if (-not ((Test-Path $cfg) -and (Test-Path $manifesto))) { continue }
        if ((Get-Content $cfg -Raw) -notmatch $padrao) { continue }
        $nome = (Get-Content $manifesto -Raw | ConvertFrom-Json).name
        if ($nome) { $nomes += $nome }
    }
    return $nomes
}

# Verificar se ha execucao de automacao em andamento que usa este clientId
$RepoRoot = Split-Path -Parent $LibDir
$EnvFile = Join-Path $RepoRoot ".env"
if (-not (Test-Path $EnvFile)) {
    Write-Host "[AVISO] .env nao encontrado — NAO foi possivel verificar automacoes em execucao." -ForegroundColor Yellow
} else {
    try {
        $apiKey = ""
        Get-Content $EnvFile | Where-Object { $_ -match '=' -and $_ -notmatch '^#' } | ForEach-Object {
            $parts = $_.Split('=', 2)
            if ($parts[0].Trim() -eq "ORCHESTRATOR_API_KEY") { $apiKey = $parts[1].Trim() }
        }
        if (-not $apiKey) {
            Write-Host "[AVISO] ORCHESTRATOR_API_KEY ausente no .env — NAO foi possivel verificar automacoes em execucao." -ForegroundColor Yellow
        } else {
            $automacoesDoCanal = @(Get-AutomacoesDoCanal -ClientId $ClientId -RepoRoot $RepoRoot)
            if ($automacoesDoCanal.Count -eq 0) {
                Write-Host "[AVISO] Nenhuma automacao encontrada usando o clientId '$ClientId' — verificacao sem alvo." -ForegroundColor Yellow
            }
            $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/executions?status=RUNNING" `
                -Headers @{ "X-API-Key" = $apiKey }
            # GET /api/executions responde PaginatedResponse ({items,total,page,...}), nao uma
            # lista crua: filtrar $resp direto nunca casava nada e a trava ficava inoperante.
            $execucoes = if ($null -ne $resp.items) { $resp.items } else { $resp }
            $runningWhatsApp = @($execucoes | Where-Object {
                $automacoesDoCanal -contains $_.automation_name
            })
            if ($runningWhatsApp.Count -gt 0) {
                Write-Host ""
                Write-Host "[ATENCAO] Ha uma automacao WhatsApp em execucao agora:" -ForegroundColor Yellow
                foreach ($ex in $runningWhatsApp) {
                    Write-Host "  -> $($ex.automation_name) (iniciada $($ex.started_at))" -ForegroundColor Yellow
                }
                Write-Host ""
                Write-Host "  Abrir esta sessao vai desconectar a automacao em andamento." -ForegroundColor Yellow
                Write-Host "  Pressione Ctrl+C para cancelar ou aguarde e tente novamente." -ForegroundColor Yellow
                Write-Host ""
                # Sem console interativo (duplo clique, tarefa agendada) Read-Host falha e
                # derrubaria o script com $ErrorActionPreference='Stop'. Cancelar e o lado
                # seguro: nao roubar a sessao de uma automacao em envio.
                $confirm = "n"
                try {
                    $confirm = Read-Host "  Continuar mesmo assim? (s/N)"
                } catch [System.Exception] {
                    Write-Host "  Console nao interativo — cancelando por seguranca." -ForegroundColor Gray
                }
                if ($confirm -ne "s" -and $confirm -ne "S") {
                    Write-Host "Operacao cancelada." -ForegroundColor Gray
                    exit 0
                }
            }
        }
    } catch [System.Exception] {
        # Uma guarda silenciosa e indistinguivel de uma guarda que passou: Orchestrator fora
        # do ar, API Key errada e timeout de rede produziriam o mesmo "nenhuma automacao
        # rodando". O operador precisa saber que a verificacao NAO foi feita.
        Write-Host "[AVISO] NAO foi possivel verificar automacoes em execucao: $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host "        Confirme manualmente que nenhuma automacao WhatsApp esta enviando agora." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  Sessao WhatsApp em modo visivel (ClientId: $ClientId)" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  O Chrome sera aberto com a sessao. Se nao houver sessao valida," -ForegroundColor Gray
Write-Host "  o proprio WhatsApp Web exibe o QR Code para autenticar." -ForegroundColor Gray
Write-Host "  Apos conectar, AGUARDE a mensagem 'Sessao gravada em disco'." -ForegroundColor Gray
Write-Host "  Para encerrar: pressione Ctrl+C nesta janela (nao feche o Chrome direto)." -ForegroundColor Gray
Write-Host ""

# Falha de executavel nativo nao lanca excecao: sem capturar $LASTEXITCODE o script sempre
# saia 0, mesmo quando o Node abortava no bootstrap. O finally garante a orientacao ao
# operador mesmo se a chamada abortar; o Ctrl+C esperado nao e falha e nao imprime nada.
$nodeExit = 0
try {
    & $NodeExe $SessionScript $ClientId
    $nodeExit = $LASTEXITCODE
} catch [System.Exception] {
    Write-Host "[ERRO] Falha ao iniciar sessao: $_" -ForegroundColor Red
    $nodeExit = 1
} finally {
    if ($nodeExit -ne 0) {
        Write-Host ""
        Write-Host "  Sessao encerrada com falha (ExitCode: $nodeExit)." -ForegroundColor Yellow
        Write-Host "  Se o perfil estiver inconsistente, use: lib\Authenticate-WhatsApp.bat" -ForegroundColor Yellow
        Write-Host "  (ele arquiva o perfil quebrado e reinicia do zero)." -ForegroundColor Yellow
        Write-Host ""
    }
}
exit $nodeExit
