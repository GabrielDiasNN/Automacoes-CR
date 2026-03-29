param(
    [Parameter(Mandatory = $true)]
    [string]$XlsmPath,

    [Parameter(Mandatory = $true)]
    [string]$SourceDir
)

$ErrorActionPreference = "Stop"

function Write-Log {
    param([string]$Level, [string]$Message)
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts] [$Level] $Message"
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

    $wb.Save()
    Write-Log "INFO" "Workbook salvo com projeto VBA sincronizado"
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
