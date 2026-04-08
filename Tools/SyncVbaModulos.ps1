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

function New-CrlfTempCopy {
    param([string]$SourcePath)

    $tempPath = Join-Path $env:TEMP ("{0}_{1}{2}" -f [System.IO.Path]::GetFileNameWithoutExtension($SourcePath), [Guid]::NewGuid().ToString("N"), [System.IO.Path]::GetExtension($SourcePath))
    $bytes = [System.IO.File]::ReadAllBytes($SourcePath)
    $normalized = New-Object System.Collections.Generic.List[byte]

    for ($i = 0; $i -lt $bytes.Length; $i++) {
        $byte = $bytes[$i]
        if ($byte -eq 10) {
            if ($i -eq 0 -or $bytes[$i - 1] -ne 13) {
                $normalized.Add(13)
            }
            $normalized.Add(10)
        }
        else {
            $normalized.Add($byte)
        }
    }

    [System.IO.File]::WriteAllBytes($tempPath, $normalized.ToArray())
    return $tempPath
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
            $expectedType = if ($moduleFile.Extension -ieq ".cls") { 2 } else { 1 }
            $tempImportPath = $null
            $importPath = $moduleFile.FullName

            if ($moduleName.Length -gt 31) {
                Write-Log -Level "ERROR" -Message ("Skipping module with invalid VBA name length (>31): {0}" -f $moduleName)
                continue
            }

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
                    $tempImportPath = New-CrlfTempCopy -SourcePath $moduleFile.FullName
                    $importPath = $tempImportPath
                }

                $importedComponent = $vbComponents.Import($importPath)
                if ($null -eq $importedComponent) {
                    Write-Log -Level "ERROR" -Message ("Import returned null for module: {0}" -f $moduleName)
                    continue
                }

                if ([int]$importedComponent.Type -ne $expectedType) {
                    try { $vbComponents.Remove($importedComponent) } catch {}
                    Write-Log -Level "ERROR" -Message ("Imported module '{0}' with wrong type={1} (expected {2})." -f $moduleName, [int]$importedComponent.Type, $expectedType)
                    continue
                }

                if ($importedComponent.Name -ne $moduleName) {
                    try {
                        $importedComponent.Name = $moduleName
                        Write-Log -Level "WARN" -Message ("Imported module name adjusted: {0} -> {1}" -f $importedComponent.Name, $moduleName)
                    }
                    catch {
                        Write-Log -Level "WARN" -Message ("Imported module name mismatch: expected {0}, actual {1}" -f $moduleName, $importedComponent.Name)
                    }
                }

                if ($moduleFile.Extension -ieq ".cls") {
                    Write-Log -Level "INFO" -Message "Imported class module: $moduleName"
                }
                else {
                    Write-Log -Level "INFO" -Message "Imported module: $moduleName"
                }
            }
            catch {
                Write-Log -Level "ERROR" -Message ("Failed to import module {0}: {1}" -f $moduleName, $_)
            }
            finally {
                if ($null -ne $tempImportPath -and (Test-Path -LiteralPath $tempImportPath)) {
                    try { Remove-Item -LiteralPath $tempImportPath -Force } catch {}
                }
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
