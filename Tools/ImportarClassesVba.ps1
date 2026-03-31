
param(
    [string]$XlsmPath,
    [string]$ClassPath,
    [string]$ClassName
)

$ErrorActionPreference = "Stop"

function Write-Log {
    param([string]$Level, [string]$Message)
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts] [$Level] $Message"
}

$XlsmPath = [System.IO.Path]::GetFullPath($XlsmPath)
$ClassPath = [System.IO.Path]::GetFullPath($ClassPath)

if (-not (Test-Path $XlsmPath)) { Write-Log "ERROR" "Arquivo nao encontrado: $XlsmPath"; exit 1 }
if (-not (Test-Path $ClassPath)) { Write-Log "ERROR" "Arquivo .cls nao encontrado: $ClassPath"; exit 1 }
if ([string]::IsNullOrWhiteSpace($ClassName)) { Write-Log "ERROR" "ClassName nao pode ser vazio"; exit 1 }
if ($ClassName.Length -gt 31) { Write-Log "ERROR" "ClassName excede 31 caracteres (limite VBA): $ClassName"; exit 1 }

Write-Log "INFO" "Workbook: $XlsmPath"
Write-Log "INFO" "Classe  : $ClassPath"

# Habilita acesso programatico ao VBA Project via registro
$regPath = "HKCU:\Software\Microsoft\Office\16.0\Excel\Security"
$prevVal = $null
try {
    $prevVal = (Get-ItemProperty -Path $regPath -Name "AccessVBOM" -ErrorAction SilentlyContinue).AccessVBOM
    Set-ItemProperty -Path $regPath -Name "AccessVBOM" -Value 1
    Write-Log "INFO" "VBOM: acesso habilitado (valor anterior: $prevVal)"
}
catch {
    Write-Log "WARN" "Nao foi possivel ajustar o registro VBOM: $_"
}

$excel = $null
$wb = $null

try {
    $excel = New-Object -ComObject "Excel.Application"
    $excel.Visible = $false
    $excel.DisplayAlerts = $false

    Write-Log "INFO" "Abrindo workbook..."
    $wb = $excel.Workbooks.Open($XlsmPath, 0, $false)

    $vbProj = $wb.VBProject

    # Remove classe existente
    $existing = $null
    foreach ($comp in $vbProj.VBComponents) {
        if ($comp.Name -eq $ClassName) {
            $existing = $comp
            break
        }
    }

    if ($null -ne $existing) {
        $vbProj.VBComponents.Remove($existing)
        Write-Log "INFO" "Classe '$ClassName' removida"
    }
    else {
        Write-Log "WARN" "Classe '$ClassName' nao encontrada no projeto (sera importada como nova)"
    }

    # Importa a classe usando Import() (mais simples e robusto que AddFromString)
    $vbProj.VBComponents.Import($ClassPath) | Out-Null
    Write-Log "INFO" "Classe '$ClassName' importada com sucesso"

    $wb.Save()
    Write-Log "INFO" "Workbook salvo"

}
finally {
    if ($null -ne $wb) {
        try { $wb.Close($false) } catch {}
    }
    if ($null -ne $excel) {
        try { $excel.Quit() } catch {}
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null
    }

    # Restaura valor anterior de VBOM
    if ($null -ne $prevVal) {
        try {
            Set-ItemProperty -Path $regPath -Name "AccessVBOM" -Value $prevVal
            Write-Log "INFO" "VBOM: valor restaurado para $prevVal"
        }
        catch {}
    }
    else {
        try {
            Remove-ItemProperty -Path $regPath -Name "AccessVBOM" -ErrorAction SilentlyContinue
            Write-Log "INFO" "VBOM: propriedade removida (estado anterior)"
        }
        catch {}
    }
}

Write-Log "INFO" "Concluido. Classe '$ClassName' atualizada em: $(Split-Path -Leaf $XlsmPath)"
