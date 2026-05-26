[CmdletBinding()]
param(
    [string]$ExecId = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ExecId)) {
    $ExecId = "MANUAL_STREAM_TEST"
}

Write-Host "[STREAM-TEST] Inicio da validacao online. ExecId=$ExecId"
Start-Sleep -Seconds 5
Write-Host "[STREAM-TEST] Etapa 1/3 - bootstrap"
Start-Sleep -Seconds 5
Write-Host "[STREAM-TEST] Etapa 2/3 - progresso continuo"
Start-Sleep -Seconds 5
Write-Host "[STREAM-TEST] Etapa 3/3 - simulando falha parcial de canal"
Start-Sleep -Seconds 5
Write-Host "[STREAM-TEST] Falha simulada de canal para validar status ERROR/24."
exit 24
[CmdletBinding()]
param(
    [string]$ExecId = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ExecId)) {
    $ExecId = "MANUAL_STREAM_TEST"
}

# Fixture operacional segura:
# - emite logs progressivos para validar streaming online do worker/dashboard;
# - encerra com exit 24 para validar classificacao de falha parcial de canal.
Write-Host "[STREAM-TEST] Inicio da validacao online. ExecId=$ExecId"
Start-Sleep -Seconds 5
Write-Host "[STREAM-TEST] Etapa 1/3 - bootstrap"
Start-Sleep -Seconds 5
Write-Host "[STREAM-TEST] Etapa 2/3 - progresso continuo"
Start-Sleep -Seconds 5
Write-Host "[STREAM-TEST] Etapa 3/3 - simulando falha parcial de canal"
Start-Sleep -Seconds 5
Write-Host "[STREAM-TEST] Falha simulada de canal para validar status ERROR/24."
exit 24
