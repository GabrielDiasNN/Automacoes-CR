# ==============================================================================
# ARQUIVO: Lib-Logging.psm1
# VERSÃƒO: 1.0
# DESCRIÃ‡ÃƒO: Biblioteca de logging para scripts de automaÃ§Ã£o PowerShell.
#            Garante o mesmo formato de linha de log usado em toda a stack
#            (VBScript, VBA, PowerShell): [dd/MM/yyyy HH:mm:ss] [PS] [LEVEL] mensagem
# ==============================================================================

$ErrorActionPreference = "Stop"

$script:Lib_Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# ------------------------------------------------------------------------------
# New-ExecId
# Gera um identificador de execuÃ§Ã£o Ãºnico no formato yyyyMMdd_HHmmss_xxxx.
# CompatÃ­vel com o formato gerado pelo VBScript (GerarExecId) e pelo monitor.
# ------------------------------------------------------------------------------
function New-ExecId {
    [CmdletBinding()]
    [OutputType([string])]
    param()

    return (Get-Date -Format 'yyyyMMdd_HHmmss') + "_" + (Get-Random -Minimum 1000 -Maximum 9999)
}

# ------------------------------------------------------------------------------
# Write-AutomacaoLog
# Grava uma linha de log em arquivo e no console.
# Formato: [dd/MM/yyyy HH:mm:ss] [PS] [LEVEL] [ExecId?] mensagem
#
# ParÃ¢metros:
#   -Message   Texto da mensagem (obrigatÃ³rio)
#   -Level     INFO | WARN | ERRO       (padrÃ£o: INFO)
#   -ExecId    ID de execuÃ§Ã£o (opcional; incluÃ­do no prefixo se fornecido)
#   -LogPath   Caminho absoluto do arquivo .log (obrigatÃ³rio)
# ------------------------------------------------------------------------------
function Write-AutomacaoLog {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message,

        [ValidateSet("INFO", "WARN", "ERRO")]
        [string]$Level = "INFO",

        [string]$ExecId = "",

        [Parameter(Mandatory = $true)]
        [string]$LogPath
    )

    $timestamp = Get-Date -Format 'dd/MM/yyyy HH:mm:ss'
    $execPrefix = if ([string]::IsNullOrWhiteSpace($ExecId)) { "" } else { " [ExecId:$ExecId]" }
    $line = "[$timestamp] [PS] [$Level]$execPrefix $Message"

    # -- Gravar em arquivo (UTF-8 sem BOM, append) --
    try {
        $logDir = Split-Path -Parent $LogPath
        if ($logDir -and -not (Test-Path $logDir)) {
            New-Item -ItemType Directory -Force -Path $logDir | Out-Null
        }

        $sw = New-Object System.IO.StreamWriter($LogPath, $true, $script:Lib_Utf8NoBom)
        try {
            $sw.WriteLine($line)
            $sw.Flush()
        }
        finally {
            $sw.Close()
            $sw.Dispose()
        }
    }
    catch {
        # Falha silenciosa: nÃ£o deve impedir a automaÃ§Ã£o principal
    }

    # -- SaÃ­da no console com cor por nÃ­vel --
    $color = switch ($Level) {
        "ERRO" { "Red" }
        "WARN" { "Yellow" }
        default { "Cyan" }
    }
    Write-Host $line -ForegroundColor $color
}

# ------------------------------------------------------------------------------
# Get-AutomacaoLogPath
# Retorna o caminho canÃ´nico do log unificado para uma automaÃ§Ã£o.
# Formato: <LogDir>\<Slug>.log  (arquivo Ãºnico, sem data no nome)
#
# ParÃ¢metros:
#   -Slug     Nome curto da automaÃ§Ã£o (ex: "ReceitasBloqueadas", "Montagem")
#   -LogDir   DiretÃ³rio base dos logs (obrigatÃ³rio)
# ------------------------------------------------------------------------------
function Get-AutomacaoLogPath {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Slug,

        [Parameter(Mandatory = $true)]
        [string]$LogDir
    )

    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    }

    return (Join-Path $LogDir "$Slug.log")
}

# ------------------------------------------------------------------------------
# Test-AutomationEnvironment
# Valida se os requisitos mÃ­nimos de ambiente estÃ£o presentes.
# Retorna um objeto com [bool]$Success e [string]$Message.
# ------------------------------------------------------------------------------
function Test-AutomationEnvironment {
    [CmdletBinding()]
    param(
        [string]$ConfigPath,
        [string[]]$RequiredPaths = @()
    )

    if (-not [string]::IsNullOrWhiteSpace($ConfigPath)) {
        if (-not (Test-Path $ConfigPath)) {
            return [PSCustomObject]@{ Success = $false; Message = "Arquivo de configuracao nao encontrado: $ConfigPath" }
        }
        try {
            $null = Get-Content $ConfigPath -Raw | ConvertFrom-Json
        }
        catch {
            return [PSCustomObject]@{ Success = $false; Message = "Erro de sintaxe no JSON de configuracao: $($_.Exception.Message)" }
        }
    }

    foreach ($path in $RequiredPaths) {
        if (-not (Test-Path $path)) {
            return [PSCustomObject]@{ Success = $false; Message = "Caminho obrigatorio inacessivel: $path" }
        }
    }

    return [PSCustomObject]@{ Success = $true; Message = "Ambiente validado com sucesso" }
}

# ------------------------------------------------------------------------------
# Invoke-LogRotation
# RotaÃ§Ã£o por conteÃºdo: mantÃ©m apenas linhas com data >= (hoje - KeepDays).
# Linhas sem prefixo de data reconhecÃ­vel sÃ£o preservadas (safe default).
# Escrita atÃ´mica: grava em .tmp â†’ Move-Item -Force sobre o original.
#
# ParÃ¢metros:
#   -LogPath    Caminho absoluto do arquivo de log
#   -KeepDays   Quantidade de dias a reter (padrÃ£o: 15)
# ------------------------------------------------------------------------------
function Invoke-LogRotation {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$LogPath,

        [int]$KeepDays = 15
    )

    if (-not (Test-Path $LogPath)) { return }

    $cutoff = (Get-Date).Date.AddDays(-1 * [Math]::Abs($KeepDays))
    $lines = [System.IO.File]::ReadAllLines($LogPath, $script:Lib_Utf8NoBom)

    $kept = [System.Collections.Generic.List[string]]::new($lines.Length)

    foreach ($line in $lines) {
        # Extrai data no formato [dd/MM/yyyy ...] no inÃ­cio da linha
        if ($line -match '^\[(\d{2}/\d{2}/\d{4})') {
            $dateStr = $Matches[1]
            $parsed = [datetime]::MinValue
            if ([datetime]::TryParseExact($dateStr, 'dd/MM/yyyy', [System.Globalization.CultureInfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::None, [ref]$parsed)) {
                if ($parsed -lt $cutoff) {
                    continue  # linha expirada â€” descartar
                }
            }
        }
        # Linha sem data ou com data >= cutoff â†’ preservar
        $kept.Add($line)
    }

    if ($kept.Count -eq $lines.Length) { return }  # nada para rotacionar

    $tmpPath = "$LogPath.tmp"
    [System.IO.File]::WriteAllLines($tmpPath, $kept.ToArray(), $script:Lib_Utf8NoBom)
    Move-Item -LiteralPath $tmpPath -Destination $LogPath -Force
}

Export-ModuleMember -Function New-ExecId, Write-AutomacaoLog, Get-AutomacaoLogPath, Invoke-LogRotation, Test-AutomationEnvironment
