#Requires -Version 5.1
<#
.SYNOPSIS
    Funcoes compartilhadas pelos hooks de .claude/hooks.

.NOTES
    Tools/Test-SourceEncoding.ps1 emite os achados via Write-Host e Out-Host,
    que escrevem no host e NAO no pipeline. Redirecionar com 2>&1 dentro do
    mesmo processo perde o detalhe. Por isso Invoke-EncodingCheck executa o
    verificador como processo filho, onde tudo converge para o stdout do
    processo e pode ser capturado integralmente.
#>

Set-StrictMode -Version Latest

function Get-HookPayload {
    <#
    .SYNOPSIS
        Le e desserializa o payload do hook (variavel de ambiente ou stdin).
    #>
    [CmdletBinding()]
    param()

    $raw = $null
    if (-not [string]::IsNullOrWhiteSpace($env:CLAUDE_TOOL_INPUT)) {
        $raw = $env:CLAUDE_TOOL_INPUT
    }
    elseif ([Console]::IsInputRedirected) {
        $raw = [Console]::In.ReadToEnd()
    }

    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $null
    }

    try {
        return $raw | ConvertFrom-Json
    }
    catch [System.Exception] {
        return $null
    }
}

function Get-HookProperty {
    <#
    .SYNOPSIS
        Le uma propriedade do payload, aceitando tanto o formato achatado
        (CLAUDE_TOOL_INPUT contem o proprio tool_input) quanto o aninhado.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        $Payload,

        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if ($null -eq $Payload) { return $null }

    $names = $Payload.PSObject.Properties.Name

    if ($names -contains $Name) {
        return $Payload.$Name
    }

    if ($names -contains 'tool_input') {
        $inner = $Payload.tool_input
        if ($null -ne $inner -and ($inner.PSObject.Properties.Name -contains $Name)) {
            return $inner.$Name
        }
    }

    return $null
}

function Get-RepositoryRoot {
    [CmdletBinding()]
    param()

    if (-not [string]::IsNullOrWhiteSpace($env:CLAUDE_PROJECT_DIR)) {
        return (Resolve-Path -LiteralPath $env:CLAUDE_PROJECT_DIR).Path
    }

    return (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
}

function Get-PowerShellHostPath {
    [CmdletBinding()]
    param()

    $pwsh = Get-Command -Name 'pwsh' -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($pwsh) { return $pwsh.Source }

    $windowsPowerShell = Get-Command -Name 'powershell' -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($windowsPowerShell) { return $windowsPowerShell.Source }

    return $null
}

function Invoke-EncodingCheck {
    <#
    .SYNOPSIS
        Roda Tools/Test-SourceEncoding.ps1 sobre os caminhos informados.

    .OUTPUTS
        PSCustomObject com ExitCode (int) e Output (string). ExitCode -1 indica
        que a verificacao nao pode ser executada e deve ser tratada como
        inconclusiva (nao bloqueante).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot,

        [Parameter(Mandatory = $true)]
        [string[]]$RelativePaths
    )

    $inconclusive = [pscustomobject]@{ ExitCode = -1; Output = '' }

    $checker = Join-Path $RepositoryRoot 'Tools\Test-SourceEncoding.ps1'
    if (-not (Test-Path -LiteralPath $checker -PathType Leaf)) {
        return $inconclusive
    }

    $hostPath = Get-PowerShellHostPath
    if (-not $hostPath) {
        return $inconclusive
    }

    # Os caminhos trafegam por arquivo, nunca interpolados na linha de comando:
    # nomes com aspas ou espacos nao viram injecao de argumento.
    $listFile = Join-Path ([System.IO.Path]::GetTempPath()) ("hook-encoding-{0}.txt" -f ([guid]::NewGuid().ToString('N')))
    try {
        Set-Content -LiteralPath $listFile -Value $RelativePaths -Encoding utf8

        $escape = { param([string]$Value) $Value.Replace("'", "''") }
        $script = "& '{0}' -RootPath '{1}' -Paths @(Get-Content -LiteralPath '{2}')" -f `
        (& $escape $checker), (& $escape $RepositoryRoot), (& $escape $listFile)

        $output = & $hostPath -NoProfile -NonInteractive -Command $script 2>&1
        $exitCode = $LASTEXITCODE

        return [pscustomobject]@{
            ExitCode = $exitCode
            Output   = (($output | Out-String).Trim())
        }
    }
    catch [System.Exception] {
        return $inconclusive
    }
    finally {
        Remove-Item -LiteralPath $listFile -Force -ErrorAction SilentlyContinue
    }
}

Export-ModuleMember -Function Get-HookPayload, Get-HookProperty, Get-RepositoryRoot, Invoke-EncodingCheck
