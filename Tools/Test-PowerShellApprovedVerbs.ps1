# cSpell:words funcao funcoes padrao substantivo verbos aprovados verificados encontrados pscustomobject isnullorwhitespace trimstart startswith additionalapprovedverbs ACMR ERRO pelo devem seguir deve existir
[CmdletBinding()]
param(
    [string]$RootPath = "",

    [string[]]$Paths = @(),
    [string[]]$AdditionalApprovedVerbs = @()
)

$ErrorActionPreference = "Stop"

function Get-RepositoryRoot {
    if (-not [string]::IsNullOrWhiteSpace($script:RootPath)) {
        return (Resolve-Path -LiteralPath $script:RootPath).Path
    }

    $gitRoot = ""
    try {
        $gitRoot = (git rev-parse --show-toplevel 2>$null)
    }
    catch [System.Exception] {
        $gitRoot = ""
    }

    if (-not [string]::IsNullOrWhiteSpace($gitRoot)) {
        return $gitRoot.Trim()
    }

    return (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
}

function Get-StagedPowerShellFiles {
    param([string]$RepositoryRoot)

    Push-Location $RepositoryRoot
    try {
        $staged = git diff --cached --name-only --diff-filter=ACMR -- '*.ps1' '*.psm1' '*.psd1'
    }
    finally {
        Pop-Location
    }

    $files = @()
    foreach ($item in $staged) {
        if ([string]::IsNullOrWhiteSpace($item)) {
            continue
        }

        $fullPath = Join-Path $RepositoryRoot $item.Trim()
        if (Test-Path -LiteralPath $fullPath) {
            $files += $fullPath
        }
    }

    return $files
}

function Get-ApprovedVerbSet {
    param([string[]]$ExtraVerbs)

    $set = New-Object System.Collections.Generic.HashSet[string]([System.StringComparer]::OrdinalIgnoreCase)

    foreach ($verbInfo in (Get-Verb)) {
        [void]$set.Add([string]$verbInfo.Verb)
    }

    foreach ($verb in $ExtraVerbs) {
        if (-not [string]::IsNullOrWhiteSpace($verb)) {
            [void]$set.Add($verb.Trim())
        }
    }

    return $set
}

function Get-FunctionDefinitions {
    param([string]$FilePath)

    $definitions = @()
    $lineNumber = 0

    foreach ($line in Get-Content -LiteralPath $FilePath) {
        $lineNumber++
        $trimmed = $line.TrimStart()

        if ($trimmed.StartsWith("#")) {
            continue
        }

        if ($trimmed -notmatch '^function\s+([^\s\(\{]+)\b') {
            continue
        }

        $definitions += [pscustomobject]@{
            FilePath     = $FilePath
            Line         = $lineNumber
            FunctionName = $matches[1]
        }
    }

    return $definitions
}

function Test-FunctionCompliance {
    param(
        [string]$FilePath,
        [System.Collections.Generic.HashSet[string]]$ApprovedVerbSet
    )

    $nameViolations = @()
    $verbViolations = @()
    $definitions = Get-FunctionDefinitions -FilePath $FilePath

    foreach ($definition in $definitions) {
        $functionName = [string]$definition.FunctionName

        if ($functionName -notmatch '^(?:(?:global|script|local|private):)?([A-Za-z][A-Za-z0-9]*)-([A-Za-z][A-Za-z0-9]*)$') {
            $nameViolations += [pscustomobject]@{
                FilePath     = $definition.FilePath
                Line         = $definition.Line
                FunctionName = $functionName
            }

            continue
        }

        $verb = $matches[1]
        $noun = $matches[2]

        if (-not $ApprovedVerbSet.Contains($verb)) {
            $verbViolations += [pscustomobject]@{
                FilePath     = $definition.FilePath
                Line         = $definition.Line
                FunctionName = ("{0}-{1}" -f $verb, $noun)
                InvalidVerb  = $verb
            }
        }
    }

    return [pscustomobject]@{
        NameViolations = $nameViolations
        VerbViolations = $verbViolations
    }
}

$repoRoot = Get-RepositoryRoot
$approvedVerbSet = Get-ApprovedVerbSet -ExtraVerbs $AdditionalApprovedVerbs

$targetFiles = @()
$allowedExtensions = @(".ps1", ".psm1", ".psd1")
if ($Paths.Count -gt 0) {
    foreach ($path in $Paths) {
        if ([string]::IsNullOrWhiteSpace($path)) {
            continue
        }

        $resolved = $path
        if (-not [System.IO.Path]::IsPathRooted($resolved)) {
            $resolved = Join-Path $repoRoot $resolved
        }

        if (Test-Path -LiteralPath $resolved -PathType Leaf) {
            $item = Get-Item -LiteralPath $resolved
            if ($allowedExtensions -contains $item.Extension.ToLowerInvariant()) {
                $targetFiles += $item.FullName
            }
        }
    }
}
else {
    $targetFiles = Get-StagedPowerShellFiles -RepositoryRoot $repoRoot
}

if ($targetFiles.Count -eq 0) {
    Write-Host "[OK] Nenhum arquivo PowerShell para validar."
    exit 0
}

$allNameViolations = @()
$allVerbViolations = @()
foreach ($file in ($targetFiles | Sort-Object -Unique)) {
    $result = Test-FunctionCompliance -FilePath $file -ApprovedVerbSet $approvedVerbSet
    $allNameViolations += @($result.NameViolations)
    $allVerbViolations += @($result.VerbViolations)
}

if ($allNameViolations.Count -eq 0 -and $allVerbViolations.Count -eq 0) {
    Write-Host "[OK] Nomes de funcao e verbos aprovados em todos os arquivos PowerShell verificados."
    exit 0
}

if ($allNameViolations.Count -gt 0) {
    Write-Host "[ERRO] Encontrados nomes de funcao fora do padrao Verbo-Substantivo:"
    foreach ($v in $allNameViolations) {
        $relative = $v.FilePath
        if ($relative.StartsWith($repoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            $relative = $relative.Substring($repoRoot.Length).TrimStart([char[]]@('\', '/'))
        }

        Write-Host (" - {0}:{1} -> {2}" -f $relative, $v.Line, $v.FunctionName)
    }
}

if ($allVerbViolations.Count -gt 0) {
    Write-Host "[ERRO] Encontrados nomes de funcao com verbo nao aprovado pelo PowerShell:"
    foreach ($v in $allVerbViolations) {
        $relative = $v.FilePath
        if ($relative.StartsWith($repoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            $relative = $relative.Substring($repoRoot.Length).TrimStart([char[]]@('\', '/'))
        }

        Write-Host (" - {0}:{1} -> {2} (verbo: {3})" -f $relative, $v.Line, $v.FunctionName, $v.InvalidVerb)
    }
}

Write-Host "Dica: nomes de funcao devem seguir Verbo-Substantivo e o verbo deve existir em Get-Verb."
exit 1

