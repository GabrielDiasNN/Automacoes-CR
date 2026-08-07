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

$script:Lib_Utf8WithBom = [System.Text.Encoding]::UTF8

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

$script:CurrentAutomationName = $AutomationName

$uri = "http://localhost:8000/api/executions/telemetry/start"

$body = @{ automation_name = $AutomationName } | ConvertTo-Json

$headers = @{ "X-API-Key" = (Get-AutomacaoApiKey) }

try {

$response = Invoke-RestMethod -Uri $uri -Method Post -Headers $headers -Body $body -ContentType "application/json" -ErrorAction Stop

return $response.exec_id

} catch [System.Exception] {

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

# Garante que os logs remanescentes do buffer sejam enviados antes do fechamento

Send-AutomacaoLogBroadcast

$uri = "http://localhost:8000/api/executions/telemetry/end/$ExecId"

$logContent = $null

if (-not [string]::IsNullOrWhiteSpace($LogPath) -and (Test-Path $LogPath)) {

try {

$logContent = [System.IO.File]::ReadAllText($LogPath, $script:Lib_Utf8WithBom)

} catch [System.Exception] { }

}

$body = @{

status = $Status

logs = $logContent

exit_code = if ($Status -eq "SUCCESS") { 0 } else { 1 }

} | ConvertTo-Json -Depth 10 -Compress

$headers = @{ "X-API-Key" = (Get-AutomacaoApiKey) }

try {

Invoke-RestMethod -Uri $uri -Method Post -Headers $headers -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) -ContentType "application/json; charset=utf-8" -ErrorAction Stop | Out-Null

} catch [System.Exception] {

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

[string]$OracleHost = "",

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

} catch [System.Exception] {

try {

# Tentativa 2: Fallback para Get-PSDrive (Nativo PS)

$psDrive = Get-PSDrive ($driveLetter.TrimEnd(':')) -ErrorAction Stop

$freeGB = [math]::Round($psDrive.Free / 1GB, 2)

} catch [System.Exception] {

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

# Host do Oracle nunca fica hardcoded aqui: resolve de -OracleHost, senao de
# ORACLE_CONNECT_STRING (env ou .env local), sempre parametrizado e nao versionado.

$oracleHostResolved = $OracleHost

if ([string]::IsNullOrWhiteSpace($oracleHostResolved)) {

$connStr = [System.Environment]::GetEnvironmentVariable("ORACLE_CONNECT_STRING", "Process")

if ([string]::IsNullOrWhiteSpace($connStr)) {

$envFile = Join-Path $script:ProjectRoot ".env"

if (Test-Path $envFile) {

$match = Select-String -Path $envFile -Pattern '^\s*ORACLE_CONNECT_STRING\s*=\s*(.+)$' | Select-Object -First 1

if ($match) { $connStr = $match.Matches[0].Groups[1].Value.Trim() }

}

}

if (-not [string]::IsNullOrWhiteSpace($connStr)) { $oracleHostResolved = ($connStr -split '[:/]')[0].Trim() }

}

if ([string]::IsNullOrWhiteSpace($oracleHostResolved)) {

$results += "WARN: Oracle host nao configurado (ORACLE_CONNECT_STRING ausente)"

} elseif (Test-Connection -ComputerName $oracleHostResolved -Count 1 -Quiet) {

$results += "OK: Oracle ($oracleHostResolved) On"

} else {

$results += "WARN: Oracle ($oracleHostResolved) Off"

}

}

$allOk = -not ($results -match "ERRO")

Write-AutomacaoLog -Message "Pre-Flight: $($results -join ' | ')" -Level $(if($allOk){"INFO"}else{"ERRO"}) -ExecId $ExecId -LogPath $LogPath

return $allOk

}

# ------------------------------------------------------------------------------

# Send-AutomacaoLogBroadcast

# ------------------------------------------------------------------------------

