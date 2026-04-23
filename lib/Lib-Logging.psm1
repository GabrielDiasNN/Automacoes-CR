# ==============================================================================
# ARQUIVO: Lib-Logging.psm1
# VERSÃO: 1.1
# DESCRIÇÃO: Biblioteca de logging para scripts de automação PowerShell.
#            Garante o mesmo formato de linha de log usado em toda a stack
#            (VBScript, VBA, PowerShell): [dd/MM/yyyy HH:mm:ss] [PS] [LEVEL] mensagem
#            Suporte a detecção dinâmica de ambiente.
# ==============================================================================

$ErrorActionPreference = "Stop"

$script:Lib_Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# ------------------------------------------------------------------------------
# Get-AutomacaoProjectRoot
# Retorna a raiz do projeto baseada no local desta biblioteca.
# ------------------------------------------------------------------------------
function Get-AutomacaoProjectRoot {
    [CmdletBinding()]
    param()

    # Tenta descobrir baseado no local físico deste arquivo psm1
    $libDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    if ([string]::IsNullOrWhiteSpace($libDir)) {
        # Fallback para PSScriptRoot se invocado de forma que MyInvocation falhe
        $libDir = $PSScriptRoot
    }
    
    # Se estamos em C:\Automacoes\lib\, o pai é a raiz.
    if ([string]::IsNullOrWhiteSpace($libDir)) {
        return "C:\Automacoes" # Hard-fallback seguro
    }
    
    return Split-Path -Parent $libDir
}

# ------------------------------------------------------------------------------
# New-ExecId
# Gera um identificador de execução único no formato yyyyMMdd_HHmmss_xxxx.
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
    catch {}

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
# ------------------------------------------------------------------------------
function Get-AutomacaoLogPath {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Slug,

        [string]$LogDir = ""
    )

    if ([string]::IsNullOrWhiteSpace($LogDir)) {
        $root = Get-AutomacaoProjectRoot
        $LogDir = Join-Path $root "Logs"
    }
    elseif (-not [System.IO.Path]::IsPathRooted($LogDir)) {
        $root = Get-AutomacaoProjectRoot
        $LogDir = Join-Path $root $LogDir
    }

    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    }

    return (Join-Path $LogDir "$Slug.log")
}

# ------------------------------------------------------------------------------
# Test-AutomationEnvironment
# Valida se os requisitos mínimos de ambiente estão presentes.
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
# Rotação por conteúdo para manter o tamanho dos logs sob controle.
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
            $tmpPath = "$LogPath.tmp"
            [System.IO.File]::WriteAllLines($tmpPath, $kept.ToArray(), $script:Lib_Utf8NoBom)
            Move-Item -LiteralPath $tmpPath -Destination $LogPath -Force
        }
    }
    catch {}
}

Export-ModuleMember -Function Get-AutomacaoProjectRoot, New-ExecId, Write-AutomacaoLog, Get-AutomacaoLogPath, Invoke-LogRotation, Test-AutomationEnvironment
