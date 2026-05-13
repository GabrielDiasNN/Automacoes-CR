<#
.SYNOPSIS
    Orquestrador Ofical para Montagem de Terceirizados (Pure-Native).
.DESCRIPTION
    Este script coordena o ciclo de vida da automacao utilizando extracao direta do Oracle via Python.
    Nao utiliza mais dependencias de Excel/VBA (Migracao Concluida).
.NOTES
    Version: 2.1.0
    Skill: ai-native-development-standard, enterprise-local-automation-stack, automation-runtime-safety
    Contract: native-fetch-logic, ipc-file-payload, base64-bridge-logs, preflight-v1
    #>
    # {
    #   "name": "orchestrator-montagem-terceirizados",
    #   "version": "2.1.0",
    #   "skill": "powershell-automation-monitor",
    #   "description": "Use when orchestrating fiscal validation of outsourcing assembly orders."
    # }
    [CmdletBinding()]
param(
    [string]$ExecId = "",
    [switch]$EmailPreviewOnly,
    [string]$EmailToTest = "",
    [string]$EmailCcTest = ""
)

$ErrorActionPreference = "Stop"

# Configuracao Global de Encoding para Interoperabilidade
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }

# Bibliotecas e Caminhos
$projectRoot = Split-Path -Parent $ScriptDir
$libLogging  = Join-Path $projectRoot "lib\Lib-Logging.psm1"
$libEmail    = Join-Path $projectRoot "lib\Lib-Email.psm1"
$pythonExe   = Join-Path $projectRoot ".venv\Scripts\python.exe"

# Scripts
$extractPy  = Join-Path $ScriptDir "extract_oracle.py"
$validatePy = Join-Path $ScriptDir "validate_and_generate_html.py"
$CacheFile  = Join-Path $ScriptDir ".cache_erros.json"
$CacheTmp   = $CacheFile + ".tmp"
$LogDir     = Join-Path $ScriptDir "Logs"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }

Import-Module $libLogging -Force
Import-Module $libEmail   -Force

if ([string]::IsNullOrWhiteSpace($ExecId)) {
    $ExecId = if (Get-Command Register-ExecutionTelemetry -ErrorAction SilentlyContinue) {
        Register-ExecutionTelemetry -AutomationName "Montagem de Terceirizados"
    } elseif (Get-Command New-ExecId -ErrorAction SilentlyContinue) { New-ExecId } else { (Get-Date -Format 'yyyyMMdd_HHmmss') }
}
Enter-AutomationLock -ExecId $ExecId

$LogFile = Get-AutomacaoLogPath -Slug "Montagem_Terceirizados" -LogDir $LogDir

# Helper para Log com suporte a Base64 Interno (v5.0.0)
function Write-Log {
    param([string]$Msg, [string]$Lvl = "INFO")
    if ($Msg -match '[^\x00-\x7F]') {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Msg)
        $b64 = [System.Convert]::ToBase64String($bytes)
        Write-AutomacaoLog -Message "B64:$b64" -Level $Lvl -ExecId $ExecId -LogPath $LogFile
    } else {
        Write-AutomacaoLog -Message $Msg -Level $Lvl -ExecId $ExecId -LogPath $LogFile
    }
}

# --- BOOTSTRAP / PRE-FLIGHT ---
$pathsToCheck = @($pythonExe, $extractPy, $validatePy)

# Housekeeping: Limpa arquivos temporarios orfaos com mais de 24h
Get-ChildItem -Path $ScriptDir -Filter ".data_*.json" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-1) } | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $ScriptDir -Filter ".payload_*.json" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-1) } | Remove-Item -Force -ErrorAction SilentlyContinue

if (-not (Test-AutomationPreFlight -ExecId $ExecId -LogPath $LogFile -CheckOracle -CheckPaths $pathsToCheck)) {
    Write-Log "FALHA NO PRE-FLIGHT (Python/Oracle/Paths). Abortando execu$([char]0xE7)$([char]0xE3)o." -Lvl "ERRO"; exit 9
}

Write-Log "========================================================================================="
Write-Log "IN$([char]0xCD)CIO - Execu$([char]0xE7)$([char]0xE3)o Montagem Terceirizados (Pure-Native). ExecId=$ExecId"

