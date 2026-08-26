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

function Resolve-WhatsAppTarget {
    <#
    .SYNOPSIS
        Resolve o destino real de um envio WhatsApp a partir do `target` de um whatsapp-config.json.
    .DESCRIPTION
        Quando o config declara `contactIdEnv`, o `contactId`/`contactPhone` do JSON e' apenas
        placeholder de schema (todo config do hub que usa contactIdEnv usa o mesmo placeholder
        generico "550000000000...") — nunca um destino real. Falha cedo se a variavel de
        ambiente nao estiver definida, em vez de enviar silenciosamente para o placeholder.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory = $true)]
        $Target,
        [string]$ConfigPath = ""
    )

    $placeholder = if ($Target.contactId) { $Target.contactId } else { $Target.contactPhone }

    if ($Target.contactIdEnv) {
        $envTarget = [Environment]::GetEnvironmentVariable([string]$Target.contactIdEnv, "Process")
        if ([string]::IsNullOrWhiteSpace($envTarget)) {
            $origem = if ($ConfigPath) { " ($ConfigPath)" } else { "" }
            throw "Destino do WhatsApp ausente: variavel de ambiente '$($Target.contactIdEnv)'$origem nao esta definida ou esta vazia. O contactId do config e apenas placeholder de schema, nunca um destino real."
        }
        return $envTarget
    }

    if ([string]::IsNullOrWhiteSpace($placeholder)) {
        $origem = if ($ConfigPath) { " ($ConfigPath)" } else { "" }
        throw "Destino do WhatsApp ausente: 'target' $origem nao declara contactId, contactPhone nem contactIdEnv."
    }

    return $placeholder
}

Export-ModuleMember -Function Get-HubConfig, Import-HubEnv, Resolve-WhatsAppTarget

