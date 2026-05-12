# ==============================================================================
# ARQUIVO: Audit-DailyStatus.ps1
# VERSAO : 1.0.0
# DESCRICAO: Consolida falhas das ultimas 24h para analise por IA/Humana.
#            Analisa logs globais e especificos.
# ==============================================================================

$ErrorActionPreference = "SilentlyContinue"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $ProjectRoot "Logs"
$Cutoff = (Get-Date).AddHours(-24)

# Bibliotecas
$libConfig = Join-Path $ProjectRoot "lib\Lib-Config.psm1"
if (Test-Path $libConfig) { Import-Module $libConfig -Force }

$Port = if (Get-Command Get-HubConfig) { Get-HubConfig -Key "HUB_API_PORT" -Default "8000" } else { "8000" }

Write-Host "=== AUDITORIA DIARIA HUB - $(Get-Date) ===" -ForegroundColor Cyan
Write-Host "Raiz: $ProjectRoot"
Write-Host "Periodo: Ultimas 24h (Desde $($Cutoff.ToString('dd/MM/yyyy HH:mm')))"

$Report = [Ordered]@{
    Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Environment = @{
        Port = $Port
        PortStatus = if (Test-NetConnection -ComputerName 127.0.0.1 -Port $Port -WarningAction SilentlyContinue | Where-Object { $_.TcpTestSucceeded }) { "ONLINE" } else { "OFFLINE" }
        FreeDiskGB = [math]::Round((Get-PSDrive C).Free / 1GB, 2)
    }
    ErrorSummary = @{}
    RecentCriticals = @()
}

# Busca Logs
$logFiles = Get-ChildItem -Path $ProjectRoot -Filter "*.log" -Recurse | Where-Object { $_.LastWriteTime -ge $Cutoff }

foreach ($file in $logFiles) {
    $lines = Get-Content $file.FullName
    $errors = $lines | Where-Object { $_ -match "\[ERRO\]" -or $_ -match "ExitCode=[1-9]" }
    
    if ($errors) {
        $Report.ErrorSummary[$file.Name] = $errors.Count
        # Pega os ultimos 3 erros fatais com contexto
        foreach ($err in $errors | Select-Object -Last 3) {
            $Report.RecentCriticals += [Ordered]@{
                File = $file.Name
                Log = $err.Trim()
            }
        }
    }
}

# Output Visual
Write-Host "`n[ESTADO DO SISTEMA]" -ForegroundColor Yellow
Write-Host "Porta ${Port}: $($Report.Environment.PortStatus)"
Write-Host "Disco Livre: $($Report.Environment.FreeDiskGB) GB"

Write-Host "`n[RESUMO DE ERROS]" -ForegroundColor Yellow
if ($Report.ErrorSummary.Count -eq 0) {
    Write-Host "Nenhum erro detectado nas ultimas 24h. Excelencia operacional mantida." -ForegroundColor Green
} else {
    $Report.ErrorSummary.GetEnumerator() | ForEach-Object {
        Write-Host "$($_.Key): $($_.Value) ocorrencia(s)" -ForegroundColor Red
    }
}

Write-Host "`n[DETALHES CRITICOS]" -ForegroundColor Yellow
foreach ($crit in $Report.RecentCriticals) {
    Write-Host "--- $($crit.File) ---" -ForegroundColor Gray
    Write-Host $crit.Log
}

# Salva Report JSON para processamento de IA
$ReportPath = Join-Path $LogDir "Audit_$(Get-Date -Format 'yyyyMMdd').json"
$Report | ConvertTo-Json -Depth 5 | Out-File $ReportPath -Encoding UTF8
Write-Host "`nRelatorio denso salvo em: $ReportPath" -ForegroundColor DarkGray
