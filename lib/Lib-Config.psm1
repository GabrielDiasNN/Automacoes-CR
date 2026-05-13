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

function Import-HubEnv {
    [CmdletBinding()]
    param([switch]$Force)

    if ($script:EnvLoaded -and -not $Force) { return }

    $envPath = Join-Path $script:ProjectRoot ".env"
    if (Test-Path $envPath) {
        Get-Content $envPath | ForEach-Object {
            $line = $_.Trim()
            if ($line -and -not $line.StartsWith("#")) {
                $parts = $line -split '=', 2
                if ($parts.Count -eq 2) {
                    $key = $parts[0].Trim()
                    $value = $parts[1].Trim()
                    if ($key -and $value) {
                        [System.Environment]::SetEnvironmentVariable($key, $value, "Process")
                    }
                }
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
