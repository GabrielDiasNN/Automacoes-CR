param(
    [string]$XlsmPath = (Join-Path $PSScriptRoot "..\Receitas Emitidas\Controle de Receitas Emitidas.xlsm"),
    [string]$BasPath = (Join-Path $PSScriptRoot "..\Receitas Emitidas\ModuloPrincipal.bas"),
    [string]$ModName = "ModuloPrincipal"
)

$ErrorActionPreference = "Stop"

function Write-Log {
    param([string]$Level, [string]$Message)
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts] [$Level] $Message"
}

$XlsmPath = [System.IO.Path]::GetFullPath($XlsmPath)
$BasPath = [System.IO.Path]::GetFullPath($BasPath)

if (-not (Test-Path $XlsmPath)) { Write-Log "ERROR" "Arquivo nao encontrado: $XlsmPath"; exit 1 }
if (-not (Test-Path $BasPath)) { Write-Log "ERROR" "Arquivo .bas nao encontrado: $BasPath"; exit 1 }

Write-Log "INFO" "Workbook : $XlsmPath"
Write-Log "INFO" "Modulo   : $BasPath"

# Habilita acesso programatico ao VBA Project via registro (necessario para VBOM)
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

    # Remove modulo existente
    $existing = $null
    foreach ($comp in $vbProj.VBComponents) {
        if ($comp.Name -eq $ModName) {
            $existing = $comp
            break
        }
    }

    if ($null -ne $existing) {
        $vbProj.VBComponents.Remove($existing)
        Write-Log "INFO" "Modulo '$ModName' removido"
    }
    else {
        Write-Log "WARN" "Modulo '$ModName' nao encontrado no projeto (sera importado como novo)"
    }

    # Importa o .bas atualizado
    $vbProj.VBComponents.Import($BasPath) | Out-Null
    Write-Log "INFO" "Modulo '$ModName' importado com sucesso"

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

Write-Log "INFO" "Concluido. Modulo '$ModName' atualizado em: $(Split-Path -Leaf $XlsmPath)"
