# ==============================================================================
# ARQUIVO: Lib-Logging.psm1
# VERSAO : 1.3
# DESCRICAO: Biblioteca de logging e seguranca para Automacoes Hub.
#            Implementa Auto-Masking, Base64 Bridge e Pre-Flight Diagnostics.
#            Garante integridade PT-BR e conformidade AI-Native.
# ==============================================================================

$ErrorActionPreference = "Stop"

# Configuracao Global de Encoding para Interoperabilidade (Skill log-standardization)
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding  = [System.Text.Encoding]::UTF8

$script:Lib_Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# Identifica a raiz do repositorio no momento da importacao
try {
    $script:ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
} catch [System.Exception] {
    $script:ProjectRoot = "." # Fallback final
}

# ------------------------------------------------------------------------------
# Get-AutomacaoProjectRoot
# ------------------------------------------------------------------------------
function Get-AutomacaoProjectRoot {
    return $script:ProjectRoot
}

# ------------------------------------------------------------------------------
# New-ExecId
# ------------------------------------------------------------------------------
function New-ExecId {
    [CmdletBinding()]
    [OutputType([string])]
    param()
    return (Get-Date -Format 'yyyyMMdd_HHmmss') + "_" + (Get-Random -Minimum 1000 -Maximum 9999)
}

# ------------------------------------------------------------------------------
# Get-FromBase64
# ------------------------------------------------------------------------------
function Get-FromBase64 {
    param([string]$B64)
    if ([string]::IsNullOrWhiteSpace($B64)) { return "" }
    try {
        $bytes = [System.Convert]::FromBase64String($B64)
        return [System.Text.Encoding]::UTF8.GetString($bytes)
    } catch [System.Exception] { return $B64 }
}

# ------------------------------------------------------------------------------
# Protect-SensitiveData
# ------------------------------------------------------------------------------
function Protect-SensitiveData {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return "" }
    # Mascara E-mails
    $masked = $Text -replace '([a-zA-Z0-9._%+-])[a-zA-Z0-9._%+-]+@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', '$1***@$2'
    # Mascara Senhas e Tokens (Expandido)
    $masked = $masked -replace '(?i)(token|key|password|pass|secret|credential|auth|apikey|client_secret)([:= ]\s*)([a-zA-Z0-9._%+-]{4,})', '$1$2[REDACTED]'
    # Mascara Strings de Conexao Oracle
    $masked = $masked -replace '(DESCRIPTION\s*=\s*\(ADDRESS\s*=\s*\(PROTOCOL\s*=\s*TCP\)\(HOST\s*=\s*)[^)]+', '$1[HIDDEN]'
    return $masked
}

# ------------------------------------------------------------------------------
# Get-AutomacaoApiKey
# ------------------------------------------------------------------------------
function Get-AutomacaoApiKey {
    $envPath = Join-Path (Get-AutomacaoProjectRoot) ".env"
    if (Test-Path $envPath) {
        $content = Get-Content $envPath
        foreach ($line in $content) {
            if ($line -match '^ORCHESTRATOR_API_KEY=(.*)$') {
                return $Matches[1].Trim()
            }
        }
    }
    return ""
}

# ------------------------------------------------------------------------------
# Register-ExecutionTelemetry
# ------------------------------------------------------------------------------
function Register-ExecutionTelemetry {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$AutomationName
    )
    $uri = "http://localhost:8000/api/executions/telemetry/start"
    $body = @{ automation_name = $AutomationName } | ConvertTo-Json
    $headers = @{ "X-API-Key" = (Get-AutomacaoApiKey) }
    try {
        $response = Invoke-RestMethod -Uri $uri -Method Post -Headers $headers -Body $body -ContentType "application/json" -ErrorAction Stop
        return $response.exec_id
    } catch {
        Write-Warning "Falha ao registrar telemetria (Orquestrador offline?): $_"
        return (New-ExecId) # Fallback seguro
    }
}

# ------------------------------------------------------------------------------
# Close-ExecutionTelemetry
# ------------------------------------------------------------------------------
function Close-ExecutionTelemetry {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$ExecId,
        [Parameter(Mandatory = $true)]
        [string]$Status,
        [string]$LogPath = ""
    )
    # Evita chamadas caso o ID seja de Fallback ou nulo
    if ([string]::IsNullOrWhiteSpace($ExecId) -or $ExecId -notmatch '^TEL_') {
        return
    }

    $uri = "http://localhost:8000/api/executions/telemetry/end/$ExecId"
    
    $logContent = $null
    if (-not [string]::IsNullOrWhiteSpace($LogPath) -and (Test-Path $LogPath)) {
        try {
            $logContent = [System.IO.File]::ReadAllText($LogPath, $script:Lib_Utf8NoBom)
        } catch { }
    }
    
    $body = @{
        status = $Status
        logs = $logContent
        exit_code = if ($Status -eq "SUCCESS") { 0 } else { 1 }
    } | ConvertTo-Json -Depth 10 -Compress
    
    $headers = @{ "X-API-Key" = (Get-AutomacaoApiKey) }
    try {
        Invoke-RestMethod -Uri $uri -Method Post -Headers $headers -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) -ContentType "application/json; charset=utf-8" -ErrorAction Stop | Out-Null
    } catch {
        Write-Warning "Falha ao fechar telemetria: $_"
    }
}

