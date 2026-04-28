param(
    [string]$RootPath = $PSScriptRoot,
    [string[]]$Paths = @()
)

$ErrorActionPreference = "Stop"
Write-Host "=== Governanca de Seguranca (Zero Trust) ==="

$targetFiles = @()
if ($Paths.Count -gt 0) {
    # Ignora arquivos de package lock e logs
    $targetFiles = $Paths | Where-Object { $_ -notmatch 'package-lock\.json|\.log$|\.env$' }
} else {
    $targetFiles = (git ls-files | Where-Object { $_ -notmatch 'package-lock\.json|\.log$|\.env$' })
}

if ($targetFiles.Count -eq 0) {
    Write-Host "Nenhum arquivo para validar Seguranca Zero Trust."
    exit 0
}

$hasErrors = $false
# Regex detectando padroes restritos (senhas e tokens)
$secretRegex = '(?i)(password|pwd|secret|token|api_key|apikey|credencial|credential)\s*[:=]\s*[''"][^''"]+[''"]'

foreach ($file in $targetFiles) {
    $file = $file.Trim('"')
    $fullPath = Join-Path $RootPath $file
    if (-not (Test-Path $fullPath)) { continue }

    # Ignorando binarios/arquivos muito grandes (leitura linha a linha para nao estourar RAM)
    $lines = Get-Content $fullPath -ErrorAction SilentlyContinue
    $lineNum = 1
    foreach ($line in $lines) {
        if ($line -match $secretRegex) {
            Write-Host "[ERRO DE SEGURANCA] Possivel credencial hardcoded encontrada em '$file' (Linha $lineNum)" -ForegroundColor Red
            Write-Host "  Linha: $($line.Trim())" -ForegroundColor DarkGray
            Write-Host "  Acao: Remova a credencial e utilize variaveis de ambiente (.env) ou gerenciador de segredos." -ForegroundColor Red
            $hasErrors = $true
        }
        $lineNum++
    }
}

if ($hasErrors) {
    Write-Host "`n[FALHA CRITICA] Seguranca Zero Trust violada. Commit bloqueado." -ForegroundColor Red
    exit 1
}

Write-Host "Validacao Zero Trust concluida com sucesso (nenhum secret detectado)." -ForegroundColor Green
exit 0