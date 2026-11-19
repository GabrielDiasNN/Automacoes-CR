# ==============================================================================
# ARQUIVO: Lib-Logging.psm1
# DESCRICAO: Mascaramento de dados sensiveis e gravacao de log para scripts PS.
# ==============================================================================

$ErrorActionPreference = "Stop"

# Configuracao global de encoding UTF-8 para interoperabilidade no runtime PS 5.1.
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
$script:Lib_Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Protect-SensitiveData {
    <#
    .SYNOPSIS
        Mascara e-mails, credenciais rotuladas e hosts Oracle antes de registrar logs.
    #>
    param([string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) { return "" }

    $masked = $Text -replace '([a-zA-Z0-9._%+-])[a-zA-Z0-9._%+-]+@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', '$1***@$2'
    $masked = $masked -replace '(?i)(token|key|password|pass|secret|credential|auth|apikey|client_secret)([:= ]\s*)([a-zA-Z0-9._%+-]{4,})', '$1$2[REDACTED]'
    $masked = $masked -replace '(DESCRIPTION\s*=\s*\(ADDRESS\s*=\s*\(PROTOCOL\s*=\s*TCP\)\(HOST\s*=\s*)[^)]+', '$1[HIDDEN]'

    return $masked
}

function Write-AutomacaoLog {
    <#
    .SYNOPSIS
        Registra evento JSONL mascarado em disco e imprime linha formatada no console.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message,

        [ValidateSet("INFO", "WARN", "ERRO", "DEBUG")]
        [string]$Level = "INFO",

        [string]$ExecId = "",

        [Parameter(Mandatory = $true)]
        [string]$LogPath,

        [string]$Step = ""
    )

    $cleanMessage = Protect-SensitiveData $Message
    $timestampText = Get-Date -Format 'dd/MM/yyyy HH:mm:ss'
    $execPrefix = if ([string]::IsNullOrWhiteSpace($ExecId)) { "" } else { " [ExecId:$ExecId]" }
    $line = "[$timestampText] [PS] [$Level]$execPrefix $cleanMessage"

    $envStr = $env:ENVIRONMENT
    if ([string]::IsNullOrWhiteSpace($envStr)) { $envStr = "PRD" }

    $autoName = ""
    try {
        $stack = Get-PSCallStack
        foreach ($frame in $stack) {
            if ($frame.ScriptName -and $frame.ScriptName -notmatch 'Lib-Logging\.psm1$') {
                $parentDir = Split-Path -Leaf (Split-Path -Parent $frame.ScriptName)
                if ($parentDir -eq "test") {
                    $autoName = "Test Task"
                    break
                }
                elseif ($parentDir -and $parentDir -notmatch '^(lib|Tools|_Template)$') {
                    $autoName = $parentDir
                    break
                }
            }
        }
    }
    catch [System.Exception] {
        Write-Verbose "Falha ao resolver automation_name via callstack: $($_.Exception.Message)"
    }

    $logObj = [ordered]@{
        timestamp       = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        level           = $Level
        component       = "ps_script"
        environment     = $envStr
        automation_name = $autoName
        exec_id         = $ExecId
        request_id      = "SYSTEM"
        message         = $cleanMessage
    }
    if (-not [string]::IsNullOrWhiteSpace($Step)) {
        $logObj["step"] = $Step
    }
    $jsonLine = $logObj | ConvertTo-Json -Depth 3 -Compress

    try {
        $logDir = Split-Path -Parent $LogPath
        if ($logDir -and -not (Test-Path -LiteralPath $logDir)) {
            New-Item -ItemType Directory -Force -Path $logDir | Out-Null
        }
        [System.IO.File]::AppendAllText($LogPath, "$jsonLine`r`n", $script:Lib_Utf8NoBom)
    }
    catch [System.Exception] {
        Write-Verbose ("Falha ao persistir linha de log em disco: {0}" -f $_.Exception.Message)
    }

    $color = switch ($Level) { "ERRO" { "Red" }; "WARN" { "Yellow" }; "DEBUG" { "Gray" }; default { "Cyan" } }
    Write-Host $line -ForegroundColor $color
}

Export-ModuleMember -Function Protect-SensitiveData, Write-AutomacaoLog