$execStatus = "ERROR"
try {
    # Carregar Variaveis de Ambiente (.env)
    $envPath = Join-Path $projectRoot ".env"
    if (Test-Path $envPath) {
        Get-Content $envPath | ForEach-Object {
            $line = $_.Trim()
            if ($line -and -not $line.StartsWith("#")) {
                $key, $value = $line -split '=', 2
                if ($key -and $value) { [System.Environment]::SetEnvironmentVariable($key.Trim(), $value.Trim(), "Process") }
            }
        }
    }

    $dataFile = Join-Path $ScriptDir ".data_$ExecId.json"
    if (Test-Path $dataFile) { Remove-Item $dataFile -Force }

    # 1. Extra$([char]0xE7)$([char]0xE3)o Nativa (Pure-Python via Oracle)
    Write-Log "Fase 1: Executando extra$([char]0xE7)$([char]0xE3)o nativa direta do Oracle..."
    $nativeExtractInfo = New-Object System.Diagnostics.ProcessStartInfo
    $nativeExtractInfo.FileName = $pythonExe
    $nativeExtractInfo.Arguments = "`"$extractPy`" `"$ExecId`""
    $nativeExtractInfo.RedirectStandardOutput = $true 
    $nativeExtractInfo.RedirectStandardError = $true
    $nativeExtractInfo.UseShellExecute = $false
    $nativeExtractInfo.CreateNoWindow = $true
    $nativeExtractInfo.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    
    # Injetar variaveis do .env no processo filho
    $envVars = [System.Environment]::GetEnvironmentVariables("Process")
    foreach ($key in $envVars.Keys) {
        if (-not $nativeExtractInfo.Environment.ContainsKey($key)) {
            $nativeExtractInfo.Environment.Add($key, $envVars[$key])
        }
    }
    
    $nativeProc = [System.Diagnostics.Process]::Start($nativeExtractInfo)
    
    # Processa logs do Python em tempo real
    while (-not $nativeProc.HasExited) {
        $line = $nativeProc.StandardOutput.ReadLine()
        if ($line) { Write-Log $line }
        $err = $nativeProc.StandardError.ReadLine()
        if ($err) { Write-Log $err -Lvl "WARN" }
    }
    $nativeProc.WaitForExit()

    if ($nativeProc.ExitCode -ne 0 -or -not (Test-Path $dataFile)) {
        throw "Falha cr$([char]0xED)tica na extra$([char]0xE7)$([char]0xE3)o nativa (ExitCode: $($nativeProc.ExitCode)). Arquivo de dados n$([char]0xE3)o encontrado."
    }

    $fileSize = (Get-Item $dataFile).Length
    if ($fileSize -lt 10) {
        throw "Arquivo de dados $dataFile gerado mas parece vazio ou corrompido (Tamanho: $fileSize bytes)."
    }
    Write-Log "Dados extra$([char]0xED)dos com sucesso ($( [math]::round($fileSize/1kb, 2) ) KB)."

    # 2. Valida$([char]0xE7)$([char]0xE3)o e HTML
    Write-Log "Fase 2: Validando dados e gerando notifica$([char]0xE7)$([char]0xE3)o..."
    $payloadFile = Join-Path $ScriptDir ".payload_$ExecId.json"
    if (Test-Path $payloadFile) { Remove-Item $payloadFile -Force }

    $genInfo = New-Object System.Diagnostics.ProcessStartInfo
    $genInfo.FileName = $pythonExe
    $genInfo.Arguments = "`"$validatePy`" `"$ExecId`""
    $genInfo.RedirectStandardOutput = $true
    $genInfo.RedirectStandardError = $true
    $genInfo.UseShellExecute = $false
    $genInfo.CreateNoWindow = $true
    
    $genProcess = [System.Diagnostics.Process]::Start($genInfo)
    while (-not $genProcess.HasExited) {
        $line = $genProcess.StandardOutput.ReadLine()
        if ($line) { Write-Log $line }
        $err = $genProcess.StandardError.ReadLine()
        if ($err) { Write-Log $err -Lvl "WARN" }
    }
    $genProcess.WaitForExit()
    
    if ($genProcess.ExitCode -ne 0) { throw "Falha na valida$([char]0xE7)$([char]0xE3)o Python (ExitCode: $($genProcess.ExitCode))." }

    # 3. Envio do E-mail (Se houver payload)
    if (Test-Path $payloadFile) {
        $jsonOutput = Get-Content $payloadFile -Raw -Encoding UTF8
        $payload = $jsonOutput | ConvertFrom-Json
        $bytes = [System.Convert]::FromBase64String($payload.subject_b64)
        $subject = [System.Text.Encoding]::UTF8.GetString($bytes)
        $htmlOutput = $payload.html

        Write-Log "Notifica$([char]0xE7)$([char]0xE3)o gerada: $subject"
        
        # Carregar Configuracoes Oficiais (config.json)
        # 1. Carregar Destinatarios Oficiais (config.json)
        $configFile = Join-Path $ScriptDir "config.json"
        $config = if (Test-Path $configFile) { Get-Content $configFile -Raw | ConvertFrom-Json } else { $null }
        $officialTo = if ($config -and $config.email -and $config.email.to) { $config.email.to } else { "gabriel.dias@costaricamalhas.ind.br" }
        $officialCc = if ($config -and $config.email -and $config.email.cc) { $config.email.cc } else { "" }

        # 2. Verificar Modo Teste Global (Ativado via AtivarModoTeste.bat / Dashboard)
        $globalTestEmail = [Environment]::GetEnvironmentVariable("AUTOMACAO_TEST_EMAIL", "User")
        
        # 3. Decisao de Entrega
        $isTestMode = (-not [string]::IsNullOrWhiteSpace($EmailToTest)) -or (-not [string]::IsNullOrWhiteSpace($globalTestEmail))
        
        if ($isTestMode) {
            # MODO TESTE: Redirecionamento para sandbox (AtivarModoTeste ou param)
            $testTarget = if (-not [string]::IsNullOrWhiteSpace($EmailToTest)) { $EmailToTest } else { $globalTestEmail }
            $finalTo = if (-not [string]::IsNullOrWhiteSpace($testTarget)) { $testTarget } else { "gabriel.dias@costaricamalhas.ind.br" }
            
            Write-Log "MODO TESTE ATIVO: Redirecionando para $finalTo" -Lvl "WARN"
            $sent = Send-OutlookEmail -To $finalTo -Subject $subject -HtmlBody $htmlOutput -ExecId $ExecId -LogPath $LogFile -PreviewOnly:([bool]$EmailPreviewOnly)
        } else {
            # MODO OFICIAL: Uso estrito do config.json
            Write-Log "MODO OFICIAL ATIVO (config.json): Disparando para $officialTo"
            $sent = Send-OutlookEmail -To $officialTo -Cc $officialCc -Subject $subject -HtmlBody $htmlOutput -ExecId $ExecId -LogPath $LogFile -PreviewOnly:([bool]$EmailPreviewOnly)
        }

        if ($sent) {
            Write-Log "Confirmando compromisso de estado (Commit Success)..."
            if (Test-Path $CacheTmp) {
                Move-Item -Path $CacheTmp -Destination $CacheFile -Force
                Write-Log "Cache de erros consolidado: $CacheFile"
            }
        } else {
            Write-Log "Falha no envio de e-mail. O cache N$([char]0xC3)O ser$([char]0xE1) atualizado para garantir retentativa." -Lvl "WARN"
        }

        Remove-Item $payloadFile -Force
        if (Test-Path $dataFile) { Remove-Item $dataFile -Force }
    } else {
        Write-Log "Nenhuma diverg$([char]0xEA)ncia ou mudan$([char]0xE7)a de estado. Nenhuma notifica$([char]0xE7)$([char]0xE3)o enviada."
    }

    $execStatus = "SUCCESS"

} catch [System.Exception] {
    Write-Log "ERRO FATAL NA EXECUCAO NATIVA: $_" -Lvl "ERRO"; exit 1
} finally {
    # Limpeza rigorosa de arquivos temporarios de intercambio
    if ($ExecId) {
        $tempPatterns = ".data_$ExecId.json", ".payload_$ExecId.json"
        foreach ($p in $tempPatterns) {
            $f = Join-Path $ScriptDir $p
            if (Test-Path $f) { Remove-Item $f -Force -ErrorAction SilentlyContinue }
        }
    }
    # Limpeza de cache temporario orfao (se nao foi consolidado)
    if (Test-Path $CacheTmp) { Remove-Item $CacheTmp -Force -ErrorAction SilentlyContinue }

    if (Get-Command Close-ExecutionTelemetry -ErrorAction SilentlyContinue) {
        Close-ExecutionTelemetry -ExecId $ExecId -Status $execStatus -LogPath $LogFile
    }

    Write-Log "FIM - Processo finalizado."
    Exit-AutomationLock
}

<#
## Gestao de Contexto (AI-Native) - Atualizado em 13/05/2026
- Estado: Estabilizado v2.1.0 (v5.3.0 Telemetry Sync).
- Governanca: Implementada telemetria nativa TEL_ para Dashboard.
- Resiliencia: Sincronia total de ciclo de vida (Start/End).
#>
