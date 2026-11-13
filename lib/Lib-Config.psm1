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

function Get-EnvFileValue {
    <#
    .SYNOPSIS
        Le UMA chave do .env do projeto sem carregar o arquivo no ambiente do processo.
        Devolve $null se o arquivo ou a chave nao existirem.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory = $true)][string]$Key)

    $envPath = Join-Path $script:ProjectRoot ".env"
    if (-not (Test-Path -LiteralPath $envPath)) { return $null }
    foreach ($linha in Get-Content -LiteralPath $envPath) {
        $parsed = ConvertFrom-EnvLine -Line $linha
        if ($parsed -and $parsed.Key -eq $Key) { return $parsed.Value.Trim('"') }
    }
    return $null
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

function Test-WhatsAppFlagEnabled {
    [CmdletBinding()]
    [OutputType([bool])]
    param($Section)

    if ($null -eq $Section) { return $true }

    $hasProp = $false
    $rawVal = $null
    if ($Section -is [System.Collections.IDictionary]) {
        if ($Section.Contains("enabled")) {
            $hasProp = $true
            $rawVal = $Section["enabled"]
        }
    }
    else {
        $prop = $Section.PSObject.Properties["enabled"]
        if ($null -ne $prop) {
            $hasProp = $true
            $rawVal = $prop.Value
        }
    }

    if (-not $hasProp -or $null -eq $rawVal) { return $true }
    if ($rawVal -is [bool]) { return $rawVal }
    if ($rawVal -is [int] -or $rawVal -is [long] -or $rawVal -is [double] -or $rawVal -is [decimal]) {
        return ($rawVal -ne 0)
    }

    $strVal = ([string]$rawVal).Trim().ToLowerInvariant()
    if ($strVal -in @("false", "0", "no")) { return $false }
    return $true
}

function Test-WhatsAppConfigEnabled {
    <#
    .SYNOPSIS
        Verifica se a configuracao de WhatsApp (`app.enabled` e `target.enabled`) esta habilitada.
    .DESCRIPTION
        Ausencia da secao ou da propriedade `enabled` equivale a habilitado ($true).
        Valor booleano `$false` ou strings "false", "0" e "no" (case-insensitive) desabilitam ($false).
    #>
    [CmdletBinding()]
    [OutputType([bool])]
    param(
        [Parameter(Mandatory = $false)]
        $Config
    )

    if ($null -eq $Config) { return $true }

    $appSection = $null
    $targetSection = $null
    if ($Config -is [System.Collections.IDictionary]) {
        if ($Config.Contains("app")) { $appSection = $Config["app"] }
        if ($Config.Contains("target")) { $targetSection = $Config["target"] }
    }
    else {
        $appProp = $Config.PSObject.Properties["app"]
        if ($null -ne $appProp) { $appSection = $appProp.Value }
        $targetProp = $Config.PSObject.Properties["target"]
        if ($null -ne $targetProp) { $targetSection = $targetProp.Value }
    }

    return (Test-WhatsAppFlagEnabled -Section $appSection) -and (Test-WhatsAppFlagEnabled -Section $targetSection)
}

Export-ModuleMember -Function Get-HubConfig, Get-EnvFileValue, Import-HubEnv, Resolve-WhatsAppTarget, Test-WhatsAppConfigEnabled

