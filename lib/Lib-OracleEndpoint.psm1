# ==============================================================================
# ARQUIVO: Lib-OracleEndpoint.psm1
# DESCRICAO: Endpoint do Oracle para o pre-flight: localiza o tnsnames.ora, resolve
#            alias TNS ou EZ Connect em host/porta e testa a porta TCP. Sem credenciais.
#            Saiu de Lib-Logging.psm1 (logging nao resolve rede nem le .env).
# ==============================================================================

$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot 'Lib-Config.psm1')

# ------------------------------------------------------------------------------
# Endpoint do Oracle para o pre-flight (alias do tnsnames.ora ou EZ Connect)
# ------------------------------------------------------------------------------

function Get-OracleTnsnamesPath {
    # Procura tnsnames.ora na ordem do cliente Oracle: TNS_ADMIN e depois ORACLE_CLIENT_PATH
    # (variavel de ambiente ou .env do projeto).
    [CmdletBinding()]
    param()

    $candidatos = @()
    if ($env:TNS_ADMIN) { $candidatos += $env:TNS_ADMIN }

    $clientePath = [System.Environment]::GetEnvironmentVariable("ORACLE_CLIENT_PATH", "Process")
    if ([string]::IsNullOrWhiteSpace($clientePath)) {
        $clientePath = Get-EnvFileValue -Key "ORACLE_CLIENT_PATH"
    }
    if (-not [string]::IsNullOrWhiteSpace($clientePath)) {
        $candidatos += (Join-Path $clientePath "network\admin")
    }

    foreach ($pasta in $candidatos) {
        $arquivo = Join-Path $pasta "tnsnames.ora"
        if (Test-Path -LiteralPath $arquivo) { return $arquivo }
    }
    return $null
}

function Resolve-OracleEndpoint {
    # Devolve Servidor e Porta para um alias do tnsnames.ora ou para EZ Connect (host:porta[/servico]
    # ou host/servico). Devolve $null quando nada resolve: alias sem ':' nem '/' que nao esta no
    # tnsnames.ora NAO vira host (antes virava e o pre-flight acusava 'Oracle Off' falso).
    # Nao le nem devolve credenciais.
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$ConnectString)

    $texto = $ConnectString.Trim()
    if ([string]::IsNullOrWhiteSpace($texto)) { return $null }

    $tns = Get-OracleTnsnamesPath
    if ($tns) {
        $conteudo = Get-Content -LiteralPath $tns -Raw
        $alias = [regex]::Escape($texto)
        # Aceita o alias com sufixo de dominio no tnsnames (DBPRD.WORLD casa DBPRD), como o
        # cliente Oracle faz com NAMES.DEFAULT_DOMAIN.
        $bloco = [regex]::Match($conteudo, "(?ims)^\s*$alias(\.[A-Za-z0-9_\-]+)*\s*=(?<corpo>.*?)(?=^\s*[A-Za-z0-9_.\-]+\s*=|\z)")
        if ($bloco.Success) {
            $corpo = $bloco.Groups['corpo'].Value
            $hostMatch = [regex]::Match($corpo, "(?i)HOST\s*=\s*([^\)\s]+)")
            $portaMatch = [regex]::Match($corpo, "(?i)PORT\s*=\s*(\d+)")
            if ($hostMatch.Success) {
                $porta = if ($portaMatch.Success) { [int]$portaMatch.Groups[1].Value } else { 1521 }
                return [pscustomobject]@{ Servidor = $hostMatch.Groups[1].Value; Porta = $porta; Origem = "TNS" }
            }
        }
    }

    if ($texto -notmatch '[:/]') { return $null }
    $ezConnect = [regex]::Match($texto, '^(//)?(?<host>[A-Za-z0-9.\-_]+)(:(?<porta>\d+))?(/[^/\s]*)?$')
    if ($ezConnect.Success) {
        $porta = if ($ezConnect.Groups['porta'].Success) { [int]$ezConnect.Groups['porta'].Value } else { 1521 }
        return [pscustomobject]@{ Servidor = $ezConnect.Groups['host'].Value; Porta = $porta; Origem = "EZConnect" }
    }
    return $null
}

function Test-OracleTcpEndpoint {
    # Abre uma conexao TCP com timeout. Ping (ICMP) nao serve: pode estar bloqueado mesmo com o banco no ar.
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$Servidor,
        [Parameter(Mandatory = $true)][int]$Porta,
        [int]$TimeoutMs = 3000
    )

    $cliente = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $cliente.BeginConnect($Servidor, $Porta, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMs)) { return $false }
        $cliente.EndConnect($async)
        return [bool]$cliente.Connected
    } catch [System.Net.Sockets.SocketException] {
        return $false
    } catch [System.ObjectDisposedException] {
        return $false
    } catch [System.ArgumentException] {
        return $false
    } finally {
        $cliente.Close()
    }
}

# ------------------------------------------------------------------------------

# Test-AutomationPreFlight

# ------------------------------------------------------------------------------

Export-ModuleMember -Function Get-OracleTnsnamesPath, Resolve-OracleEndpoint, Test-OracleTcpEndpoint
