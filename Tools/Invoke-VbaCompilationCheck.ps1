# ==============================================================================
# Invoke-VbaCompilationCheck.ps1
# OBJETIVO: Tentar compilar o projeto VBA para detectar erros de sintaxe
#           ou referências ausentes de forma programática.
# ==============================================================================
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false

$xlsmPath = "C:\Automacoes\Receitas Bloqueadas\Receitas Bloqueadas.xlsm"

try {
    Write-Host "Abrindo: $xlsmPath"
    $wb = $excel.Workbooks.Open($xlsmPath)
    
    $vbe = $excel.VBE
    $proj = $vbe.ActiveVBProject
    
    Write-Host "Projeto: $($proj.Name)"
    
    # Tentar disparar a compilação via CommandBar do VBE (ID 578 é o padrão para Compile)
    $compileControl = $vbe.CommandBars.FindControl(1, 578)
    if ($null -ne $compileControl) {
        Write-Host "Executando comando de compilação..."
        $compileControl.Execute()
        Write-Host "Compilação disparada."
    } else {
        Write-Host "Comando de compilação não encontrado. Tentando salvar para forçar verificação..."
    }

    $wb.Save()
    Write-Host "Workbook salvo."
    $wb.Close($false)
} catch {
    Write-Host "ERRO DETECTADO: $($_.Exception.Message)"
} finally {
    $excel.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null
}