# ------------------------------------------------------------------------------
# Test-AutomationPreFlight
# ------------------------------------------------------------------------------
function Test-AutomationPreFlight {
    [CmdletBinding()]
    param(
        [string]$ExecId = "bootstrap",
        [string]$LogPath,
        [switch]$CheckOracle,
        [string[]]$CheckPaths = @()
    )

    Write-AutomacaoLog -Message "Iniciando Pre-Flight Check..." -Level "INFO" -ExecId $ExecId -LogPath $LogPath
    $results = @()
    
    # Portabilidade: Detecta a unidade de disco do projeto dinamicamente
    $projectRoot = Get-AutomacaoProjectRoot
    $driveLetter = (Split-Path -Path $projectRoot -Qualifier)
    if ([string]::IsNullOrWhiteSpace($driveLetter)) { $driveLetter = "C:" }
    
    # Deteccao de Disco Hardened (v5.2.0)
    $freeGB = 0
    try {
        # Tentativa 1: Get-CimInstance (Moderno)
        $cimDisk = Get-CimInstance -ClassName Win32_LogicalDisk -Filter "DeviceID='$driveLetter'" -ErrorAction Stop
        $freeGB = [math]::Round($cimDisk.FreeSpace / 1GB, 2)
    } catch {
        try {
            # Tentativa 2: Fallback para Get-PSDrive (Nativo PS)
            $psDrive = Get-PSDrive ($driveLetter.TrimEnd(':')) -ErrorAction Stop
            $freeGB = [math]::Round($psDrive.Free / 1GB, 2)
        } catch {
            $freeGB = -1 # Sinaliza falha na leitura
        }
    }

    if ($freeGB -eq -1) {
        $results += "WARN: Falha ao ler espaco em disco (Ignorado)"
    } elseif ($freeGB -lt 1) {
        $results += "ERRO: Disco critico ($freeGB GB)"
    } else {
        $results += "OK: Disco estavel ($freeGB GB)"
    }

    foreach ($p in $CheckPaths) {
        if (Test-Path $p) {
            $results += "OK: Path: $(Split-Path $p -Leaf)"
        } else {
            $results += "ERRO: Path inacessivel: $(Split-Path $p -Leaf)"
        }
    }

    if ($CheckOracle) {
        if (Test-Connection -ComputerName "SRVDB02" -Count 1 -Quiet) {
            $results += "OK: SRVDB02 On"
        } else {
            $results += "WARN: SRVDB02 Off"
        }
    }

    $allOk = -not ($results -match "ERRO")
    Write-AutomacaoLog -Message "Pre-Flight: $($results -join ' | ')" -Level $(if($allOk){"INFO"}else{"ERRO"}) -ExecId $ExecId -LogPath $LogPath
    return $allOk
}

# ------------------------------------------------------------------------------
# Write-AutomacaoLog
# ------------------------------------------------------------------------------
function Write-AutomacaoLog {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message,
        [ValidateSet("INFO", "WARN", "ERRO", "DEBUG")]
        [string]$Level = "INFO",
        [string]$ExecId = "",
        [Parameter(Mandatory = $true)]
        [string]$LogPath
    )

    $cleanMessage = Protect-SensitiveData $Message
    $timestamp = Get-Date -Format 'dd/MM/yyyy HH:mm:ss'
    $execPrefix = if ([string]::IsNullOrWhiteSpace($ExecId)) { "" } else { " [ExecId:$ExecId]" }
    $line = "[$timestamp] [PS] [$Level]$execPrefix $cleanMessage"
    try {
        $logDir = Split-Path -Parent $LogPath
        if ($logDir -and -not (Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
        $sw = New-Object System.IO.StreamWriter($LogPath, $true, $script:Lib_Utf8NoBom)
        try { $sw.WriteLine($line); $sw.Flush() } finally { $sw.Close(); $sw.Dispose() }
    } catch [System.Exception] {}
    $color = switch ($Level) { "ERRO" { "Red" }; "WARN" { "Yellow" }; "DEBUG" { "Gray" }; default { "Cyan" } }
    Write-Host $line -ForegroundColor $color

    # Envio de Broadcast para o Dashboard (se tiver ExecId atrelado)
    if (-not [string]::IsNullOrWhiteSpace($ExecId) -and $ExecId -match '^TEL_') {
        try {
            $uri = "http://localhost:8000/api/broadcast_log"
            $body = @{ message = $line; exec_id = $ExecId } | ConvertTo-Json -Compress
            $headers = @{ "X-API-Key" = (Get-AutomacaoApiKey) }
            Invoke-RestMethod -Uri $uri -Method Post -Headers $headers -Body $body -ContentType "application/json" -ErrorAction SilentlyContinue | Out-Null
        } catch { }
    }
}

# ------------------------------------------------------------------------------
# Get-AutomacaoLogPath
# ------------------------------------------------------------------------------
function Get-AutomacaoLogPath {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$Slug, [string]$LogDir = "")
    $root = Get-AutomacaoProjectRoot
    if ([string]::IsNullOrWhiteSpace($LogDir)) { $LogDir = Join-Path $root "Logs" }
    elseif (-not [System.IO.Path]::IsPathRooted($LogDir)) { $LogDir = Join-Path $root $LogDir }
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }
    return (Join-Path $LogDir "$Slug.log")
}

