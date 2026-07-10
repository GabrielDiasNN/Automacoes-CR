param(
    [string]$RootPath = $PSScriptRoot,
    [string[]]$Paths = @()
)

$ErrorActionPreference = "Stop"
Write-Host "=== Governanca SQL (Performance Oracle) ==="

$targetFiles = @()
if ($Paths.Count -gt 0) {
    $targetFiles = $Paths | Where-Object { $_ -match '\.sql$' }
} else {
    $targetFiles = (git ls-files "*.sql")
}

if ($targetFiles.Count -eq 0) {
    Write-Host "Nenhum arquivo SQL (.sql) para validar."
    exit 0
}

$hasErrors = $false
$bannedRegex = '(?i)\bSELECT\s+\*'

foreach ($file in $targetFiles) {
    $file = $file.Trim('"')
    $fullPath = Join-Path $RootPath $file
    if (-not (Test-Path $fullPath)) { continue }

    $content = Get-Content $fullPath -Raw
    if ($content -match $bannedRegex) {
        Write-Host "[ERRO] A query em '$file' contem 'SELECT *'." -ForegroundColor Red
        Write-Host "  Motivo: 'SELECT *' viola a diretriz de Performance O(n) e Custo de Plano de Execucao." -ForegroundColor Red
        Write-Host "  Acao: Especifique as colunas explicitamente." -ForegroundColor Red
        $hasErrors = $true
    }
}

if ($hasErrors) {
    Write-Host "`n[FALHA] Foram encontrados erros de performance SQL. Corrija-os antes de commitar." -ForegroundColor Red
    exit 1
}

Write-Host "Validacao SQL concluida com sucesso." -ForegroundColor Green
exit 0