function Send-AutomacaoLogBroadcast {

    if (-not $script:BroadcastQueue -or $script:BroadcastQueue.Count -eq 0) { return }

    try {

        $uri = "http://localhost:8000/api/broadcast_logs"

        $body = @{ logs = $script:BroadcastQueue } | ConvertTo-Json -Depth 3 -Compress

        $headers = @{ "X-API-Key" = (Get-AutomacaoApiKey) }

        # Inicia Runspace ou Start-Job? Nao, no caso faremos sincrono por lote (Batch)

        Invoke-RestMethod -Uri $uri -Method Post -Headers $headers -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) -ContentType "application/json; charset=utf-8" -ErrorAction SilentlyContinue -TimeoutSec 2 | Out-Null

    } catch [System.Exception] { }

    finally {

        $script:BroadcastQueue.Clear()

    }

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

$timestampText = Get-Date -Format 'dd/MM/yyyy HH:mm:ss'
$execPrefix = if ([string]::IsNullOrWhiteSpace($ExecId)) { "" } else { " [ExecId:$ExecId]" }
$line = "[$timestampText] [PS] [$Level]$execPrefix $cleanMessage"

$envStr = $env:ENVIRONMENT
if ([string]::IsNullOrWhiteSpace($envStr)) { $envStr = "PRD" }

$autoName = $script:CurrentAutomationName
if ([string]::IsNullOrWhiteSpace($autoName)) {
    try {
        $stack = Get-PSCallStack
        foreach ($frame in $stack) {
            if ($frame.ScriptName -and $frame.ScriptName -notmatch 'Lib-Logging\.psm1$') {
                $parentDir = Split-Path -Leaf (Split-Path -Parent $frame.ScriptName)
                if ($parentDir -eq "test") {
                    $autoName = "Test Task"
                    break
                } elseif ($parentDir -and $parentDir -notmatch '^(lib|Tools|_Template)$') {
                    $autoName = $parentDir
                    break
                }
            }
        }
    } catch [System.Exception] { }
}
if ([string]::IsNullOrWhiteSpace($autoName)) { $autoName = "" }
$logObj = [ordered]@{
    timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    level = $Level
    component = "ps_script"
    environment = $envStr
    automation_name = $autoName
    exec_id = $ExecId
    request_id = "SYSTEM"
    message = $cleanMessage
}
$jsonLine = $logObj | ConvertTo-Json -Depth 3 -Compress

try {

$logDir = Split-Path -Parent $LogPath

if ($logDir -and -not (Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }

# Otimizacao de I/O: AppendAllText eh mais rapido que instanciar StreamWriter, usar e fechar linha a linha.

[System.IO.File]::AppendAllText($LogPath, "$jsonLine`r`n", $script:Lib_Utf8WithBom)

} catch [System.Exception] { Write-Verbose ("Falha ao persistir linha de log em disco: {0}" -f $_.Exception.Message) }

$color = switch ($Level) { "ERRO" { "Red" }; "WARN" { "Yellow" }; "DEBUG" { "Gray" }; default { "Cyan" } }

Write-Host $line -ForegroundColor $color

# Envio de Broadcast para o Dashboard (se tiver ExecId atrelado)

if (-not [string]::IsNullOrWhiteSpace($ExecId) -and $ExecId -match '^TEL_') {

    if (-not $script:BroadcastQueue) { $script:BroadcastQueue = [System.Collections.Generic.List[Hashtable]]::new() }

    $script:BroadcastQueue.Add(@{ message = $line; exec_id = $ExecId })

    if ($script:BroadcastQueue.Count -ge 10) {

        Send-AutomacaoLogBroadcast

    }

}

}

# ------------------------------------------------------------------------------

# Get-ForwardedLogLevel

# ------------------------------------------------------------------------------

