# ==============================================================================
# ARQUIVO: run.ps1
# VERSÃO: 2.0 (MIGRADO - SEM EXCEL/VBA)
# DESCRIÇÃO: Automação nativa para Receitas Emitidas.
#            Extrai dados do Oracle via Python, gera HTML e envia via Outlook.
# ==============================================================================
[CmdletBinding()]
param([string]$ExecId = "")

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }

# Bibliotecas e Caminhos
$libLogging = Join-Path (Split-Path -Parent $ScriptDir) "lib\Lib-Logging.psm1"
$libEmail   = Join-Path (Split-Path -Parent $ScriptDir) "lib\Lib-Email.psm1"
$envPath    = Join-Path (Split-Path -Parent $ScriptDir) ".env"
$pythonExe  = Join-Path (Split-Path -Parent $ScriptDir) ".venv\Scripts\python.exe"

# Arquivos da Automação
$configPath = Join-Path $ScriptDir "receitas_config.json"
$extractPy  = Join-Path $ScriptDir "extract_oracle.py"
$generatePy = Join-Path $ScriptDir "generate_html_report.py"
$LogDir     = Join-Path $ScriptDir "Logs"

# Importa bibliotecas
if (Test-Path $libLogging) { Import-Module $libLogging -Force }
if (Test-Path $libEmail)   { Import-Module $libEmail -Force }

# ID de Execução e Log
if ([string]::IsNullOrWhiteSpace($ExecId)) {
    $ExecId = if (Get-Command New-ExecId -ErrorAction SilentlyContinue) { New-ExecId } else { (Get-Date -Format 'yyyyMMdd_HHmmss') }
}
$LogFile = if (Get-Command Get-AutomacaoLogPath -ErrorAction SilentlyContinue) { Get-AutomacaoLogPath -Slug "ReceitasEmitidas" -LogDir $LogDir } else { Join-Path $LogDir "ReceitasEmitidas.log" }

function Write-Log {
    param([string]$Msg, [string]$Lvl = "INFO")
    if (Get-Command Write-AutomacaoLog -ErrorAction SilentlyContinue) {
        Write-AutomacaoLog -Message $Msg -Level $Lvl -ExecId $ExecId -LogPath $LogFile
    } else {
        Write-Host "[$Lvl] [ExecId:$ExecId] $Msg"
    }
}

Write-Log "========================================================================================="
Write-Log "INICIO - Execucao Nativa Receitas Emitidas. ExecId=$ExecId"

try {
    # 1. Carregar Variáveis de Ambiente (.env)
    if (-not (Test-Path $envPath)) { throw "Arquivo .env nao encontrado na raiz do projeto." }
    Get-Content $envPath | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            $key, $value = $line -split '=', 2
            if ($key -and $value) { [System.Environment]::SetEnvironmentVariable($key.Trim(), $value.Trim(), "Process") }
        }
    }

    # 2. Extração de Dados
    Write-Log "Passo 1/3: Extraindo dados do Oracle..."
    & $pythonExe $extractPy $ExecId 2>&1 | ForEach-Object { Write-Log "Python-Extract: $_" }
    if ($LASTEXITCODE -ne 0) { throw "Falha na extracao de dados do Oracle." }

    # 3. Geração do HTML
    Write-Log "Passo 2/3: Gerando corpo do e-mail em HTML..."
    & $pythonExe $generatePy $ExecId 2>&1 | ForEach-Object { Write-Log "Python-HTML: $_" }
    if ($LASTEXITCODE -ne 0) { throw "Falha na geracao do HTML." }

    # 4. Carregar Configurações e Enviar E-mail
    Write-Log "Passo 3/3: Preparando envio de e-mail..."
    if (-not (Test-Path $configPath)) { throw "Configuracao receitas_config.json nao encontrada." }
    $config = Get-Content $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $htmlPath = Join-Path $ScriptDir "email_body_shadow_$ExecId.html"
    $tableHtml = Get-Content $htmlPath -Raw -Encoding UTF8
    
    # Monta o corpo: Introdução + Tabela (A assinatura será anexada pela biblioteca)
    $fullHtmlBody = @"
    <p>$($config.email.intro_text)</p>
    $tableHtml
"@

    # Tratamento de acentuação no Assunto (String nativa PS é UTF16, Outlook COM entende melhor se for direta)
    $subject = "$($config.email.subject_prefix) - $(Get-Date -Format 'dd/MM/yyyy')"
    
    if (Get-Command Send-OutlookEmail -ErrorAction SilentlyContinue) {
        $sent = Send-OutlookEmail -To $config.email.to -Subject $subject -HtmlBody $fullHtmlBody -ExecId $ExecId -LogPath $LogFile
        if (-not $sent) { throw "Falha no envio via Outlook." }
    } else {
        throw "Biblioteca de e-mail (Send-OutlookEmail) nao carregada."
    }

    Write-Log "FIM - Processo concluido com sucesso."
    Write-Log "========================================================================================="
    
    # Limpeza de arquivos temporários desta execução
    Remove-Item $htmlPath -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $ScriptDir "ReceitasEmitidas_shadow_$ExecId.json") -ErrorAction SilentlyContinue
    
} catch {
    Write-Log "ERRO FATAL: $_" -Lvl "ERRO"
    Write-Log "========================================================================================="
    exit 1
}
