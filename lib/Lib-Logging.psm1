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

Export-ModuleMember -Function New-ExecId, Write-AutomacaoLog
