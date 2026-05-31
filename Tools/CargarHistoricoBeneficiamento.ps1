# Requires -Version 5.1
<#
.SYNOPSIS
    Carrega o histórico de produção do Beneficiamento a partir do Oracle de forma fatiada para o SQLite local.
.DESCRIPTION
    Este script interativo divide a carga histórica em fatias diárias para mitigar timeouts do Oracle,
    salvando os resultados diretamente e de forma idempotente no SQLite local.
.PARAMETER DataInicio
    Data inicial da carga no formato YYYY-MM-DD.
.PARAMETER DataFim
    Data final da carga no formato YYYY-MM-DD. Se omitida, usa a data de hoje.
.EXAMPLE
    .\CargarHistoricoBeneficiamento.ps1 -DataInicio "2026-05-01" -DataFim "2026-05-31"
#>
param(
    [string]$DataInicio,
    [string]$DataFim
)

$ErrorActionPreference = 'Stop'

# Garantir codificação correta para o console do PowerShell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = 1

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  CARGA HISTORICA DE PRODUCAO DO BENEFICIAMENTO (ORACLE)" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Determinar caminhos de executáveis e scripts
$rootPath = Resolve-Path (Join-Path $PSScriptRoot "..")
$venvPath = Join-Path $rootPath ".venv"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"
$runnerScript = Join-Path $rootPath "Produção Beneficimento\analise_producao_diaria_beneficiamento.py"

if (-not (Test-Path $pythonExe)) {
    Write-Error "Ambiente virtual (.venv) nao encontrado na raiz! Execute o setup do projeto primeiro."
}
if (-not (Test-Path $runnerScript)) {
    Write-Error "Script runner do beneficiamento nao encontrado em: $runnerScript"
}

$hojeStr = (Get-Date).ToString("yyyy-MM-dd")

# 3. Se as datas não foram passadas por parâmetro, solicitar via prompt interativo
if ([string]::IsNullOrEmpty($DataInicio)) {
    Write-Host "`nPor favor, informe a data inicial e final para a carga retroativa." -ForegroundColor Gray
    Write-Host "A carga sera executada dia a dia automaticamente, evitando timeouts do Oracle.`n" -ForegroundColor Yellow

    # Sugerir 7 dias atrás por padrão
    $defaultInicio = (Get-Date).AddDays(-7).ToString("yyyy-MM-dd")
    $DataInicioInput = Read-Host "Data de Inicio [Padrão: $defaultInicio (7 dias atras)]"
    if ([string]::IsNullOrEmpty($DataInicioInput)) {
        $DataInicio = $defaultInicio
    } else {
        $DataInicio = $DataInicioInput.Trim()
    }
}

if ([string]::IsNullOrEmpty($DataFim)) {
    $DataFimInput = Read-Host "Data de Fim [Padrão: $hojeStr (Hoje)]"
    if ([string]::IsNullOrEmpty($DataFimInput)) {
        $DataFim = $hojeStr
    } else {
        $DataFim = $DataFimInput.Trim()
    }
}

# 4. Validar formato rudimentar de data YYYY-MM-DD
$dateRegex = '^\d{4}-\d{2}-\d{2}$'
if ($DataInicio -notmatch $dateRegex) {
    Write-Error "Data de inicio invalida: '$DataInicio'. Use o formato YYYY-MM-DD."
}
if ($DataFim -notmatch $dateRegex) {
    Write-Error "Data de fim invalida: '$DataFim'. Use o formato YYYY-MM-DD."
}

# 5. Executar carga via runner Python
Write-Host "`nExecutando carga fatiada: $DataInicio ate $DataFim..." -ForegroundColor Green

$arguments = @(
    "`"$runnerScript`"",
    "--range-start", $DataInicio,
    "--range-end", $DataFim
)

try {
    # Executar processo python de forma síncrona, capturando saídas
    $process = Start-Process -FilePath $pythonExe -ArgumentList $arguments -NoNewWindow -PassThru -Wait
    
    if ($process.ExitCode -eq 0) {
        Write-Host "`n==========================================================" -ForegroundColor Green
        Write-Host "   CARGA CONCLUIDA COM SUCESSO NO BANCO DE DADOS LOCAL!" -ForegroundColor Green
        Write-Host "==========================================================" -ForegroundColor Green
    } else {
        Write-Host "`n[FALHA] O processo Python retornou codigo de saida: $($process.ExitCode)" -ForegroundColor Red
        exit $process.ExitCode
    }
}
catch [System.Management.Automation.RuntimeException], [System.Exception] {
    Write-Host "`n[ERRO] Ocorreu uma exceção inesperada durante a execução:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
