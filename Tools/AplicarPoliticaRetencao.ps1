[CmdletBinding()]
param(
    [string]$ExecId = "",
    [string]$BasePath = "C:\Automacoes",
    [int]$KeepLogsDays = 7,
    [int]$KeepAuditDays = 30,
    [int]$KeepBootstrapDays = 15,
    [switch]$DryRun,
    [switch]$SkipWhatsAppCachePurge
)

$ErrorActionPreference = "Stop"

# Importar biblioteca de logging padrÃ£o
$libPath = Join-Path $BasePath "lib\Lib-Logging.psm1"
if (Test-Path $libPath) {
    Import-Module $libPath -Force
}

$LogDir = Join-Path $BasePath "Logs"
$RunLogFile = Join-Path $LogDir ("Retention_{0}.log" -f (Get-Date -Format "yyyy-MM"))

if ([string]::IsNullOrWhiteSpace($ExecId)) {
    if (Get-Command New-ExecId -ErrorAction SilentlyContinue) {
        $ExecId = New-ExecId
    }
    else {
        $ExecId = "RET_{0}_{1}" -f (Get-Date -Format "yyyyMMdd_HHmmss"), (Get-Random -Minimum 1000 -Maximum 9999)
    }
}

$script:Stats = [ordered]@{
    FilesRemoved = 0
    DirsRemoved  = 0
    BytesFreed   = 0
    Errors       = 0
}

function Write-RunLog {
    param(
        [string]$Level,
        [string]$Message
    )

    if (Get-Command Write-AutomacaoLog -ErrorAction SilentlyContinue) {
        # Traduzir nÃ­veis para os suportados pela Lib-Logging
        $mappedLevel = switch ($Level) {
            "ERROR" { "ERRO" }
            "FATAL" { "ERRO" }
            "WARN"  { "WARN" }
            default { "INFO" }
        }
        Write-AutomacaoLog -Message $Message -Level $mappedLevel -ExecId $ExecId -LogPath $RunLogFile
    }
    else {
        # Fallback caso a biblioteca falhe
        $ts = Get-Date -Format "dd/MM/yyyy HH:mm:ss"
        $line = "[$ts] [PS] [$Level] [ExecId:$ExecId] $Message"
        Write-Host $line
        try {
            if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
            Add-Content -Path $RunLogFile -Value $line -Encoding UTF8
        }
        catch { } # Ignorado
    }
}

function Remove-FileSafe {
    param(
        [System.IO.FileInfo]$File,
        [string]$Reason
    )

    if (-not $File) { return }

    try {
        if ($DryRun) {
            Write-RunLog -Level "INFO" -Message ("[DRY-RUN] Remover arquivo ({0}): {1}" -f $Reason, $File.FullName)
            return
        }

        $length = $File.Length
        Remove-Item -LiteralPath $File.FullName -Force -ErrorAction Stop
        $script:Stats.FilesRemoved++
        $script:Stats.BytesFreed += [int64]$length
        Write-RunLog -Level "INFO" -Message ("Arquivo removido ({0}): {1}" -f $Reason, $File.FullName)
    }
    catch {
        $script:Stats.Errors++
        Write-RunLog -Level "WARN" -Message ("Falha ao remover arquivo ({0}): {1} | Erro: {2}" -f $Reason, $File.FullName, $_)
    }
}

function Remove-DirectorySafe {
    param(
        [string]$DirectoryPath,
        [string]$Reason
    )

    if (-not (Test-Path -LiteralPath $DirectoryPath)) { return }

    try {
        $dirItem = Get-Item -LiteralPath $DirectoryPath -ErrorAction Stop
        $files = Get-ChildItem -LiteralPath $DirectoryPath -Recurse -File -ErrorAction SilentlyContinue
        $bytes = ($files | Measure-Object -Property Length -Sum).Sum
        if (-not $bytes) { $bytes = 0 }

        if ($DryRun) {
            Write-RunLog -Level "INFO" -Message ("[DRY-RUN] Remover diretÃ³rio ({0}): {1} | arquivos={2}" -f $Reason, $DirectoryPath, $files.Count)
            return
        }

        Remove-Item -LiteralPath $dirItem.FullName -Recurse -Force -ErrorAction Stop
        $script:Stats.DirsRemoved++
        $script:Stats.BytesFreed += [int64]$bytes
        Write-RunLog -Level "INFO" -Message ("DiretÃ³rio removido ({0}): {1}" -f $Reason, $DirectoryPath)
    }
    catch {
        $script:Stats.Errors++
        Write-RunLog -Level "WARN" -Message ("Falha ao remover diretÃ³rio ({0}): {1} | Erro: {2}" -f $Reason, $DirectoryPath, $_)
    }
}

