# ==============================================================================
# ARQUIVO: Test-VbaHtmlConformidade.ps1
# DESCRICAO: Valida contratos de HTML/CSS em fluxos VBA de email Outlook.
# ==============================================================================

[CmdletBinding()]
param(
    [string]$BasePath = "C:\Automacoes",
    [switch]$FailOnWarnings
)

$ErrorActionPreference = "Stop"

function Get-FileTextCp1252 {
    param([string]$FilePath)

    $enc = [System.Text.Encoding]::GetEncoding(1252)
    return [System.IO.File]::ReadAllText($FilePath, $enc)
}

function Convert-ToRelativePath {
    param(
        [string]$Path,
        [string]$Root
    )

    $rootNorm = [System.IO.Path]::GetFullPath($Root)
    $pathNorm = [System.IO.Path]::GetFullPath($Path)

    if ($pathNorm.StartsWith($rootNorm, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $pathNorm.Substring($rootNorm.Length).TrimStart([char[]]@([char]'\', [char]'/' ))
    }

    return $Path
}

function New-Finding {
    param(
        [string]$File,
        [string]$Rule,
        [string]$Severity,
        [string]$Detail,
        [bool]$IsBlocking = $false
    )

    return [pscustomobject]@{
        File     = $File
        Rule     = $Rule
        Severity = $Severity
        Blocking = $IsBlocking
        Detail   = $Detail
    }
}

function Test-ContainsPattern {
    param(
        [string]$Content,
        [string]$Pattern
    )

    return [regex]::IsMatch($Content, $Pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
}

$targets = @(
    "_Shared/VBA/ClsEmailComposerService.cls",
    "_Shared/VBA/ClsOutlookAdapter.cls",
    "Montagem de Terceirizados/modEmailOutlook.bas",
    "Receitas Bloqueadas/modReceitasBloqueadas.bas",
    "Receitas Emitidas/modReceitasEmitidas.bas"
)

$findings = New-Object System.Collections.Generic.List[object]

foreach ($target in $targets) {
    $fullPath = Join-Path $BasePath $target
    if (-not (Test-Path -LiteralPath $fullPath)) {
        $findings.Add((New-Finding -File $target.Replace('\\', '/') -Rule "TARGET_FILE_MISSING" -Severity "WARN" -Detail "Arquivo alvo nao encontrado para validacao de HTML/CSS VBA."))
        continue
    }

    $text = Get-FileTextCp1252 -FilePath $fullPath
    $rel = Convert-ToRelativePath -Path $fullPath -Root $BasePath

    $hasHtmlSignals = (Test-ContainsPattern -Content $text -Pattern '<table|\.htmlBody\s*=|\.HTMLBody\s*=|ComposeHtmlBodyWithSignature')
    if (-not $hasHtmlSignals) {
        continue
    }

    $hasHtmlMarkup = (Test-ContainsPattern -Content $text -Pattern '<table|<tr|<td|style=')

    if ($hasHtmlMarkup) {
        if (-not (Test-ContainsPattern -Content $text -Pattern 'role=''presentation''|role="presentation"')) {
            $findings.Add((New-Finding -File $rel -Rule "ROLE_PRESENTATION_MISSING" -Severity "ERRO" -Detail "HTML de email sem role='presentation' nas tabelas de layout." -IsBlocking $true))
        }

        if (-not (Test-ContainsPattern -Content $text -Pattern 'mso-table-lspace:0pt') -or -not (Test-ContainsPattern -Content $text -Pattern 'mso-table-rspace:0pt')) {
            $findings.Add((New-Finding -File $rel -Rule "MSO_TABLE_SPACING_GUARD_MISSING" -Severity "WARN" -Detail "Fix de espaco para Outlook (mso-table-lspace/rspace) ausente."))
        }

        $hasEncoding = (Test-ContainsPattern -Content $text -Pattern 'HtmlEncodeText\s*\(|HtmlEncode\s*\(|SafeTextoHtml\s*\(')
        if (-not $hasEncoding) {
            $findings.Add((New-Finding -File $rel -Rule "HTML_ENCODING_HELPER_MISSING" -Severity "WARN" -Detail "Nao foi encontrado helper de encode HTML (HtmlEncode/HtmlEncodeText)."))
        }

        if ((Test-ContainsPattern -Content $text -Pattern 'linear-gradient|display\s*:\s*flex|display\s*:\s*grid|@media|position\s*:\s*fixed')) {
            $findings.Add((New-Finding -File $rel -Rule "OUTLOOK_UNSAFE_CSS" -Severity "WARN" -Detail "CSS potencialmente inseguro para Outlook detectado (gradient/flex/grid/@media/fixed)."))
        }

        if (Test-ContainsPattern -Content $text -Pattern '<style\b') {
            $findings.Add((New-Finding -File $rel -Rule "STYLE_TAG_IN_VBA_HTML" -Severity "WARN" -Detail "Tag <style> encontrada; para Outlook prefira inline CSS critico."))
        }

        if (-not (Test-ContainsPattern -Content $text -Pattern 'font-family\s*:\s*[^;]*(Calibri|Arial|sans-serif)')) {
            $findings.Add((New-Finding -File $rel -Rule "FONT_FALLBACK_NOT_FOUND" -Severity "WARN" -Detail "Nao foi encontrado fallback de fonte comum (Calibri/Arial/sans-serif)."))
        }
    }
}

# Checagens cross-file de contrato adapter/composer.
$adapterPath = Join-Path $BasePath "_Shared/VBA/ClsOutlookAdapter.cls"
$composerPath = Join-Path $BasePath "_Shared/VBA/ClsEmailComposerService.cls"

if ((Test-Path -LiteralPath $adapterPath) -and (Test-Path -LiteralPath $composerPath)) {
    $adapterText = Get-FileTextCp1252 -FilePath $adapterPath
    $composerText = Get-FileTextCp1252 -FilePath $composerPath

    if (-not (Test-ContainsPattern -Content $adapterText -Pattern 'ComposeHtmlBodyWithSignature\s*\(')) {
        $findings.Add((New-Finding -File "_Shared/VBA/ClsOutlookAdapter.cls" -Rule "COMPOSER_CALL_MISSING" -Severity "ERRO" -Detail "Adapter nao chama ComposeHtmlBodyWithSignature." -IsBlocking $true))
    }

    if (-not (Test-ContainsPattern -Content $composerText -Pattern 'Function\s+HtmlEncodeText\s*\(')) {
        $findings.Add((New-Finding -File "_Shared/VBA/ClsEmailComposerService.cls" -Rule "HTML_ENCODE_FUNCTION_MISSING" -Severity "ERRO" -Detail "Composer sem funcao HtmlEncodeText." -IsBlocking $true))
    }
}

$blockingFindings = @($findings | Where-Object { $_.Blocking })
$warningFindings = @($findings | Where-Object { -not $_.Blocking })

Write-Host "=== VALIDACAO HTML/CSS VBA OUTLOOK ==="
Write-Host ("Arquivos alvo: " + $targets.Count)
Write-Host ("Bloqueios: " + $blockingFindings.Count)
Write-Host ("Alertas : " + $warningFindings.Count)
Write-Host ""

if ($blockingFindings.Count -gt 0) {
    Write-Host "-- BLOQUEIOS --" -ForegroundColor Red
    $blockingFindings | Select-Object File, Rule, Detail | Format-Table -AutoSize | Out-Host
    Write-Host ""
}

if ($warningFindings.Count -gt 0) {
    Write-Host "-- ALERTAS --" -ForegroundColor Yellow
    $warningFindings | Select-Object File, Rule, Detail | Format-Table -AutoSize | Out-Host
    Write-Host ""
}

if ($blockingFindings.Count -gt 0) {
    exit 2
}

if ($FailOnWarnings -and $warningFindings.Count -gt 0) {
    exit 3
}

exit 0
