# ==============================================================================
# ARQUIVO: Test-NodeCommunications.ps1
# VERSAO: 1.2.0
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

# Cada entrada e' um diretorio com package.json + "npm test" proprio. Contrato offline
# de Receitas Bloqueadas (regex sobre o codigo-fonte) e suite real de unidade + cobertura
# de lib/WhatsApp-Core.js (node:test, gate de 90% linhas/branches/funcs) rodam aqui.
$candidatos = @(
    (Join-Path $base "Receitas Bloqueadas\package.json"),
    (Join-Path $base "lib\package.json")
)

# @(...) e obrigatorio: Where-Object devolve $null com 0 correspondencias e um escalar
# (nao array) com exatamente 1 — sob Set-StrictMode -Version Latest, .Count em qualquer
# um dos dois lanca PropertyNotFoundException em vez de cair no fallback "[OK] nenhum
# package.json encontrado" abaixo, derrubando o gate com $ErrorActionPreference = "Stop".
$packagePaths = @($candidatos | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })

if ($packagePaths.Count -eq 0) {
    Write-Host "[OK] Nenhum package.json de comunicacao Node.js encontrado." -ForegroundColor Green
    exit 0
}

$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npm) {
    Write-Host "[ERRO] npm nao encontrado para executar testes Node.js offline." -ForegroundColor Red
    exit 1
}

$falhou = $false
foreach ($packagePath in $packagePaths) {
    $workdir = Split-Path -Parent $packagePath

    # So' exige node_modules quando o proprio package.json declara dependencias reais
    # (ex.: lib/ precisa de 'whatsapp-web.js' — require() de topo, mesmo que os testes
    # troquem a implementacao via seam de DI depois). "Receitas Bloqueadas" nao declara
    # nenhuma dependencia (o teste usa so' assert/fs/path nativos) e sempre rodou sem
    # instalacao previa — exigir node_modules ali seria um [SKIP] falso-positivo que
    # reduziria a cobertura do gate sem necessidade real. node_modules e' gitignored,
    # entao um clone novo sem 'npm ci' em diretorio QUE PRECISA dele nao deve bloquear o
    # commit local por falta de rede/setup. O CI (job "governanca-agregada") sempre
    # instala via 'npm ci' antes deste gate, entao a cobertura real da suite continua
    # garantida no pipeline bloqueante independente do estado da maquina local.
    $pkg = Get-Content -LiteralPath $packagePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $props = $pkg.PSObject.Properties.Name
    $precisaNodeModules = (
        ($props -contains 'dependencies' -and @($pkg.dependencies.PSObject.Properties).Count -gt 0) -or
        ($props -contains 'devDependencies' -and @($pkg.devDependencies.PSObject.Properties).Count -gt 0)
    )
    if ($precisaNodeModules) {
        $nodeModules = Join-Path $workdir "node_modules"
        if (-not (Test-Path -LiteralPath $nodeModules -PathType Container)) {
            Write-Host "[SKIP] ${workdir}: declara dependencias mas node_modules ausente — rode 'npm ci --prefix `"$workdir`"' para incluir esta suite no gate local." -ForegroundColor DarkYellow
            continue
        }
    }

    Write-Host "--- npm test em $workdir ---" -ForegroundColor Cyan
    Push-Location $workdir
    try {
        & npm test | Out-Host
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }

    if ($exitCode -ne 0) {
        Write-Host "[FALHA] Testes Node.js offline reprovaram em $workdir." -ForegroundColor Red
        $falhou = $true
    }
}

if ($falhou) {
    exit 1
}

Write-Host "[OK] Testes Node.js offline aprovados." -ForegroundColor Green
exit 0