function Remove-OldLogFiles {
    param(
        [string]$DirectoryPath,
        [datetime]$Cutoff,
        [string]$Reason,
        [string]$Filter = "*.log"
    )

    if (-not (Test-Path -LiteralPath $DirectoryPath)) {
        Write-RunLog -Level "INFO" -Message ("DiretÃ³rio inexistente ({0}): {1}" -f $Reason, $DirectoryPath)
        return
    }

    $files = Get-ChildItem -LiteralPath $DirectoryPath -File -Filter $Filter -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt $Cutoff }

    foreach ($file in $files) {
        Remove-FileSafe -File $file -Reason $Reason
    }
}

try {
    Write-RunLog -Level "INFO" -Message "Inicio da politica de retencao."
    Write-RunLog -Level "INFO" -Message ("Parametros: BasePath={0} | KeepLogsDays={1} | KeepAuditDays={2} | KeepBootstrapDays={3} | DryRun={4} | SkipWhatsAppCachePurge={5}" -f $BasePath, $KeepLogsDays, $KeepAuditDays, $KeepBootstrapDays, [bool]$DryRun, [bool]$SkipWhatsAppCachePurge)

    $logsCutoff = (Get-Date).AddDays(-1 * [math]::Abs($KeepLogsDays))
    $auditCutoff = (Get-Date).AddDays(-1 * [math]::Abs($KeepAuditDays))
    $bootstrapCutoff = (Get-Date).AddDays(-1 * [math]::Abs($KeepBootstrapDays))

    $logFolders = @(
        (Join-Path $BasePath "_Template\Logs"),
        (Join-Path $BasePath "Montagem de Terceirizados\Logs"),
        (Join-Path $BasePath "Receitas Bloqueadas\Logs"),
        (Join-Path $BasePath "Receitas Emitidas\Logs"),
        (Join-Path $BasePath "Audit\vba")
    )

    # Limpar logs diÃ¡rios legados (log_DD-MM-YYYY.log, Execution.log, VBA_Internal.log)
    $legacyFilters = @("log_*.log", "Execution.log", "VBA_Internal.log")
    foreach ($folder in $logFolders) {
        foreach ($filter in $legacyFilters) {
            Remove-OldLogFiles -DirectoryPath $folder -Cutoff $logsCutoff -Reason "retencao-logs-legado" -Filter $filter
        }
    }

    # Logs unificados (ReceitasBloqueadas.log, ReceitasEmitidas.log, Montagem.log)
    # Safety net: remover apenas se nao modificados ha 15+ dias (rotaÃ§Ã£o de conteÃºdo Ã© feita pelo run.ps1)
    $unifiedCutoff = (Get-Date).AddDays(-15)
    $unifiedLogs = @(
        (Join-Path $BasePath "Montagem de Terceirizados\Logs\Montagem.log"),
        (Join-Path $BasePath "Receitas Bloqueadas\Logs\ReceitasBloqueadas.log"),
        (Join-Path $BasePath "Receitas Emitidas\Logs\ReceitasEmitidas.log")
    )
    foreach ($logFile in $unifiedLogs) {
        if (Test-Path -LiteralPath $logFile) {
            $item = Get-Item -LiteralPath $logFile
            if ($item.LastWriteTime -lt $unifiedCutoff) {
                Remove-FileSafe -File $item -Reason "retencao-log-unificado-inativo"
            }
        }
    }

    # Arquivo legado ReceitasBloqueadas.txt na raiz do mÃ³dulo
    $legacyRbTxt = Join-Path $BasePath "Receitas Bloqueadas\ReceitasBloqueadas.txt"
    if (Test-Path -LiteralPath $legacyRbTxt) {
        $rbTxtItem = Get-Item -LiteralPath $legacyRbTxt
        if ($rbTxtItem.LastWriteTime -lt $logsCutoff) {
            Remove-FileSafe -File $rbTxtItem -Reason "retencao-log-legado-txt"
        }
    }

    # Monitor logs â€” polÃ­tica padrÃ£o (KeepLogsDays)
    Remove-OldLogFiles -DirectoryPath (Join-Path $BasePath "Logs") `
        -Cutoff $logsCutoff -Reason "retencao-monitor-log" -Filter "Monitor_*.log"

    # Logs de retenÃ§Ã£o prÃ³prios â€” polÃ­tica de auditoria (KeepAuditDays)
    Remove-OldLogFiles -DirectoryPath (Join-Path $BasePath "Logs") `
        -Cutoff $auditCutoff -Reason "retencao-logs-retencao" -Filter "Retention_*.log"

    $bootstrapFile = Join-Path $BasePath "Receitas Bloqueadas\sendWhatsApp-bootstrap.log"
    if (Test-Path -LiteralPath $bootstrapFile) {
        $bootstrapItem = Get-Item -LiteralPath $bootstrapFile
        if ($bootstrapItem.LastWriteTime -lt $bootstrapCutoff) {
            Remove-FileSafe -File $bootstrapItem -Reason "retencao-bootstrap"
        }
    }

    $auditRoot = Join-Path $BasePath "Audit"
    if (Test-Path -LiteralPath $auditRoot) {
        $auditFiles = Get-ChildItem -LiteralPath $auditRoot -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt $auditCutoff }

        foreach ($file in $auditFiles) {
            Remove-FileSafe -File $file -Reason "retencao-audit"
        }

        $auditDirs = Get-ChildItem -LiteralPath $auditRoot -Recurse -Directory -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending
        foreach ($dir in $auditDirs) {
            try {
                $hasFiles = @(Get-ChildItem -LiteralPath $dir.FullName -Force -ErrorAction SilentlyContinue).Count -gt 0
                if (-not $hasFiles) {
                    if ($DryRun) {
                        Write-RunLog -Level "INFO" -Message ("[DRY-RUN] Remover diretÃ³rio vazio (retencao-audit): {0}" -f $dir.FullName)
                    }
                    else {
                        Remove-Item -LiteralPath $dir.FullName -Force -ErrorAction Stop
                        $script:Stats.DirsRemoved++
                        Write-RunLog -Level "INFO" -Message ("DiretÃ³rio vazio removido (retencao-audit): {0}" -f $dir.FullName)
                    }
                }
            }
            catch {
                $script:Stats.Errors++
                Write-RunLog -Level "WARN" -Message ("Falha ao remover diretÃ³rio vazio no Audit: {0} | Erro: {1}" -f $dir.FullName, $_)
            }
        }
    }

    if (-not $SkipWhatsAppCachePurge) {
        $waSessionRoot = Join-Path $BasePath "Receitas Bloqueadas\.wwebjs_auth\session-receitas-bloqueadas"
        if (Test-Path -LiteralPath $waSessionRoot) {
            $waCacheDirectories = @(
                "Default\Cache",
                "Default\Code Cache",
                "Default\GPUCache",
                "Default\DawnGraphiteCache",
                "Default\DawnWebGPUCache",
                "Default\Service Worker\CacheStorage",
                "GrShaderCache",
                "GraphiteDawnCache",
                "ShaderCache"
            )

            foreach ($relative in $waCacheDirectories) {
                $fullDir = Join-Path $waSessionRoot $relative
                Remove-DirectorySafe -DirectoryPath $fullDir -Reason "retencao-whatsapp-cache"
            }

            $oldSuffixFiles = Get-ChildItem -LiteralPath $waSessionRoot -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match "(?i)(\.old$|\.tmp$|\.bak$|\.temp$)" }
            foreach ($file in $oldSuffixFiles) {
                Remove-FileSafe -File $file -Reason "retencao-whatsapp-arquivo-temporario"
            }

            $browserMetrics = Join-Path $waSessionRoot "BrowserMetrics-spare.pma"
            if (Test-Path -LiteralPath $browserMetrics) {
                Remove-FileSafe -File (Get-Item -LiteralPath $browserMetrics) -Reason "retencao-whatsapp-browser-metrics"
            }
        }
        else {
            Write-RunLog -Level "INFO" -Message "Sessao WhatsApp nao encontrada. Nenhuma limpeza de cache aplicada."
        }
    }

    $summary = "Resumo: filesRemoved={0} | dirsRemoved={1} | bytesFreed={2:N2} MB | errors={3}" -f $script:Stats.FilesRemoved, $script:Stats.DirsRemoved, ($script:Stats.BytesFreed / 1MB), $script:Stats.Errors
    if ($DryRun) {
        Write-RunLog -Level "INFO" -Message ("[DRY-RUN] " + $summary)
    }
    else {
        Write-RunLog -Level "INFO" -Message $summary
    }

    if ($script:Stats.Errors -gt 0) {
        exit 2
    }

    exit 0
}
catch {
    Write-RunLog -Level "ERRO" -Message ("Falha fatal na politica de retencao: {0}" -f $_)
    exit 1
}
