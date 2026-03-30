param(
    [string]$RootPath = (Join-Path $PSScriptRoot ".."),
    [string[]]$Paths = @(),
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Test-ShouldSkipMarkdownFile {
    param(
        [string]$BasePath,
        [string]$FilePath
    )

    $relativePath = $FilePath
    if ($relativePath.StartsWith($BasePath, [System.StringComparison]::OrdinalIgnoreCase)) {
        $relativePath = $relativePath.Substring($BasePath.Length).TrimStart([char[]]@('\', '/'))
    }

    $normalizedRelativePath = $relativePath.Replace('/', '\')
    $skipPatterns = @(
        'node_modules\',
        '.git\',
        '.wwebjs_auth\',
        'Logs\',
        '.code-search\'
    )

    foreach ($skipPattern in $skipPatterns) {
        if ($normalizedRelativePath.IndexOf($skipPattern, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            return $true
        }
    }

    return $false
}

function Write-Utf8File {
    param(
        [string]$FilePath,
        [string]$Content
    )

    $directoryPath = Split-Path -Parent $FilePath
    if (-not [string]::IsNullOrWhiteSpace($directoryPath) -and -not (Test-Path -LiteralPath $directoryPath)) {
        New-Item -ItemType Directory -Force -Path $directoryPath | Out-Null
    }

    [System.IO.File]::WriteAllText($FilePath, $Content, $Utf8NoBom)
}

function Get-TargetMarkdownFiles {
    param(
        [string]$BasePath,
        [string[]]$SelectedPaths
    )

    if ($SelectedPaths.Count -gt 0) {
        $files = foreach ($selectedPath in $SelectedPaths) {
            if ([string]::IsNullOrWhiteSpace($selectedPath)) {
                continue
            }

            $resolvedPath = $selectedPath
            if (-not [System.IO.Path]::IsPathRooted($resolvedPath)) {
                $resolvedPath = Join-Path $BasePath $resolvedPath
            }

            if (Test-Path -LiteralPath $resolvedPath -PathType Leaf) {
                Resolve-Path -LiteralPath $resolvedPath | ForEach-Object { $_.Path }
            }
        }

        return @(
            $files |
            Where-Object { -not (Test-ShouldSkipMarkdownFile -BasePath $BasePath -FilePath $_) } |
            Sort-Object -Unique
        )
    }

    return @(
        Get-ChildItem -LiteralPath $BasePath -Recurse -File -Filter "*.md" |
        ForEach-Object { $_.FullName } |
        Where-Object { -not (Test-ShouldSkipMarkdownFile -BasePath $BasePath -FilePath $_) } |
        Sort-Object -Unique
    )
}

function ConvertTo-NormalizedMarkdownContent {
    param([string[]]$Lines)

    $updatedLines = New-Object System.Collections.Generic.List[string]
    $changes = 0

    for ($index = 0; $index -lt $Lines.Count; $index++) {
        $line = $Lines[$index]
        $updatedLine = $line

        if ($updatedLine -match '^(\d+)\.\s{2,}(.*)$') {
            $updatedLine = ("{0}. {1}" -f $matches[1], $matches[2])
        }

        if ($updatedLine -match '^_([^_].*[^_])_$') {
            $previousContentLine = ""
            for ($previousIndex = $updatedLines.Count - 1; $previousIndex -ge 0; $previousIndex--) {
                if (-not [string]::IsNullOrWhiteSpace($updatedLines[$previousIndex])) {
                    $previousContentLine = $updatedLines[$previousIndex]
                    break
                }
            }

            if ($previousContentLine -eq '---') {
                $updatedLine = $matches[1]
            }
        }

        if ($updatedLine -ne $line) {
            $changes++
        }

        $updatedLines.Add($updatedLine)
    }

    return [pscustomobject]@{
        Content = ($updatedLines -join "`r`n") + "`r`n"
        Changes = $changes
    }
}

$resolvedRoot = (Resolve-Path -LiteralPath $RootPath).Path
$targetFiles = Get-TargetMarkdownFiles -BasePath $resolvedRoot -SelectedPaths $Paths

if ($targetFiles.Count -eq 0) {
    Write-Host "[OK] Nenhum arquivo Markdown encontrado para corrigir."
    exit 0
}

$totalFilesChanged = 0
$totalLineChanges = 0

foreach ($filePath in $targetFiles) {
    $lines = Get-Content -LiteralPath $filePath
    $result = ConvertTo-NormalizedMarkdownContent -Lines $lines

    if ($result.Changes -le 0) {
        continue
    }

    $totalFilesChanged++
    $totalLineChanges += $result.Changes

    if ($DryRun) {
        Write-Host ("[DRY-RUN] {0} -> {1} ajuste(s)" -f $filePath, $result.Changes)
        continue
    }

    Write-Utf8File -FilePath $filePath -Content $result.Content
    Write-Host ("[FIXED] {0} -> {1} ajuste(s)" -f $filePath, $result.Changes)
}

if ($DryRun) {
    Write-Host ("[OK] Dry-run concluido. Arquivos com ajustes: {0} | Linhas ajustadas: {1}" -f $totalFilesChanged, $totalLineChanges)
    exit 0
}

Write-Host ("[OK] Correcao concluida. Arquivos alterados: {0} | Linhas ajustadas: {1}" -f $totalFilesChanged, $totalLineChanges)
exit 0