# ------------------------------------------------------------------------------
# Test-AutomationEnvironment
# ------------------------------------------------------------------------------
function Test-AutomationEnvironment {
    [CmdletBinding()]
    param([string]$ConfigPath, [string[]]$RequiredPaths = @())
    $res = Test-AutomationPreFlight -CheckPaths $RequiredPaths -LogPath (Join-Path $script:ProjectRoot "Logs\EnvTest.log")
    return [PSCustomObject]@{ Success = $res; Message = "Ambiente validado" }
}

# ------------------------------------------------------------------------------
# Invoke-LogRotation
# ------------------------------------------------------------------------------
function Invoke-LogRotation {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$LogPath, [int]$KeepDays = 15)
    if (-not (Test-Path $LogPath)) { return }
    $cutoff = (Get-Date).Date.AddDays(-1 * [Math]::Abs($KeepDays))
    try {
        $lines = [System.IO.File]::ReadAllLines($LogPath, $script:Lib_Utf8NoBom)
        $kept = [System.Collections.Generic.List[string]]::new($lines.Length)
        foreach ($line in $lines) {
            if ($line -match '^\[(\d{2}/\d{2}/\d{4})') {
                $dateStr = $Matches[1]
                $parsed = [datetime]::MinValue
                if ([datetime]::TryParseExact($dateStr, 'dd/MM/yyyy', [System.Globalization.CultureInfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::None, [ref]$parsed)) {
                    if ($parsed -lt $cutoff) { continue }
                }
            }
            $kept.Add($line)
        }
        if ($kept.Count -lt $lines.Length) {
            $tmpPath = "$LogPath.tmp"; [System.IO.File]::WriteAllLines($tmpPath, $kept.ToArray(), $script:Lib_Utf8NoBom)
            Move-Item -LiteralPath $tmpPath -Destination $LogPath -Force
        }
    } catch [System.Exception] {}
}

# ------------------------------------------------------------------------------
# Enter-AutomationLock
# ------------------------------------------------------------------------------
function Enter-AutomationLock {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$ExecId,
        [string]$LogPath = ""
    )

    $mutexName = "Global\AutomationHub_$ExecId"
    $script:AutomationMutex = New-Object System.Threading.Mutex($false, $mutexName)
    
    if (-not $script:AutomationMutex.WaitOne(5000)) {
        $msg = "CONCORRENCIA DETECTADA: Ja existe um processo rodando para o ExecId $ExecId. Abortando para evitar corrupcao."
        if ([string]::IsNullOrWhiteSpace($LogPath)) {
            Write-Warning $msg
        } else {
            Write-AutomacaoLog -Message $msg -Level "ERRO" -ExecId $ExecId -LogPath $LogPath
        }
        throw $msg
    }

    if (-not [string]::IsNullOrWhiteSpace($LogPath)) {
        Write-AutomacaoLog -Message "Lock global adquirido com sucesso (Mutex: $mutexName)." -Level "DEBUG" -ExecId $ExecId -LogPath $LogPath
    }

    return $true
}

# ------------------------------------------------------------------------------
# Exit-AutomationLock
# ------------------------------------------------------------------------------
function Exit-AutomationLock {
    [CmdletBinding()]
    param(
        [string]$ExecId = "",
        [string]$LogPath = ""
    )
    if ($script:AutomationMutex) {
        $script:AutomationMutex.ReleaseMutex()
        $script:AutomationMutex.Dispose()
        $script:AutomationMutex = $null
    }
}

Export-ModuleMember -Function Get-AutomacaoProjectRoot, New-ExecId, Write-AutomacaoLog, Get-AutomacaoLogPath, Invoke-LogRotation, Test-AutomationEnvironment, Test-AutomationPreFlight, Enter-AutomationLock, Exit-AutomationLock, Register-ExecutionTelemetry, Close-ExecutionTelemetry
