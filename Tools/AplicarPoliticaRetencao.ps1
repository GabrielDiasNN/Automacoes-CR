[CmdletBinding()]
param(
    [string]$ExecId = "",
    [string]$RootPath = "",
    [switch]$DryRun,
    [int]$LogRetentionDays = 14,
    [int]$BackupRetentionDays = 30,
    [int]$TransientStateRetentionDays = 7,
    [int]$TestArtifactRetentionDays = 2
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ([string]::IsNullOrWhiteSpace($RootPath)) {
    $RootPath = Split-Path -Parent $PSScriptRoot
}

$resolvedRoot = (Resolve-Path -LiteralPath $RootPath).Path
$rootWithSeparator = $resolvedRoot.TrimEnd('\') + '\'
$now = Get-Date

$script:TrackedFiles = New-Object "System.Collections.Generic.HashSet[string]" ([System.StringComparer]::OrdinalIgnoreCase)
$script:Results = New-Object System.Collections.Generic.List[object]
$script:PreservePathRegexes = @(
    '(^|\\)\.git($|\\)',
    '(^|\\)\.venv($|\\)',
    '(^|\\)\.gemini($|\\)',
    '(^|\\)\.env$',
    '(^|\\)\.wwebjs_auth($|\\)'
)
$script:CategoryRules = @(
    @{
        Name = "Python Cache"
        Type = "DirectoryName"
        Names = @("__pycache__", ".pytest_cache", ".mypy_cache", "htmlcov")
        MinAgeDays = 0
        Recurse = $true
    },
    @{
        Name = "Python Coverage"
        Type = "FileName"
        Names = @(".coverage")
        MinAgeDays = 0
        Recurse = $true
    },
    @{
        Name = "Playwright Artifacts"
        Type = "DirectoryName"
        Names = @(".playwright-cli", ".playwright-mcp", "playwright-report", "test-results")
        MinAgeDays = 0
        Recurse = $true
    },
    @{
        Name = "Orchestrator E2E Artifacts"
        Type = "Pattern"
        RelativeDirectory = "Orchestrator\tests"
        IncludeFiles = @(
            "test-e2e-automacoes-*.db",
            "test-e2e-automacoes-*.db-shm",
            "test-e2e-automacoes-*.db-wal",
            "uvicorn-stdout-*.log",
            "uvicorn-stderr-*.log",
            "fix_tests*.py"
        )
        MinAgeDays = 0
    },
    @{
        Name = "Operational Logs"
        Type = "Pattern"
        RelativeDirectories = @("Logs", "Orchestrator\Logs", "Montagem de Terceirizados\Logs", "Receitas Bloqueadas\Logs", "Receitas Emitidas\Logs")
        IncludeFiles = @("*.log", "*.jsonl", "*.txt")
        MinAgeDays = $LogRetentionDays
    },
    @{
        Name = "Operational Backups"
        Type = "Pattern"
        RelativeDirectories = @("Backups", "Orchestrator\Backups")
        IncludeFiles = @("*")
        MinAgeDays = $BackupRetentionDays
    },
    @{
        Name = "Orchestrator Runtime Transients"
        Type = "Pattern"
        RelativeDirectory = "Orchestrator"
        IncludeFiles = @(
            "*.pid",
            "*.db-shm",
            "*.db-wal",
            "debug.log"
        )
        MinAgeDays = 0
        Recurse = $false
    },
    @{
        Name = "Automation Temporary State"
        Type = "Pattern"
        RelativeDirectories = @("Montagem de Terceirizados", "Receitas Bloqueadas", "Receitas Emitidas")
        IncludeFiles = @(
            "email_body.html",
            ".cache_erros.json",
            "delivery_state.json",
            "email_state.json",
            "receitas_state.json"
        )
        MinAgeDays = $TransientStateRetentionDays
    }
)

function Convert-ToRelativePath {
    param([string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    if ($fullPath.StartsWith($rootWithSeparator, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $fullPath.Substring($rootWithSeparator.Length)
    }

    return $fullPath
}

function Add-Result {
    param(
        [string]$Category,
        [string]$Path,
        [string]$Status,
        [string]$Reason
    )

    $script:Results.Add(
        [pscustomobject]@{
            Category = $Category
            Path     = Convert-ToRelativePath -Path $Path
            Status   = $Status
            Reason   = $Reason
        }
    ) | Out-Null
}

function Test-IsPreservedPath {
    param([string]$Path)

    $normalized = [System.IO.Path]::GetFullPath($Path).Replace('/', '\')
    foreach ($pattern in $script:PreservePathRegexes) {
        if ($normalized -match $pattern) {
            return $true
        }
    }

    return $false
}

function Initialize-TrackedFiles {
    $gitCommand = Get-Command git -ErrorAction SilentlyContinue
    if (-not $gitCommand) {
        return
    }

    $tracked = & git -C $resolvedRoot ls-files 2>$null
    if ($LASTEXITCODE -ne 0) {
        return
    }

    foreach ($relativePath in $tracked) {
        if ([string]::IsNullOrWhiteSpace($relativePath)) {
            continue
        }

        $absolutePath = [System.IO.Path]::GetFullPath((Join-Path $resolvedRoot $relativePath))
        $script:TrackedFiles.Add($absolutePath) | Out-Null
    }
}

function Test-IsTrackedPath {
    param([string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    if ($script:TrackedFiles.Contains($fullPath)) {
        return $true
    }

    $prefix = $fullPath.TrimEnd('\') + '\'
    foreach ($trackedFile in $script:TrackedFiles) {
        if ($trackedFile.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }

    return $false
}

function Test-IsWithinRoot {
    param([string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    return $fullPath.StartsWith($rootWithSeparator, [System.StringComparison]::OrdinalIgnoreCase) -or
        $fullPath.Equals($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)
}

function Get-ItemAgeDays {
    param([System.IO.FileSystemInfo]$Item)

    return ($now - $Item.LastWriteTime).TotalDays
}

function Test-OrchestratorRuntimeActive {
    $pidFiles = @(
        (Join-Path $resolvedRoot "Orchestrator\orchestrator.pid"),
        (Join-Path $resolvedRoot "Orchestrator\worker.pid")
    )

    foreach ($pidFile in $pidFiles) {
        if (-not (Test-Path -LiteralPath $pidFile -PathType Leaf)) {
            continue
        }

        try {
            $rawPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
            if ([string]::IsNullOrWhiteSpace($rawPid)) {
                continue
            }

            $pidValue = [int]$rawPid
            $process = Get-Process -Id $pidValue -ErrorAction Stop
            if ($null -ne $process) {
                return $true
            }
        }
        catch [System.Exception] {
            continue
        }
    }

    return $false
}

function Get-CandidateDirectoriesByName {
    param(
        [string[]]$Names
    )

    return @(
        Get-ChildItem -LiteralPath $resolvedRoot -Directory -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object {
            ($Names -contains $_.Name) -and
            -not (Test-IsPreservedPath -Path $_.FullName)
        } |
        Sort-Object FullName -Unique
    )
}

function Get-CandidateFilesByName {
    param(
        [string[]]$Names
    )

    return @(
        Get-ChildItem -LiteralPath $resolvedRoot -File -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object {
            ($Names -contains $_.Name) -and
            -not (Test-IsPreservedPath -Path $_.FullName)
        } |
        Sort-Object FullName -Unique
    )
}

function Get-CandidateItemsByPattern {
    param(
        [string[]]$RelativeDirectories,
        [string[]]$IncludeFiles,
        [bool]$Recurse = $true
    )

    $items = New-Object System.Collections.Generic.List[object]
    foreach ($relativeDirectory in $RelativeDirectories) {
        $directoryPath = Join-Path $resolvedRoot $relativeDirectory
        if (-not (Test-Path -LiteralPath $directoryPath -PathType Container)) {
            continue
        }

        foreach ($include in $IncludeFiles) {
            $getChildItemParams = @{
                LiteralPath   = $directoryPath
                File          = $true
                Filter        = $include
                Force         = $true
                ErrorAction   = "SilentlyContinue"
            }
            if ($Recurse) {
                $getChildItemParams.Recurse = $true
            }

            foreach ($item in (Get-ChildItem @getChildItemParams)) {
                if (Test-IsPreservedPath -Path $item.FullName) {
                    continue
                }
                $items.Add($item) | Out-Null
            }
        }
    }

    return @($items | Sort-Object FullName -Unique)
}

function Test-CategorySpecificSkip {
    param(
        [hashtable]$Rule,
        [System.IO.FileSystemInfo]$Item
    )

    if ($Rule.Name -eq "Orchestrator Runtime Transients") {
        if (Test-OrchestratorRuntimeActive) {
            return "Runtime do Orchestrator aparenta estar ativo."
        }
    }

    return $null
}

function Remove-CandidateItem {
    param(
        [hashtable]$Rule,
        [System.IO.FileSystemInfo]$Item
    )

    $fullPath = [System.IO.Path]::GetFullPath($Item.FullName)
    $category = [string]$Rule.Name

    if (-not (Test-IsWithinRoot -Path $fullPath)) {
        Add-Result -Category $category -Path $fullPath -Status "Pulado" -Reason "Caminho fora do repositório."
        return
    }

    if (Test-IsPreservedPath -Path $fullPath) {
        Add-Result -Category $category -Path $fullPath -Status "Preservado" -Reason "Caminho preservado por contrato."
        return
    }

    if (Test-IsTrackedPath -Path $fullPath) {
        Add-Result -Category $category -Path $fullPath -Status "Pulado" -Reason "Item rastreado pelo Git."
        return
    }

    $ageDays = Get-ItemAgeDays -Item $Item
    $minAgeDays = [double]$Rule.MinAgeDays
    if ($ageDays -lt $minAgeDays) {
        Add-Result -Category $category -Path $fullPath -Status "Preservado" -Reason ("Idade {0:N1}d abaixo da retenção mínima de {1}d." -f $ageDays, $minAgeDays)
        return
    }

    $categorySkipReason = Test-CategorySpecificSkip -Rule $Rule -Item $Item
    if ($categorySkipReason) {
        Add-Result -Category $category -Path $fullPath -Status "Pulado" -Reason $categorySkipReason
        return
    }

    if ($DryRun) {
        Add-Result -Category $category -Path $fullPath -Status "DryRun" -Reason "Candidato elegível para remoção."
        return
    }

    try {
        if ($Item.PSIsContainer) {
            Remove-Item -LiteralPath $fullPath -Recurse -Force -ErrorAction Stop
        } else {
            Remove-Item -LiteralPath $fullPath -Force -ErrorAction Stop
        }

        Add-Result -Category $category -Path $fullPath -Status "Removido" -Reason "Item removido com sucesso."
    }
    catch [System.Exception] {
        $message = $_.Exception.Message
        if (
            $message -match "being used by another process" -or
            $message -match "Access to the path .* is denied"
        ) {
            Add-Result -Category $category -Path $fullPath -Status "Pulado" -Reason ("Item bloqueado no momento da limpeza: {0}" -f $message)
            return
        }

        Add-Result -Category $category -Path $fullPath -Status "Erro" -Reason $message
    }
}

function Invoke-CleanupRule {
    param([hashtable]$Rule)

    $items = @()
    switch ($Rule.Type) {
        "DirectoryName" {
            $items = Get-CandidateDirectoriesByName -Names $Rule.Names
        }
        "FileName" {
            $items = Get-CandidateFilesByName -Names $Rule.Names
        }
        "Pattern" {
            [string[]]$relativeDirectories = @()
            if ($Rule.ContainsKey("RelativeDirectory")) {
                $relativeDirectories += [string]$Rule.RelativeDirectory
            }
            if ($Rule.ContainsKey("RelativeDirectories")) {
                foreach ($dir in $Rule.RelativeDirectories) {
                    $relativeDirectories += [string]$dir
                }
            }
            $recurse = $true
            if ($Rule.ContainsKey("Recurse")) {
                $recurse = [bool]$Rule.Recurse
            }
            $items = Get-CandidateItemsByPattern -RelativeDirectories $relativeDirectories -IncludeFiles $Rule.IncludeFiles -Recurse:$recurse
        }
        default {
            throw "Tipo de regra não suportado: $($Rule.Type)"
        }
    }

    foreach ($item in $items) {
        Remove-CandidateItem -Rule $Rule -Item $item
    }
}

function Write-ResultsSummary {
    Write-Host "=== LIMPEZA SEGURA DO REPOSITÓRIO ==="
    Write-Host ("Modo: " + $(if ($DryRun) { "DryRun" } else { "Execução real" }))
    Write-Host ("Raiz: " + $resolvedRoot)
    Write-Host ""

    if ($script:Results.Count -eq 0) {
        Write-Host "[OK] Nenhum candidato encontrado para a política atual."
        return
    }

    $summary = $script:Results |
        Group-Object Category, Status |
        Sort-Object Name |
        ForEach-Object {
            $parts = $_.Name -split ',\s*', 2
            [pscustomobject]@{
                Category = $parts[0]
                Status   = $parts[1]
                Count    = $_.Count
            }
        }

    $summary | Format-Table -AutoSize | Out-Host
    Write-Host ""

    $script:Results |
        Sort-Object Category, Status, Path |
        Select-Object Category, Status, Path, Reason |
        Format-Table -Wrap -AutoSize |
        Out-Host
}

Initialize-TrackedFiles

foreach ($rule in $script:CategoryRules) {
    Invoke-CleanupRule -Rule $rule
}

Write-ResultsSummary

$errorCount = @($script:Results | Where-Object { $_.Status -eq "Erro" }).Count
if ($errorCount -gt 0) {
    exit 1
}

exit 0