function Get-ForwardedLogLevel {
    <#
    .SYNOPSIS
        Extrai o nivel de log de uma linha ja formatada por um processo filho.

    .DESCRIPTION
        Scripts de automacao encaminham para o log a saida de processos Python/Node
        que ja vem prefixada com [INFO]/[WARN]/[ERROR]. Esta funcao reaproveita esse
        nivel em vez de rebaixar tudo para INFO, normalizando ERROR->ERRO (padrao
        do Write-AutomacaoLog).

        Centralizada aqui na revisao arquitetural (achado A1): a mesma
        implementacao estava copiada em tres run.ps1 de automacao.

    .PARAMETER Message
        Linha de log recebida do processo filho.

    .PARAMETER Fallback
        Nivel usado quando a linha nao traz marcador reconhecivel. Padrao: INFO.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        # Alias -Msg mantido: e o nome usado pelas chamadas ja existentes nos run.ps1.
        [Alias('Msg')]
        [string]$Message,
        [string]$Fallback = "INFO"
    )

    if ([string]::IsNullOrWhiteSpace($Message)) { return $Fallback }

    $detected = [regex]::Match(
        $Message,
        '\[(INFO|WARN|ERROR|ERRO|DEBUG)\]',
        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
    if (-not $detected.Success) { return $Fallback }

    switch ($detected.Groups[1].Value.ToUpperInvariant()) {
        "ERROR" { return "ERRO" }
        "ERRO" { return "ERRO" }
        "WARN" { return "WARN" }
        "DEBUG" { return "DEBUG" }
        default { return "INFO" }
    }
}

# ------------------------------------------------------------------------------

# Get-AutomationExitStatus

# ------------------------------------------------------------------------------

function Get-AutomationExitStatus {
    <#
    .SYNOPSIS
        Classifica um exit code de automacao como sucesso ou falha.

    .DESCRIPTION
        Extraida de `Exit-AutomationWithCode` para ficar testavel isoladamente
        sem precisar mockar `exit` (que encerraria o processo de teste). Era
        exatamente esta classificacao que tinha divergido entre run.ps1 (-eq 0,
        -eq 0 -or -eq 2, -in $NonFailureCodes) antes da consolidacao.

    .PARAMETER Code
        Codigo de saida a classificar.

    .PARAMETER NonFailureCodes
        Codigos que contam como sucesso. Padrao: apenas 0.
    #>
    [CmdletBinding()]
    [OutputType([bool])]
    param(
        [Parameter(Mandatory = $true)][int]$Code,
        [int[]]$NonFailureCodes = @(0)
    )
    return $Code -in $NonFailureCodes
}

# ------------------------------------------------------------------------------

# Exit-AutomationWithCode

# ------------------------------------------------------------------------------

function Exit-AutomationWithCode {
    <#
    .SYNOPSIS
        Finaliza uma automacao: loga o encerramento, fecha a telemetria e sai do processo.

    .DESCRIPTION
        Centraliza o padrao de `Exit-WithCode` que cada run.ps1 reimplementava
        localmente: gravar as linhas finais de log, classificar o Code como
        sucesso/falha (via `Get-AutomationExitStatus`) e fechar a telemetria
        antes de `exit`. A lista de codigos que NAO representam falha
        (`NonFailureCodes`) e propria de cada automacao -- so a estrutura e
        compartilhada, nao a lista.

        Cada run.ps1 continua com sua propria funcao local `Exit-WithCode`, que
        so encaminha para esta com ExecId/LogPath/NonFailureCodes fechados por
        closure -- os call sites ao longo do script nao mudam.

    .PARAMETER Code
        Codigo de saida do processo.

    .PARAMETER Msg
        Mensagem final opcional, logada antes da linha de encerramento.

    .PARAMETER ExecId
        Identificador da execucao corrente (telemetria/log).

    .PARAMETER LogPath
        Caminho do arquivo de log jsonl da automacao.

    .PARAMETER NonFailureCodes
        Codigos de saida que contam como sucesso para fins de log/telemetria.
        Padrao: apenas 0.

    .PARAMETER EndMessage
        Linha final de encerramento gravada no log. Padrao mantem o texto
        historico de Receitas Bloqueadas/Receitas Emitidas ("FIM - Finalizado.
        ExitCode=..."); OBs Fluxo Sem Tingimento e OBs Paradas Fase passam
        "FIM - ExitCode=..." explicitamente para preservar o texto que usavam
        antes da consolidacao.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][int]$Code,
        [string]$Msg = "",
        [Parameter(Mandatory = $true)][string]$ExecId,
        [Parameter(Mandatory = $true)][string]$LogPath,
        [int[]]$NonFailureCodes = @(0),
        [string]$EndMessage = "FIM - Finalizado. ExitCode=$Code"
    )

    $isSuccess = Get-AutomationExitStatus -Code $Code -NonFailureCodes $NonFailureCodes

    if ($Msg) {
        Write-AutomacaoLog -Message $Msg -Level $(if ($isSuccess) { "INFO" } else { "ERRO" }) -ExecId $ExecId -LogPath $LogPath
    }
    Write-AutomacaoLog -Message $EndMessage -Level "INFO" -ExecId $ExecId -LogPath $LogPath
    Write-AutomacaoLog -Message "=========================================================================================" -Level "INFO" -ExecId $ExecId -LogPath $LogPath

    if (Get-Command Close-ExecutionTelemetry -ErrorAction SilentlyContinue) {
        $finalStatus = if ($isSuccess) { "SUCCESS" } else { "ERROR" }
        Close-ExecutionTelemetry -ExecId $ExecId -Status $finalStatus -LogPath $LogPath
    }

    exit $Code
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

