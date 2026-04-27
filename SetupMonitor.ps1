<#
.SYNOPSIS
    Instalador do Monitor de Automacoes Hub.
.DESCRIPTION
    Configura o ambiente para execucao automatica:
    1. Valida pastas obrigatorias.
    2. Cria o arquivo .env inicial se nao existir.
    3. Registra o Monitor no Agendador de Tarefas do Windows (Opcional).
.NOTES
    Version: 1.0.1
    Skill: ai-native-development-standard, automacao-monitor
#>

$ErrorActionPreference = "Stop"

$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }

Write-Host "--- Iniciando Setup do Monitor ---" -ForegroundColor Cyan

# 1. Pastas obrigatorias
$folders = @("Logs", "Dashboard", "Audit", "lib")
foreach ($f in $folders) {
    $path = Join-Path $ScriptDir $f
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
        Write-Host "Criada pasta: $f"
    }
}

# 2. Arquivo .env inicial
$envPath = Join-Path $ScriptDir ".env"
if (-not (Test-Path $envPath)) {
    $template = @"
ORACLE_READONLY_USER=seu_usuario
ORACLE_READONLY_PASSWORD=sua_senha
ORACLE_CONNECT_STRING=seu_dsn
ORACLE_CLIENT_LIB_DIR=C:\instantclient_19_25
AUTOMACAO_TEST_EMAIL=seu_email@empresa.com
"@
    Set-Content -Path $envPath -Value $template -Encoding UTF8
    Write-Host "Arquivo .env criado com template. Edite as credenciais!" -ForegroundColor Yellow
}

# 3. Validacao do config.json
$configPath = Join-Path $ScriptDir "config.json"
if (-not (Test-Path $configPath)) {
    Write-Host "AVISO: config.json nao encontrado na raiz. O Monitor nao funcionara sem ele." -ForegroundColor Red
}

Write-Host "--- Setup Concluido com Sucesso ---" -ForegroundColor Green
