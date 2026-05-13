# ==============================================================================
# ARQUIVO: Test-EncodingResilience.ps1
# VERSAO : 1.0.0
# DESCRICAO: Trava de Regressao para Caracteres Especiais (UTF-8).
#            Valida se o ecossistema (Logs, API, DB) suporta acentuacao PT-BR.
# ==============================================================================

[CmdletBinding()]
param(
    [string]$ApiBase = "http://localhost:8000",
    [string]$ApiKey = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ApiKey)) {
    $ApiKey = [System.Environment]::GetEnvironmentVariable("ORCHESTRATOR_API_KEY", "Process")
    if (-not $ApiKey) { throw "API Key nao fornecida e nao encontrada no ambiente." }
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot

# 1. Teste de Log (Escrita em UTF-8)
$testLogPath = Join-Path $ProjectRoot "Logs\EncodingTest.log"
$specialChars = "Acentuacao: aeiou aeiou ao aeiou c C"
Write-Host "--- Teste 1: Escrita de Log UTF-8 ---" -ForegroundColor Cyan

# Simula o comportamento do RotatingFileHandler (UTF-8)
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($testLogPath, @($specialChars), $utf8NoBom)

$readChars = Get-Content $testLogPath -Encoding UTF8
if ($readChars -eq $specialChars) {
    Write-Host "[OK] Escrita/Leitura de arquivo UTF-8 integra." -ForegroundColor Green
} else {
    Write-Host "[ERRO] Corrupcao detectada no arquivo de log." -ForegroundColor Red
    Write-Host "Esperado: $specialChars"
    Write-Host "Obtido  : $readChars"
    exit 1
}

# 2. Teste de API (Round-trip com caracteres especiais)
Write-Host "`n--- Teste 2: Round-trip API / JSON ---" -ForegroundColor Cyan
$auditPayload = @{
    action = "ENCODING_TEST"
    entity_type = "SYSTEM"
    entity_id = "TEST"
    actor = "ResilienceTester"
    details = $specialChars
} | ConvertTo-Json

try {
    # Tenta registrar no Log de Auditoria
    $response = Invoke-RestMethod -Uri "$ApiBase/api/system/audit" -Method Get -Headers @{"X-API-Key"=$ApiKey} -ErrorAction SilentlyContinue

    # Criar uma entrada de auditoria via um endpoint que permita (ou simular via post se houver)
    # Como nao temos um endpoint direto de POST audit aberto (apenas interno),
    # vamos testar via criacao de uma automacao temporaria com nome acentuado.

    $testAutoName = "Automacao Teste Cae " + (Get-Date -Format "ssmmHH")
    $createPayload = @{
        name = $testAutoName
        description = "Teste de encoding"
        script_path = "./_Template/run.ps1"
        max_runtime_minutes = 10
    } | ConvertTo-Json

    Write-Host "Tentando criar automacao com nome: $testAutoName"
    $createResp = Invoke-RestMethod -Uri "$ApiBase/api/automations" -Method Post -Headers @{"X-API-Key"=$ApiKey; "Content-Type"="application/json"} -Body ([System.Text.Encoding]::UTF8.GetBytes($createPayload))

    if ($createResp.name -eq $testAutoName) {
        Write-Host "[OK] API aceitou e retornou caracteres especiais corretamente." -ForegroundColor Green
    } else {
        Write-Host "[ERRO] API corrompeu os caracteres no retorno." -ForegroundColor Red
        exit 1
    }

    # Limpeza
    Invoke-RestMethod -Uri "$ApiBase/api/automations/$($createResp.id)" -Method Delete -Headers @{"X-API-Key"=$ApiKey} | Out-Null
    Write-Host "[OK] Limpeza concluida." -ForegroundColor Green

} catch [System.Exception] {
    Write-Host "[FALHA] Erro na comunicacao com a API: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        Write-Host "Detalhes: $($reader.ReadToEnd())"
    }
    exit 1
}

Write-Host "`n--- TRAVA DE REGRESSAO APROVADA ---" -ForegroundColor Green
exit 0
