param(
    [string]$RootPath = $PSScriptRoot,
    [string[]]$Paths = @()
)

$ErrorActionPreference = "Stop"
Write-Host "=== Governanca de Portabilidade (Caminhos Relativos) ==="

$targetFiles = @()
if ($Paths.Count -gt 0) {
    # Ignora logs e arquivos compilados
    $targetFiles = $Paths | Where-Object { $_ -notmatch '\.(log|json\.bak|png|jpg)$' }
} else {
    $targetFiles = (git ls-files | Where-Object { $_ -notmatch '\.(log|json\.bak|png|jpg)$' })
}

if ($targetFiles.Count -eq 0) {
    Write-Host "Nenhum arquivo para validar portabilidade."
    exit 0
}

$hasErrors = $false
# Regex detectando caminhos absolutos hardcoded, ex: ., D:\Projetos, C:/Users
$absolutePathRegex = '(?i)[a-z]:[\\/](?!instantclient)[a-z0-9_ -]+'

foreach ($file in $targetFiles) {
    $file = $file.Trim('"')
    $fullPath = Join-Path $RootPath $file
    if (-not (Test-Path $fullPath)) { continue }

    # Ignorando scripts de setup que podem ter caminhos de exemplo em comentarios
    if ($file -match 'SetupMonitor|Copilot|CONTEXT|README|runbook') { continue }

    $lines = Get-Content $fullPath -ErrorAction SilentlyContinue
    $lineNum = 1
    foreach ($line in $lines) {
        # Ignora linhas comentadas (PowerShell, Python, JS, VBA)
        if ($line -match '^\s*(#|//|''|--|REM)') { $lineNum++; continue }

        if ($line -match $absolutePathRegex) {
            Write-Host "[ERRO DE PORTABILIDADE] Caminho absoluto engessado encontrado em '$file' (Linha $lineNum)" -ForegroundColor Red
            Write-Host "  Linha: $($line.Trim())" -ForegroundColor DarkGray
            Write-Host "  Acao: O projeto e 100% dinamico. Utilize variaveis relativas como `$PSScriptRoot, .\ ou os modulos de config." -ForegroundColor Red
            $hasErrors = $true
        }
        $lineNum++
    }
}

if ($hasErrors) {
    Write-Host "`n[FALHA CRITICA] Portabilidade violada. Nao crie dependencias de C:\ ou D:\. Commit bloqueado." -ForegroundColor Red
    exit 1
}

Write-Host "Validacao de Portabilidade concluida com sucesso." -ForegroundColor Green
exit 0
