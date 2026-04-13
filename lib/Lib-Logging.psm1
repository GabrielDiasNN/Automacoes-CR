# ==============================================================================
# ARQUIVO: Lib-Logging.psm1
# VERSÃO: 1.0
# DESCRIÇÃO: Biblioteca de logging para scripts de automação PowerShell.
#            Garante o mesmo formato de linha de log usado em toda a stack
#            (VBScript, VBA, PowerShell): [dd/MM/yyyy HH:mm:ss] [PS] [LEVEL] mensagem
# ==============================================================================

$ErrorActionPreference = "Stop"

$script:Lib_Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# ------------------------------------------------------------------------------
# New-ExecId
# Gera um identificador de execução único no formato yyyyMMdd_HHmmss_xxxx.
# Compatível com o formato gerado pelo VBScript (GerarExecId) e pelo monitor.
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
# Parâmetros:
#   -Message   Texto da mensagem (obrigatório)
#   -Level     INFO | WARN | ERRO       (padrão: INFO)
#   -ExecId    ID de execução (opcional; incluído no prefixo se fornecido)
#   -LogPath   Caminho absoluto do arquivo .log (obrigatório)
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
    $execPrefix = if ([string]::IsNullOrWhiteSpace($ExecId)) { "" } else { " [$ExecId]" }
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
        # Falha silenciosa: não deve impedir a automação principal
    }

    # -- Saída no console com cor por nível --
    $color = switch ($Level) {
        "ERRO" { "Red" }
        "WARN" { "Yellow" }
        default { "Cyan" }
    }
    Write-Host $line -ForegroundColor $color
}

# ------------------------------------------------------------------------------
# Get-AutomacaoLogPath
# Retorna o caminho canônico do log unificado para uma automação.
# Formato: <LogDir>\<Slug>.log  (arquivo único, sem data no nome)
#
# Parâmetros:
#   -Slug     Nome curto da automação (ex: "ReceitasBloqueadas", "Montagem")
#   -LogDir   Diretório base dos logs (obrigatório)
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
# Invoke-LogRotation
# Rotação por conteúdo: mantém apenas linhas com data >= (hoje - KeepDays).
# Linhas sem prefixo de data reconhecível são preservadas (safe default).
# Escrita atômica: grava em .tmp → Move-Item -Force sobre o original.
#
# Parâmetros:
#   -LogPath    Caminho absoluto do arquivo de log
#   -KeepDays   Quantidade de dias a reter (padrão: 15)
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
        # Extrai data no formato [dd/MM/yyyy ...] no início da linha
        if ($line -match '^\[(\d{2}/\d{2}/\d{4})') {
            $dateStr = $Matches[1]
            $parsed = [datetime]::MinValue
            if ([datetime]::TryParseExact($dateStr, 'dd/MM/yyyy', [System.Globalization.CultureInfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::None, [ref]$parsed)) {
                if ($parsed -lt $cutoff) {
                    continue  # linha expirada — descartar
                }
            }
        }
        # Linha sem data ou com data >= cutoff → preservar
        $kept.Add($line)
    }

    if ($kept.Count -eq $lines.Length) { return }  # nada para rotacionar

    $tmpPath = "$LogPath.tmp"
    [System.IO.File]::WriteAllLines($tmpPath, $kept.ToArray(), $script:Lib_Utf8NoBom)
    Move-Item -LiteralPath $tmpPath -Destination $LogPath -Force
}

Export-ModuleMember -Function New-ExecId, Write-AutomacaoLog, Get-AutomacaoLogPath, Invoke-LogRotation
