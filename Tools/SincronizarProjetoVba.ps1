param(
    [Parameter(Mandatory = $true)]
    [string]$XlsmPath,

    [Parameter(Mandatory = $true)]
    [string]$SourceDir,

    # Opcional: pasta com classes/modulos compartilhados (ex: _Shared\VBA).
    # Importados APOS os arquivos de SourceDir para garantir que a versao
    # canonica shared sempre sobrescreve eventuais copias locais.
    [string]$SharedDir = ""
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

$XlsmPath = [System.IO.Path]::GetFullPath($XlsmPath)
$SourceDir = [System.IO.Path]::GetFullPath($SourceDir)

if (-not (Test-Path $XlsmPath)) { throw "Workbook nao encontrado: $XlsmPath" }
if (-not (Test-Path $SourceDir)) { throw "Pasta de fontes nao encontrada: $SourceDir" }

$moduleFiles = Get-ChildItem -Path $SourceDir -File | Where-Object {
    $_.Extension -in ".bas", ".cls"
} | Sort-Object Name

if ($moduleFiles.Count -eq 0) {
    throw "Nenhum arquivo .bas/.cls encontrado em: $SourceDir"
}

$regPath = "HKCU:\Software\Microsoft\Office\16.0\Excel\Security"
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
    $vbProj = $wb.VBProject

    foreach ($file in $moduleFiles) {
        $modName = [System.IO.Path]::GetFileNameWithoutExtension($file.Name)

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
                try { $vbProj.VBComponents.Remove($importedComponent) } catch {}
                throw "Componente '$($file.Name)' importado com tipo incorreto ($([int]$importedComponent.Type)). Esperado: $expectedType."
            }

            Write-Log "INFO" "Importado: $($file.Name)"
        }
        finally {
            if ($null -ne $tempImportPath -and (Test-Path -LiteralPath $tempImportPath)) {
                try { Remove-Item -LiteralPath $tempImportPath -Force } catch {}
            }
        }
    }

    Invoke-ActivateDataSheet -Workbook $wb
    $wb.Save()
    Write-Log "INFO" "Workbook salvo com projeto VBA sincronizado"

    # -------------------------------------------------------------------------
    # Importar arquivos shared (sobrescreve componentes de mesmo nome, se houver)
    # -------------------------------------------------------------------------
    if ($SharedDir -ne "" -and (Test-Path $SharedDir)) {
        $sharedFiles = Get-ChildItem -Path $SharedDir -File | Where-Object {
            $_.Extension -in ".bas", ".cls"
        } | Sort-Object Name

        foreach ($file in $sharedFiles) {
            $modName = [System.IO.Path]::GetFileNameWithoutExtension($file.Name)

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
                    try { $vbProj.VBComponents.Remove($importedComponent) } catch {}
                    throw "Componente shared '$($file.Name)' importado com tipo incorreto ($([int]$importedComponent.Type)). Esperado: $expectedType."
                }

                Write-Log "INFO" "[Shared] Importado: $($file.Name)"
            }
            finally {
                if ($null -ne $tempImportPath -and (Test-Path -LiteralPath $tempImportPath)) {
                    try { Remove-Item -LiteralPath $tempImportPath -Force } catch {}
                }
            }
        }

        Invoke-ActivateDataSheet -Workbook $wb
        $wb.Save()
        Write-Log "INFO" "Workbook salvo apos importacao shared"
    }
}
finally {
    if ($null -ne $wb) {
        try { $wb.Close($false) } catch {}
    }
    if ($null -ne $excel) {
        try { $excel.Quit() } catch {}
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null
    }

    if ($null -ne $prevVal) {
        try { Set-ItemProperty -Path $regPath -Name "AccessVBOM" -Value $prevVal } catch {}
    }
}

Write-Log "INFO" "Sincronizacao concluida"
