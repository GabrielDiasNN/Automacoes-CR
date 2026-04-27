# ==============================================================================
# Test-VbaComponentTypes.ps1
# OBJETIVO: Validar se as classes compartilhadas foram importadas corretamente 
#           como Modulos de Classe (Type 2) e nao como Modulos Padrao (Type 1).
# ==============================================================================
param(
    [string]$WorkbookPath,
    [string]$SourceFolder
)

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false

$criticalClasses = @("ClsEmailComposerService", "ClsOutlookAdapter")
$errors = 0

# Se um caminho especifico foi passado, valida apenas ele. Caso contrario, valida os padroes.
$projects = if ($WorkbookPath) { @($WorkbookPath) } else {
    @(
        "C:\Automacoes\Receitas Bloqueadas\Receitas Bloqueadas.xlsm",
        "C:\Automacoes\Receitas Emitidas\Controle de Receitas Emitidas.xlsm",
        "C:\Automacoes\Montagem de Terceirizados\Validador_Notas_Montagem.xlsm"
    )
}

foreach ($xlsm in $projects) {
    if (-not (Test-Path $xlsm)) {
        Write-Host "  [AVISO] Arquivo nao encontrado: $xlsm" -ForegroundColor Yellow
        continue
    }

    try {
        $wb = $excel.Workbooks.Open($xlsm)
        $project = $wb.VBProject
        Write-Host "Verificando: $(Split-Path $xlsm -Leaf)" -ForegroundColor Cyan
        
        foreach ($className in $criticalClasses) {
            try {
                $comp = $project.VBComponents.Item($className)
                if ($comp.Type -ne 2) {
                    Write-Host "  [ERRO] $className esta com Tipo=$($comp.Type). Deveria ser 2 (Classe)." -ForegroundColor Red
                    $errors++
                } else {
                    Write-Host "  [OK] $className (Tipo 2)" -ForegroundColor Green
                }
            } catch {
                Write-Host "  [AVISO] $className nao encontrado neste projeto." -ForegroundColor Yellow
            }
        }
        $wb.Close($false)
    } catch {
        Write-Host "  [FALHA] Nao foi possivel abrir o projeto: $($_.Exception.Message)" -ForegroundColor Red
        $errors++
    }
}

$excel.Quit()
[System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null

if ($errors -gt 0) {
    Write-Host "`nIntegridade VBA COMPROMETIDA! ($errors erro(s))" -ForegroundColor Red
    exit 1
} else {
    Write-Host "`nIntegridade VBA VALIDADA." -ForegroundColor Green
    exit 0
}
