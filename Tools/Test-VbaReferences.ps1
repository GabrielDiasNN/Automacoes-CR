# ==============================================================================

# Test-VbaReferences.ps1

# OBJETIVO: Verificar se existem referencias quebradas (Missing References)

#           nos projetos VBA das automacoes.

# ==============================================================================

param(

    [string]$WorkbookPath

)



$excel = New-Object -ComObject Excel.Application

$excel.Visible = $false

$excel.DisplayAlerts = $false



# Se um caminho especifico foi passado, valida apenas ele. Caso contrario, valida os padroes.

$projects = if ($WorkbookPath) { @($WorkbookPath) } else {

    @(

        "C:\Automacoes\Receitas Bloqueadas\Receitas Bloqueadas.xlsm",

        "C:\Automacoes\Receitas Emitidas\Controle de Receitas Emitidas.xlsm",

        "C:\Automacoes\Montagem de Terceirizados\Validador_Notas_Montagem.xlsm"

    )

}



$errors = 0



foreach ($xlsm in $projects) {

    if (-not (Test-Path $xlsm)) {

        Write-Host "  [AVISO] Arquivo nao encontrado: $xlsm" -ForegroundColor Yellow

        continue

    }



    try {

        $wb = $excel.Workbooks.Open($xlsm)

        $project = $wb.VBProject

        Write-Host "--- Referencias: $($wb.Name) ---" -ForegroundColor Cyan

        foreach ($ref in $project.References) {

            $status = if ($ref.IsBroken) { 

                $errors++

                "BROKEN" 

            } else { "OK" }

            

            $color = if ($ref.IsBroken) { "Red" } else { "Green" }

            Write-Host "  [$status] $($ref.Name) - $($ref.Description)" -ForegroundColor $color

        }

        $wb.Close($false)

    } catch {

        Write-Host "ERRO ao abrir $($xlsm): $($_.Exception.Message)" -ForegroundColor Red

        $errors++

    }

}



$excel.Quit()

[System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null



if ($errors -gt 0) {

    exit 1

} else {

    exit 0

}

