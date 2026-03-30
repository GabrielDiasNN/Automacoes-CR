param(
    [string]$RootPath = (Join-Path $PSScriptRoot ".."),
    [string[]]$WorkbookPaths = @()
)

$ErrorActionPreference = "Stop"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Log {
    param(
        [string]$Level,
        [string]$Message
    )

    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] [$Level] $Message"
    Write-Host $line
    Write-Utf8Line -FilePath (Join-Path $RootPath "Audit\vba\sync-modules.log") -Line $line
}

function Write-Utf8Line {
    param(
        [string]$FilePath,
        [string]$Line
    )

    $dir = Split-Path -Parent $FilePath
    if ($dir) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }

    $sw = New-Object System.IO.StreamWriter($FilePath, $true, $Utf8NoBom)
    try {
        $sw.WriteLine($Line)
        $sw.Flush()
    }
    finally {
        $sw.Close()
        $sw.Dispose()
    }
}

function Remove-ComObjectReference {
    param([object]$Obj)

    if ($null -eq $Obj) {
        return
    }

    try {
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($Obj)
    }
    catch {}
}

function Get-VbaModulesFromFolder {
    param([string]$FolderPath)

    $basFiles = Get-ChildItem -LiteralPath $FolderPath -File -Filter "*.bas"
    $clsFiles = Get-ChildItem -LiteralPath $FolderPath -File -Filter "*.cls"
    return @(@($basFiles) + @($clsFiles))
}

$resolvedRoot = (Resolve-Path -LiteralPath $RootPath).Path

if ($WorkbookPaths.Count -eq 0) {
    $WorkbookPaths = @(
        (Join-Path $resolvedRoot "Montagem de Terceirizados\Validador_Notas_Montagem.xlsm"),
        (Join-Path $resolvedRoot "Receitas Bloqueadas\Receitas Bloqueadas.xlsm"),
        (Join-Path $resolvedRoot "Receitas Emitidas\Controle de Receitas Emitidas.xlsm")
    )
}

$excel = $null

try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.ScreenUpdating = $false
    $excel.EnableEvents = $false
    $excel.AskToUpdateLinks = $false
}
catch {
    Write-Log -Level "ERROR" -Message "Failed to start Excel.Application: $_"
    exit 1
}

foreach ($workbookPath in $WorkbookPaths) {
    if (-not (Test-Path -LiteralPath $workbookPath)) {
        Write-Log -Level "ERROR" -Message "Workbook not found: $workbookPath"
        continue
    }

    $moduleFolder = Split-Path -Parent $workbookPath
    $modules = Get-VbaModulesFromFolder -FolderPath $moduleFolder
    $moduleNameSet = @{}
    foreach ($moduleFile in $modules) {
        $moduleName = [System.IO.Path]::GetFileNameWithoutExtension($moduleFile.Name)
        $moduleNameSet[$moduleName] = $true
    }

    if ($modules.Count -eq 0) {
        Write-Log -Level "WARN" -Message "No .bas/.cls files found in folder: $moduleFolder"
        continue
    }

    Write-Log -Level "INFO" -Message "Syncing modules for $workbookPath"

    $wb = $null
    try {
        $wb = $excel.Workbooks.Open($workbookPath, 0, $false)
        $vbProject = $wb.VBProject
        $vbComponents = $vbProject.VBComponents

        $existingMap = @{}
        foreach ($component in $vbComponents) {
            $existingMap[$component.Name] = $component
        }

        $toRemove = @()
        foreach ($component in $vbComponents) {
            if ($component.Type -eq 1 -or $component.Type -eq 2 -or $component.Type -eq 3) {
                if (-not $moduleNameSet.ContainsKey($component.Name)) {
                    $toRemove += $component
                }
            }
        }

        foreach ($component in $toRemove) {
            try {
                $vbComponents.Remove($component)
                Write-Log -Level "INFO" -Message ("Removed orphan module: {0}" -f $component.Name)
            }
            catch {
                Write-Log -Level "WARN" -Message ("Failed to remove orphan module {0}: {1}" -f $component.Name, $_)
            }
        }

        foreach ($moduleFile in $modules) {
            $moduleName = [System.IO.Path]::GetFileNameWithoutExtension($moduleFile.Name)

            if ($existingMap.ContainsKey($moduleName)) {
                $existingComponent = $existingMap[$moduleName]
                if ($existingComponent.Type -eq 100) {
                    Write-Log -Level "WARN" -Message "Skipping document module: $moduleName"
                    continue
                }

                try {
                    $vbComponents.Remove($existingComponent)
                    Write-Log -Level "INFO" -Message "Removed existing module: $moduleName"
                }
                catch {
                    Write-Log -Level "WARN" -Message ("Failed to remove module {0}: {1}" -f $moduleName, $_)
                }
            }

            try {
                if ($moduleFile.Extension -ieq ".cls") {
                    $newComponent = $vbComponents.Add(2)
                    $newComponent.Name = $moduleName

                    $rawContent = Get-Content -LiteralPath $moduleFile.FullName -Raw
                    $lines = $rawContent -split "`r?`n"
                    $filtered = @()
                    foreach ($line in $lines) {
                        if ($line -match '^\s*VERSION\s') { continue }
                        if ($line -match '^\s*BEGIN\s*$') { continue }
                        if ($line -match '^\s*END\s*$') { continue }
                        if ($line -match '^\s*Attribute\s+VB_Name\b') { continue }
                        $filtered += $line
                    }

                    $cleanContent = ($filtered -join "`r`n").Trim()
                    if ($cleanContent.Length -gt 0) {
                        $newComponent.CodeModule.AddFromString($cleanContent)
                    }

                    Write-Log -Level "INFO" -Message "Imported class module: $moduleName"
                }
                else {
                    $null = $vbComponents.Import($moduleFile.FullName)
                    Write-Log -Level "INFO" -Message "Imported module: $moduleName"
                }
            }
            catch {
                Write-Log -Level "ERROR" -Message ("Failed to import module {0}: {1}" -f $moduleName, $_)
            }
        }

        $wb.Save()
        Write-Log -Level "INFO" -Message "Workbook saved: $workbookPath"
    }
    catch {
        Write-Log -Level "ERROR" -Message ("Failed to sync {0}: {1}" -f $workbookPath, $_)
    }
    finally {
        if ($wb) {
            try { $wb.Close($false) | Out-Null } catch {}
            Remove-ComObjectReference -Obj $wb
        }
    }
}

try {
    if ($excel) {
        $excel.Quit()
    }
}
catch {}
finally {
    Remove-ComObjectReference -Obj $excel
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
}

Write-Log -Level "INFO" -Message "VBA sync completed."
