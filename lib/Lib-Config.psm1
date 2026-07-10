# ==============================================================================
# ARQUIVO: Lib-Config.psm1
# VERSAO : 1.0.0
# DESCRICAO: Biblioteca central para gestao de configuracoes e variaveis de ambiente.
#            Implementa cache de ambiente e fallbacks seguros.
# ==============================================================================

$ErrorActionPreference = "Stop"

# Identifica a raiz do repositorio no momento da importacao
try {
    $script:ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
    if ([string]::IsNullOrWhiteSpace($script:ProjectRoot)) { $script:ProjectRoot = "." }
} catch [System.Exception] {
    $script:ProjectRoot = "."
}

$script:EnvLoaded = $false

function ConvertFrom-EnvLine {
    <#
    .SYNOPSIS
        Parseia uma linha de .env em par chave/valor, removendo comentario inline.
    #>
    [CmdletBinding()]
    [OutputType([hashtable])]
    param([string]$Line)

    $trimmed = $Line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith("#")) { return $null }

    $parts = $trimmed -split '=', 2
    if ($parts.Count -ne 2) { return $null }

    $key = $parts[0].Trim()
    $value = $parts[1].Trim()
    # Remove comentario inline (ex.: "5511999999999   # Nome Legivel")
    $value = [regex]::Replace($value, '\s+#.*$', '').Trim()

    if (-not $key -or -not $value) { return $null }
    return @{ Key = $key; Value = $value }
}

function Import-HubEnv {
    [CmdletBinding()]
    param([switch]$Force)

    if ($script:EnvLoaded -and -not $Force) { return }

    $envPath = Join-Path $script:ProjectRoot ".env"
    if (Test-Path $envPath) {
        Get-Content $envPath | ForEach-Object {
            $parsed = ConvertFrom-EnvLine -Line $_
            if ($parsed) {
                [System.Environment]::SetEnvironmentVariable($parsed.Key, $parsed.Value, "Process")
            }
        }
        $script:EnvLoaded = $true
    }
}

function Get-HubConfig {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Key,
        [string]$Default = ""
    )

    Import-HubEnv
    $val = [System.Environment]::GetEnvironmentVariable($Key, "Process")
    if ([string]::IsNullOrWhiteSpace($val)) { return $Default }
    return $val
}

Export-ModuleMember -Function Get-HubConfig, Import-HubEnv