return (Join-Path $LogDir "$Slug.jsonl")

}

# ------------------------------------------------------------------------------

# Test-AutomationEnvironment

# ------------------------------------------------------------------------------

function Test-AutomationEnvironment {

[CmdletBinding()]

param([string]$ConfigPath, [string[]]$RequiredPaths = @())

$res = Test-AutomationPreFlight -CheckPaths $RequiredPaths -LogPath (Join-Path $script:ProjectRoot "Logs\EnvTest.jsonl")

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

$lines = [System.IO.File]::ReadAllLines($LogPath, $script:Lib_Utf8WithBom)

$kept = [System.Collections.Generic.List[string]]::new($lines.Length)

foreach ($line in $lines) {

if ($line -match '^\{"timestamp":"(\d{4}-\d{2}-\d{2})T') {

$dateStr = $Matches[1]

$parsed = [datetime]::MinValue

if ([datetime]::TryParseExact($dateStr, 'yyyy-MM-dd', [System.Globalization.CultureInfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::None, [ref]$parsed)) {

if ($parsed -lt $cutoff) { continue }

}

}

$kept.Add($line)

}

if ($kept.Count -lt $lines.Length) {

$tmpPath = "$LogPath.tmp"; [System.IO.File]::WriteAllLines($tmpPath, $kept.ToArray(), $script:Lib_Utf8WithBom)

Move-Item -LiteralPath $tmpPath -Destination $LogPath -Force

}

} catch [System.Exception] { Write-Verbose ("Falha ao aplicar retencao do arquivo de log: {0}" -f $_.Exception.Message) }

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

try {
    if (-not $script:AutomationMutex.WaitOne(5000)) {
        $msg = "CONCORRENCIA DETECTADA: Ja existe um processo rodando para o ExecId $ExecId. Abortando para evitar corrupcao."
        if ([string]::IsNullOrWhiteSpace($LogPath)) {
            Write-Warning $msg
        } else {
            Write-AutomacaoLog -Message $msg -Level "ERRO" -ExecId $ExecId -LogPath $LogPath
        }
        throw $msg
    }
} catch [System.Threading.AbandonedMutexException] {
    if (-not [string]::IsNullOrWhiteSpace($LogPath)) {
        Write-AutomacaoLog -Message "Mutex anterior foi abandonado. Reciclando lock (Mutex: $mutexName)." -Level "WARN" -ExecId $ExecId -LogPath $LogPath
    }
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

Export-ModuleMember -Function Get-AutomacaoProjectRoot, New-ExecId, Write-AutomacaoLog, Get-ForwardedLogLevel, Get-AutomationExitStatus, Exit-AutomationWithCode, Get-AutomacaoLogPath, Invoke-LogRotation, Test-AutomationEnvironment, Test-AutomationPreFlight, Enter-AutomationLock, Exit-AutomationLock, Register-ExecutionTelemetry, Close-ExecutionTelemetry, Send-AutomacaoLogBroadcast


