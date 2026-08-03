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

    return Invoke-GovernedScript `
        -ScriptPath $checker `
        -RootParameterName 'RootPath' `
        -RepositoryRoot $RepositoryRoot `
        -RelativePaths $RelativePaths
}

function Invoke-GovernanceGate {
    <#
    .SYNOPSIS
        Roda Tools/ValidarAutomacoes.ps1 -OnlyGovernance em modo direcionado.

    .DESCRIPTION
        Sem -Paths o script cai em full_scan (~171 s, medido), inviavel em hook.
        Com -Paths ele roda os 14 checks apenas sobre os alvos informados: ~6 s
        sem Python e ~18 s com dois .py (o mypy domina o custo).

    .OUTPUTS
        Mesmo contrato de Invoke-EncodingCheck: ExitCode (-1 = inconclusivo,
        nao bloqueante) e Output.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot,

        [Parameter(Mandatory = $true)]
        [string[]]$RelativePaths
    )

    $gate = Join-Path $RepositoryRoot 'Tools\ValidarAutomacoes.ps1'
    if (-not (Test-Path -LiteralPath $gate -PathType Leaf)) {
        return [pscustomobject]@{ ExitCode = -1; Output = '' }
    }

    return Invoke-GovernedScript `
        -ScriptPath $gate `
        -RootParameterName 'BasePath' `
        -RepositoryRoot $RepositoryRoot `
        -RelativePaths $RelativePaths `
        -ExtraArguments '-OnlyGovernance'
}

function Select-FailureLines {
    <#
    .SYNOPSIS
        Reduz a saida de um gate as linhas que descrevem falha.

    .DESCRIPTION
        O gate emite 60+ linhas de [OK] mesmo quando reprova. Devolver tudo ao
        agente gasta contexto sem informar. Esta funcao mantem cada linha de
        erro e as linhas de detalhe indentadas que a seguem.

        Se nenhum marcador de falha for reconhecido, devolve a saida integral —
        e melhor pecar por excesso do que esconder o motivo da reprovacao.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Output,

        [int]$ContextLines = 3
    )

    if ([string]::IsNullOrWhiteSpace($Output)) {
        return ''
    }

    $lines = $Output -split "`r?`n"
    $keep = New-Object 'System.Collections.Generic.HashSet[int]'

    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -notmatch '\[(ERRO|FALHA|AVISO)') { continue }

        [void]$keep.Add($i)

        # Detalhe do achado vem indentado logo abaixo da linha de erro.
        for ($j = $i + 1; $j -lt [Math]::Min($i + 1 + $ContextLines, $lines.Count); $j++) {
            if ($lines[$j] -match '^\s+\S' -or $lines[$j] -match '\[(ERRO|FALHA)') {
                [void]$keep.Add($j)
            }
            else {
                break
            }
        }
    }

    if ($keep.Count -eq 0) {
        return $Output
    }

    $selected = @($keep) | Sort-Object | ForEach-Object { $lines[$_] }
    return ($selected -join [Environment]::NewLine)
}

function Invoke-GovernedScript {
    <#
    .SYNOPSIS
        Executa um script de Tools/ como processo filho e captura tudo.

    .DESCRIPTION
        Write-Host e Out-Host escrevem no host, nao no pipeline: redirecionar
        com 2>&1 dentro do mesmo processo perde o detalhe dos achados. Como
        processo filho, tudo converge para o stdout e pode ser lido.

        Os caminhos trafegam por arquivo, nunca interpolados na linha de
        comando: nome com aspas ou espaco nao vira injecao de argumento.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,

        [Parameter(Mandatory = $true)]
        [string]$RootParameterName,

        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot,

        [Parameter(Mandatory = $true)]
        [string[]]$RelativePaths,

        [string]$ExtraArguments = ''
    )

    $inconclusive = [pscustomobject]@{ ExitCode = -1; Output = '' }

    $hostPath = Get-PowerShellHostPath
    if (-not $hostPath) {
        return $inconclusive
    }

    $listFile = Join-Path ([System.IO.Path]::GetTempPath()) ("hook-paths-{0}.txt" -f ([guid]::NewGuid().ToString('N')))
    try {
        Set-Content -LiteralPath $listFile -Value $RelativePaths -Encoding utf8

        $escape = { param([string]$Value) $Value.Replace("'", "''") }
        $script = "& '{0}' -{1} '{2}' {3} -Paths @(Get-Content -LiteralPath '{4}')" -f `
        (& $escape $ScriptPath), $RootParameterName, (& $escape $RepositoryRoot), `
            $ExtraArguments, (& $escape $listFile)

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

Export-ModuleMember -Function Get-HookPayload, Get-HookProperty, Get-RepositoryRoot, Invoke-EncodingCheck, Invoke-GovernanceGate, Select-FailureLines
