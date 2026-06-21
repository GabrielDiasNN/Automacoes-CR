[CmdletBinding()]
param(
    [string]$RootPath = ".",
    [string[]]$Paths = @()
)

$ErrorActionPreference = "Stop"

$script:Utf8Strict = New-Object System.Text.UTF8Encoding($false, $true)
$script:Utf8NoBomExtensions = @(
    ".md",
    ".py",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".json",
    ".txt",
    ".sql",
    ".html",
    ".css"
)
$script:PowerShellExtensions = @(
    ".ps1",
    ".psm1"
)
$script:SkipPathFragments = @(
    "\.git\",
    "\.venv\",
    "\node_modules\",
    "\Logs\",
    "\.wwebjs_auth\",
    "\.code-search\",
    # Arquivos de estado runtime gerados pelo Orchestrator (ignorados pelo .gitignore)
    "email_state.json",
    "receitas_state.json",
    "delivery_state.json"
)

function Convert-ToRelativePath {
    param(
        [string]$Path,
        [string]$Root
    )

    $rootNorm = [System.IO.Path]::GetFullPath($Root)
    $pathNorm = [System.IO.Path]::GetFullPath($Path)

    if ($pathNorm.StartsWith($rootNorm, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $pathNorm.Substring($rootNorm.Length).TrimStart([char[]]@('\', '/'))
    }

    return $Path
}

function Test-ShouldSkipFile {
    param([string]$FilePath)

    $normalized = $FilePath.Replace('/', '\')
    foreach ($fragment in $script:SkipPathFragments) {
        if ($normalized.IndexOf($fragment, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            return $true
        }
    }

    return $false
}

function Test-HasUtf8Bom {
    param([byte[]]$Bytes)

    return $Bytes.Length -ge 3 -and $Bytes[0] -eq 0xEF -and $Bytes[1] -eq 0xBB -and $Bytes[2] -eq 0xBF
}

function Get-Utf8TextStrict {
    param([byte[]]$Bytes)

    $offset = 0
    if (Test-HasUtf8Bom -Bytes $Bytes) {
        $offset = 3
    }

    return $script:Utf8Strict.GetString($Bytes, $offset, $Bytes.Length - $offset)
}

function New-Finding {
    param(
        [string]$File,
        [string]$Rule,
        [string]$Detail
    )

    return [pscustomobject]@{
        File   = $File
        Rule   = $Rule
        Detail = $Detail
    }
}

function Test-ContainsMojibake {
    param([string]$Content)

    $normalizedContent = [regex]::Replace($Content, '(?s)```.*?```', '')
    $normalizedContent = [regex]::Replace($normalizedContent, '`[^`]*`', '')

    $c3 = [string][char]0x00C3
    $c2Space = [string]([char]0x00C2) + " "
    $e2euro = [string]([char]0x00E2) + [char]0x20AC

    if ($normalizedContent -match ([regex]::Escape($c3) + '[\x80-\xBF]')) {
        return $true
    }

    if ($normalizedContent.Contains($c2Space)) {
        return $true
    }

    if ($normalizedContent.Contains($e2euro)) {
        return $true
    }

    return $false
}

function Test-SourceFileEncoding {
    param(
        [string]$FilePath,
        [string]$RepoRoot
    )

    $findings = @()
    $relativePath = Convert-ToRelativePath -Path $FilePath -Root $RepoRoot
    $extension = [System.IO.Path]::GetExtension($FilePath).ToLowerInvariant()
    $bytes = [System.IO.File]::ReadAllBytes($FilePath)
    $hasBom = Test-HasUtf8Bom -Bytes $bytes

    try {
        $content = Get-Utf8TextStrict -Bytes $bytes
    }
    catch [System.Exception] {
        $findings += New-Finding -File $relativePath -Rule "UTF8_INVALID" -Detail "Arquivo nao esta em UTF-8 valido."
        return $findings
    }

    if ($script:PowerShellExtensions -contains $extension) {
        if (-not $hasBom) {
            $detail = if ($extension -eq ".psm1") {
                "Modulo PowerShell deve usar UTF-8 with BOM."
            } else {
                "Arquivo PowerShell deve usar UTF-8 with BOM."
            }

            $findings += New-Finding -File $relativePath -Rule "POWERSHELL_BOM_MISSING" -Detail $detail
        }
    }

    if ($script:Utf8NoBomExtensions -contains $extension) {
        if ($hasBom) {
            $findings += New-Finding -File $relativePath -Rule "UTF8_BOM_FORBIDDEN" -Detail ("Arquivo {0} deve usar UTF-8 sem BOM." -f $extension)
        }
    }

    if ($extension -eq ".md") {
        if ($content -match [char]0xFFFD) {
            $findings += New-Finding -File $relativePath -Rule "MARKDOWN_REPLACEMENT_CHAR_DETECTED" -Detail "Arquivo Markdown contem caractere de substituicao Unicode, indicando corrupcao de encoding."
        }

        if (Test-ContainsMojibake -Content $content) {
            $findings += New-Finding -File $relativePath -Rule "MARKDOWN_MOJIBAKE_DETECTED" -Detail "Arquivo Markdown contem sequencias tipicas de mojibake; revisar acentuacao e origem do encoding."
        }
    }

    return $findings
}

$resolvedRoot = (Resolve-Path -LiteralPath $RootPath).Path
$targetFiles = @()

if ($Paths.Count -gt 0) {
    foreach ($p in $Paths) {
        $p = $p.Trim('"')
        $fullPath = Join-Path $resolvedRoot $p
        if (Test-Path -LiteralPath $fullPath -PathType Leaf) {
            $fileInfo = Get-Item -LiteralPath $fullPath
            if ($fileInfo.Extension -in ($script:PowerShellExtensions + $script:Utf8NoBomExtensions) -and -not (Test-ShouldSkipFile -FilePath $fileInfo.FullName)) {
                $targetFiles += $fileInfo
            }
        }
    }
} else {
    $targetFiles = @(
        Get-ChildItem -LiteralPath $resolvedRoot -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Extension -in ($script:PowerShellExtensions + $script:Utf8NoBomExtensions) -and
            -not (Test-ShouldSkipFile -FilePath $_.FullName)
        } |
        Sort-Object FullName
    )
}

$findings = @()
foreach ($file in $targetFiles) {
    $findings += @(Test-SourceFileEncoding -FilePath $file.FullName -RepoRoot $resolvedRoot)
}

Write-Host "=== GOVERNANCA DE ENCODING ==="
Write-Host ("Arquivos analisados: " + $targetFiles.Count)
Write-Host ("Erros: " + $findings.Count)
Write-Host ""

if ($findings.Count -eq 0) {
    Write-Host "[OK] Encoding de fontes e documentacao em conformidade."
    exit 0
}

$findings |
Sort-Object File, Rule, Detail |
Select-Object File, Rule, Detail |
Format-Table -Wrap -AutoSize |
Out-Host

exit 2
