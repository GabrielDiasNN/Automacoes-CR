[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$XlsmPath,

    [Parameter(Mandatory = $true)]
    [string]$SourceDir,

    # Opcional: pasta com classes/modulos compartilhados (ex: _Shared\VBA).
    # Importados APOS os arquivos de SourceDir para garantir que a versao
    # canonica shared sempre sobrescreve eventuais copias locais.
    [string]$SharedDir = "",

    # Permite pular validacao pre-importacao (nao recomendado).
    [switch]$SkipPreImportValidation,

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Write-Log {
    param([string]$Level, [string]$Message)
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts] [$Level] $Message"
}

function Invoke-ActivateDataSheet {
    param($Workbook)
    # Ativa a aba de dados Oracle antes de salvar, evitando que o workbook
    # seja persistido com uma aba auxiliar (ex.: 'Erros NF' ou 'Config') como aba ativa.
    # Estrategia 1: planilha que contem o ListObject da tabela Oracle (VW_EXC_OB_PED_ROM_Faccao).
    $oracleTableName = "VW_EXC_OB_PED_ROM_Faccao"
    foreach ($sh in $Workbook.Worksheets) {
        foreach ($lo in $sh.ListObjects) {
            if ($lo.Name -like "*$oracleTableName*") {
                $sh.Activate()
                Write-Log "INFO" "Aba ativa antes de salvar: $($sh.Name) (via ListObject Oracle)"
                return
            }
        }
    }
    # Estrategia 2: qualquer sheet com ListObjects, exceto abas auxiliares conhecidas.
    $abasAuxiliares = @("Erros NF", "Config")
    foreach ($sh in $Workbook.Worksheets) {
        if ($sh.Name -notin $abasAuxiliares -and $sh.ListObjects.Count -gt 0) {
            $sh.Activate()
            Write-Log "INFO" "Aba ativa antes de salvar: $($sh.Name) (via fallback ListObject)"
            return
        }
    }
    Write-Log "WARN" "Nenhuma aba de dados Oracle encontrada para ativar antes de salvar"
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

function Get-VbaSourceFiles {
    param([string]$FolderPath)

    if ([string]::IsNullOrWhiteSpace($FolderPath)) { return @() }
    if (-not (Test-Path -LiteralPath $FolderPath)) { return @() }

    Get-ChildItem -LiteralPath $FolderPath -File | Where-Object {
        $_.Extension -in ".bas", ".cls" -and
        $_.BaseName -notmatch '^_tmp' -and
        $_.Name -notmatch '^~\$'
    } | Sort-Object Name
}

function Get-VbaComponentNameFromFile {
    param([string]$FilePath)

    $fallback = [System.IO.Path]::GetFileNameWithoutExtension($FilePath)
    $probe = Get-Content -LiteralPath $FilePath -TotalCount 80 -Encoding UTF8 -ErrorAction SilentlyContinue
    foreach ($line in $probe) {
        if ($line -match 'Attribute\s+VB_Name\s*=\s*"([^"]+)"') {
            return $Matches[1]
        }
    }

    return $fallback
}

function Remove-OrphanVbaComponents {
    param(
        $VBProject,
        [System.Collections.Generic.HashSet[string]]$AllowedNames
    )

    $toRemove = @()
    foreach ($comp in $VBProject.VBComponents) {
        if (($comp.Type -eq 1 -or $comp.Type -eq 2 -or $comp.Type -eq 3) -and (-not $AllowedNames.Contains($comp.Name))) {
            $toRemove += $comp
        }
    }

    foreach ($comp in $toRemove) {
        $compName = $comp.Name
        try {
            $VBProject.VBComponents.Remove($comp)
            Write-Log "INFO" "Removido componente orfao: $compName"
        }
        catch [System.Exception] {
            Write-Log "WARN" "Falha ao remover componente orfao '$compName': $($_.Exception.Message)"
        }
    }
}

function Invoke-VbaProjectCompile {
    param(
        $ExcelApp,
        $Workbook
    )

    $Workbook.Activate() | Out-Null
    $compileControl = $ExcelApp.VBE.CommandBars.FindControl(1, 578)

    if ($null -eq $compileControl) {
        throw "Comando de compilacao VBA nao encontrado no VBE (ID 578)."
    }

    $compileControl.Execute()
}

$XlsmPath = [System.IO.Path]::GetFullPath($XlsmPath)
$SourceDir = [System.IO.Path]::GetFullPath($SourceDir)

if (-not (Test-Path $XlsmPath)) { throw "Workbook nao encontrado: $XlsmPath" }
if (-not (Test-Path $SourceDir)) { throw "Pasta de fontes nao encontrada: $SourceDir" }

$moduleFiles = @(Get-VbaSourceFiles -FolderPath $SourceDir)

if ($moduleFiles.Count -eq 0) {
    throw "Nenhum arquivo .bas/.cls encontrado em: $SourceDir"
}

$sharedFiles = @()
if ($SharedDir -ne "" -and (Test-Path -LiteralPath $SharedDir)) {
    $SharedDir = [System.IO.Path]::GetFullPath($SharedDir)
    $sharedFiles = @(Get-VbaSourceFiles -FolderPath $SharedDir)
}

if (-not $SkipPreImportValidation) {
    $validatorScript = Join-Path $PSScriptRoot "ValidarVbaAntesImportar.ps1"
    if (-not (Test-Path -LiteralPath $validatorScript)) {
        throw "Validador pre-importacao nao encontrado: $validatorScript"
    }

    Write-Log "INFO" "Executando validacao pre-importacao de VBA..."
    if ($SharedDir -ne "") {
        & $validatorScript -SourceDir $SourceDir -SharedDir $SharedDir
    }
    else {
        & $validatorScript -SourceDir $SourceDir
    }
    Write-Log "INFO" "Validacao pre-importacao concluida com sucesso"
}

if ($DryRun) {
    Write-Log "INFO" "DRY-RUN: importaria $($moduleFiles.Count) modulo(s) de '$SourceDir' em '$XlsmPath'. Nenhuma alteracao realizada."
    exit 0
}

$officeVersion = (Get-ChildItem "HKCU:\Software\Microsoft\Office" -ErrorAction SilentlyContinue |
    Where-Object { $_.PSChildName -match '^\d+\.\d+$' } |
    Sort-Object { [version]$_.PSChildName } -Descending |
    Select-Object -First 1).PSChildName
if ([string]::IsNullOrWhiteSpace($officeVersion)) { $officeVersion = "16.0" }
$regPath = "HKCU:\Software\Microsoft\Office\$officeVersion\Excel\Security"
$prevVal = $null

$excel = $null
$wb = $null

try {
    $prevVal = (Get-ItemProperty -Path $regPath -Name "AccessVBOM" -ErrorAction SilentlyContinue).AccessVBOM
    Set-ItemProperty -Path $regPath -Name "AccessVBOM" -Value 1

    Write-Log "INFO" "Abrindo Excel COM"
    $excel = New-Object -ComObject "Excel.Application"
    $excel.Visible = $false
    $excel.DisplayAlerts = $false

    Write-Log "INFO" "Abrindo workbook: $XlsmPath"
    $wb = $excel.Workbooks.Open($XlsmPath, 0, $false)
    if ($wb.ReadOnly) {
        throw "Workbook aberto em modo somente leitura. Feche o arquivo no Excel/VBE e tente novamente: $XlsmPath"
    }
    $vbProj = $wb.VBProject

    $allowedNames = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($file in $moduleFiles) {
        [void]$allowedNames.Add((Get-VbaComponentNameFromFile -FilePath $file.FullName))
    }
    foreach ($file in $sharedFiles) {
        [void]$allowedNames.Add((Get-VbaComponentNameFromFile -FilePath $file.FullName))
    }

    Remove-OrphanVbaComponents -VBProject $vbProj -AllowedNames $allowedNames

    foreach ($file in $moduleFiles) {
        $modName = Get-VbaComponentNameFromFile -FilePath $file.FullName

        $existing = $null
        foreach ($comp in $vbProj.VBComponents) {
            if ($comp.Name -eq $modName) {
                # 1=StdModule, 2=ClassModule, 3=MSForm, 100=Document
                if ($comp.Type -eq 1 -or $comp.Type -eq 2 -or $comp.Type -eq 3) {
                    $existing = $comp
                }
                break
            }
        }

        if ($null -ne $existing) {
            $vbProj.VBComponents.Remove($existing)
            Write-Log "INFO" "Removido modulo existente: $modName"
        }

        $expectedType = if ($file.Extension -ieq ".cls") { 2 } else { 1 }
        $tempImportPath = $null
        $importPath = $file.FullName

        try {
            if ($file.Extension -ieq ".cls") {
                $tempImportPath = New-CrlfTempCopy -SourcePath $file.FullName
                $importPath = $tempImportPath
            }

            $importedComponent = $vbProj.VBComponents.Import($importPath)
            if ($null -eq $importedComponent) {
                throw "Import retornou nulo para '$($file.Name)'."
            }

            if ([int]$importedComponent.Type -ne $expectedType) {
                try { $vbProj.VBComponents.Remove($importedComponent) } catch [System.Exception] { } # Ignorado
                throw "Componente '$($file.Name)' importado com tipo incorreto ($([int]$importedComponent.Type)). Esperado: $expectedType."
            }

            Write-Log "INFO" "Importado: $($file.Name)"
        }
        finally {
            if ($null -ne $tempImportPath -and (Test-Path -LiteralPath $tempImportPath)) {
                try { Remove-Item -LiteralPath $tempImportPath -Force } catch [System.Exception] { } # Ignorado
            }
        }
    }

    # -------------------------------------------------------------------------
    # Importar arquivos shared (sobrescreve componentes de mesmo nome, se houver)
    # -------------------------------------------------------------------------
    if ($sharedFiles.Count -gt 0) {
        foreach ($file in $sharedFiles) {
            $modName = Get-VbaComponentNameFromFile -FilePath $file.FullName

            $existing = $null
            foreach ($comp in $vbProj.VBComponents) {
                if ($comp.Name -eq $modName) {
                    if ($comp.Type -eq 1 -or $comp.Type -eq 2 -or $comp.Type -eq 3) {
                        $existing = $comp
                    }
                    break
                }
            }

            if ($null -ne $existing) {
                $vbProj.VBComponents.Remove($existing)
                Write-Log "INFO" "[Shared] Substituindo componente existente: $modName"
            }

            $expectedType = if ($file.Extension -ieq ".cls") { 2 } else { 1 }
            $tempImportPath = $null
            $importPath = $file.FullName

            try {
                if ($file.Extension -ieq ".cls") {
                    $tempImportPath = New-CrlfTempCopy -SourcePath $file.FullName
                    $importPath = $tempImportPath
                }

                $importedComponent = $vbProj.VBComponents.Import($importPath)
                if ($null -eq $importedComponent) {
                    throw "Import shared retornou nulo para '$($file.Name)'."
                }

                if ([int]$importedComponent.Type -ne $expectedType) {
                    try { $vbProj.VBComponents.Remove($importedComponent) } catch [System.Exception] { } # Ignorado
                    throw "Componente shared '$($file.Name)' importado com tipo incorreto ($([int]$importedComponent.Type)). Esperado: $expectedType."
                }

                Write-Log "INFO" "[Shared] Importado: $($file.Name)"
            }
            finally {
                if ($null -ne $tempImportPath -and (Test-Path -LiteralPath $tempImportPath)) {
                    try { Remove-Item -LiteralPath $tempImportPath -Force } catch [System.Exception] { } # Ignorado
                }
            }
        }
    }

    Write-Log "INFO" "Compilando projeto VBA no workbook real antes de salvar..."
    Invoke-VbaProjectCompile -ExcelApp $excel -Workbook $wb
    Write-Log "INFO" "Compilacao no workbook real concluida com sucesso"

    Invoke-ActivateDataSheet -Workbook $wb
    $wb.Save()
    Write-Log "INFO" "Workbook salvo com projeto VBA sincronizado e compilado"
}
finally {
    if ($null -ne $wb) {
        try { $wb.Close($false) } catch [System.Exception] { } # Ignorado
    }
    if ($null -ne $excel) {
        try { $excel.Quit() } catch [System.Exception] { } # Ignorado
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null
    }

    if ($null -ne $prevVal) {
        try { Set-ItemProperty -Path $regPath -Name "AccessVBOM" -Value $prevVal } catch [System.Exception] { } # Ignorado
    }
}

Write-Log "INFO" "Sincronizacao concluida"
