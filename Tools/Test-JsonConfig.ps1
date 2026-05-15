# {
#   "version": "1.0.0",
#   "skill": "automation-runtime-safety",
#   "description": "Validador de sintaxe JSON para arquivos de configuracao e estado"
# }
[CmdletBinding()]
param(
    [string]$RootPath = "."
)

$ErrorActionPreference = "Stop"

$jsonFiles = Get-ChildItem -Path $RootPath -Filter "*.json" -Recurse | Where-Object {
    $_.FullName -notmatch "\\(\.venv|node_modules|\.git)\\" -and $_.Name -ne "package-lock.json"
}

Write-Host "=== Validando Sintaxe JSON ===" -ForegroundColor Cyan
$hasErrors = $false

foreach ($file in $jsonFiles) {
    try {
        $content = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($content)) {
            Write-Host "[WARN] Arquivo vazio: $($file.FullName)" -ForegroundColor Yellow
            continue
        }
        $null = $content | ConvertFrom-Json
        Write-Host "[OK] $($file.FullName)" -ForegroundColor Green
    }
    catch [System.Exception] {
        $hasErrors = $true
        Write-Host "[ERRO] Falha de sintaxe em: $($file.FullName)" -ForegroundColor Red
        Write-Host "  Motivo: $($_.Exception.Message)" -ForegroundColor Red
    }
}

if ($hasErrors) {
    exit 1
} else {
    Write-Host "Sintaxe JSON validada com sucesso.`n" -ForegroundColor Green
    exit 0
}

