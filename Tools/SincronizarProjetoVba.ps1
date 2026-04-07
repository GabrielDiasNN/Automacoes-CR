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

        $vbProj.VBComponents.Import($file.FullName) | Out-Null
        Write-Log "INFO" "Importado: $($file.Name)"
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

            $vbProj.VBComponents.Import($file.FullName) | Out-Null
            Write-Log "INFO" "[Shared] Importado: $($file.Name)"
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
