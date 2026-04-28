param(
    [string]$RootPath = $PSScriptRoot,
    [string[]]$Paths = @()
)

$ErrorActionPreference = "Stop"
Write-Host "=== Governanca Python (Type Hints & Pylint) ==="

$targetFiles = @()
if ($Paths.Count -gt 0) {
    $targetFiles = $Paths | Where-Object { $_ -match '\.py$' }
} else {
    $targetFiles = (git ls-files "*.py")
}

if ($targetFiles.Count -eq 0) {
    Write-Host "Nenhum arquivo Python (.py) para validar."
    exit 0
}

$hasErrors = $false

foreach ($file in $targetFiles) {
    $file = $file.Trim('"')
    $fullPath = Join-Path $RootPath $file
    if (-not (Test-Path $fullPath)) { continue }

    Write-Host "Verificando: $file"

    # Verificacao Mypy (Tipagem Estrita)
    if (Get-Command mypy -ErrorAction SilentlyContinue) {
        $mypyOutput = & mypy --strict $fullPath 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERRO] Falha de Tipagem Estrita (Mypy) em $file" -ForegroundColor Red
            $mypyOutput | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
            $hasErrors = $true
        }
    } else {
        Write-Host "[AVISO] Mypy nao instalado. Validacao de tipagem Python pulada para '$file'." -ForegroundColor Yellow
    }

    # Verificacao Pylint (Qualidade)
    if (Get-Command pylint -ErrorAction SilentlyContinue) {
        $pylintOutput = & pylint --disable=C0114,C0116 $fullPath 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERRO] Falha de Qualidade de Codigo (Pylint) em $file" -ForegroundColor Red
            $pylintOutput | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
            $hasErrors = $true
        }
    } else {
        Write-Host "[AVISO] Pylint nao instalado. Validacao de qualidade Python pulada para '$file'." -ForegroundColor Yellow
    }
}

if ($hasErrors) {
    Write-Host "`n[FALHA] Foram encontrados erros de governanca Python. Corrija-os antes de commitar." -ForegroundColor Red
    exit 1
}

Write-Host "Validacao Python concluida com sucesso." -ForegroundColor Green
exit 0