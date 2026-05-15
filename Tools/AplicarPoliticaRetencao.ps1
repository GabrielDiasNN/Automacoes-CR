[CmdletBinding()]
param(
    [string]$ExecId = "",
    [string]$BasePath = "",
    [int]$KeepLogsDays = 7,
    [int]$KeepBackupsDays = 30,
    [switch]$DryRun
)

if ([string]::IsNullOrWhiteSpace($BasePath)) {
    $BasePath = Split-Path -Parent $PSScriptRoot
}
if ([string]::IsNullOrWhiteSpace($BasePath)) { $BasePath = "." }

$ErrorActionPreference = "Stop"

# 1. Setup e Logging Inicial
$LogDir = Join-Path $BasePath "Logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force }
$RunLogFile = Join-Path $LogDir ("Retention_{0}.log" -f (Get-Date -Format "yyyy-MM"))

function Write-RunLog {
    param([string]$Level, [string]$Message)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] [RETENCAO] [$Level] $Message"
    Write-Host $line
    Add-Content -Path $RunLogFile -Value $line -Encoding UTF8
}

Write-RunLog -Level "INFO" -Message "Iniciando Politica de Retencao v5.0.0 (Pure Modern)"

# 2. Definicao de Datas de Corte
$logsCutoff = (Get-Date).AddDays(-$KeepLogsDays)
$backupsCutoff = (Get-Date).AddDays(-$KeepBackupsDays)

# 3. Limpeza de Logs (Raiz e Modulos)
$targetFolders = @(
    (Join-Path $BasePath "Logs"),
    (Join-Path $BasePath "Montagem de Terceirizados\Logs"),
    (Join-Path $BasePath "Receitas Bloqueadas\Logs"),
    (Join-Path $BasePath "Receitas Emitidas\Logs")
)

foreach ($folder in $targetFolders) {
    if (Test-Path $folder) {
        $files = Get-ChildItem -Path $folder -File -Recurse | Where-Object { $_.LastWriteTime -lt $logsCutoff }
        foreach ($f in $files) {
            if ($DryRun) { Write-RunLog -Level "INFO" -Message "[DRY-RUN] Removendo log antigo: $($f.FullName)" }
            else {
                Remove-Item $f.FullName -Force
                Write-RunLog -Level "INFO" -Message "Log removido: $($f.Name)"
            }
        }
    }
}

# 4. Limpeza de Backups do Orchestrator
$backupDir = Join-Path $BasePath "Orchestrator\Backups"
if (Test-Path $backupDir) {
    $backups = Get-ChildItem -Path $backupDir -Filter "*.db.bak" | Where-Object { $_.LastWriteTime -lt $backupsCutoff }
    foreach ($b in $backups) {
        if ($DryRun) { Write-RunLog -Level "INFO" -Message "[DRY-RUN] Removendo backup antigo: $($b.Name)" }
        else {
            Remove-Item $b.FullName -Force
            Write-RunLog -Level "INFO" -Message "Backup removido: $($b.Name)"
        }
    }
}

# 5. Limpeza do Banco de Dados via API (Purge)
try {
    $apiKey = [System.Environment]::GetEnvironmentVariable("ORCHESTRATOR_API_KEY", "Process")
    if (-not $apiKey) { Write-RunLog -Level "WARN" -Message "ORCHESTRATOR_API_KEY nao encontrada no ambiente."; return }

    $apiUrl = "http://127.0.0.1:8000/api/system/purge"
    if (-not $DryRun) {
        $resp = Invoke-RestMethod -Uri $apiUrl -Method Post -Headers @{"X-API-Key"=$apiKey} -ErrorAction Stop
        Write-RunLog -Level "INFO" -Message "API Purge executado com sucesso."
    }
} catch [System.Exception] {
    Write-RunLog -Level "WARN" -Message "Nao foi possivel invocar o Purge da API (Servidor offline?)"
}

Write-RunLog -Level "INFO" -Message "Politica de Retencao Finalizada."

