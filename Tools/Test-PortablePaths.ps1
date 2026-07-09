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
# Regex detectando caminhos absolutos hardcoded, ex: C:\Users, D:/Projetos
# Exige que tenha pelo menos uma barra seguida de caracteres de pasta
# Tambem captura caminhos de UM UNICO segmento sem barra final antes do fim
# da string/aspas (ex: r"c:\Automacoes"), usando lookahead alternativo.
# Exclui tambem "Windows" (ex: C:\Windows, C:/Windows) pelo mesmo motivo de
# "instantclient": e um caminho de sistema operacional universal (mesmo em toda maquina
# Windows), nao um caminho de projeto/desenvolvedor especifico.
$absolutePathRegex = '(?i)[a-z]:[\\/](?![\\/\s])(?!instantclient)(?!Windows\b)[a-z0-9_ -]+(?:[\\/]|(?=["''\)\];,]|\s*$))'

foreach ($file in $targetFiles) {
    $file = $file.Trim('"')
    $fullPath = Join-Path $RootPath $file
    if (-not (Test-Path $fullPath)) { continue }

    # Ignorando scripts de setup e pastas de legado/template
    if ($file -match 'SetupMonitor|Copilot|CONTEXT|README|runbook|_Template') { continue }

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

