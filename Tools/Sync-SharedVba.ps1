# ==============================================================================
# ARQUIVO: Sync-SharedVba.ps1
# VERSÃO: 1.0
# DESCRIÇÃO: Sincroniza módulos VBA compartilhados da pasta _Shared\VBA para
#            cada automação individual, garantindo unicidade de código.
# ==============================================================================

[CmdletBinding()]
param(
    [string]$RootPath = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RootPath)) {
    $RootPath = $PSScriptRoot
    if (-not $RootPath) { $RootPath = Split-Path -Parent $MyInvocation.MyCommand.Path }
    if ($RootPath -match "Tools$") { $RootPath = Split-Path -Parent $RootPath }
}

$SharedDir = Join-Path $RootPath "_Shared\VBA"
if (-not (Test-Path $SharedDir)) {
    Write-Host "ERRO: Pasta _Shared\VBA nao encontrada em $SharedDir" -ForegroundColor Red
    exit 1
}

$SharedFiles = Get-ChildItem -Path $SharedDir -File | Where-Object { $_.Extension -in ".bas", ".cls" }
if ($SharedFiles.Count -eq 0) {
    Write-Host "AVISO: Nenhum arquivo .bas ou .cls encontrado em _Shared\VBA" -ForegroundColor Yellow
    exit 0
}

Write-Host "--- Sincronizando VBA Shared (Raiz: $RootPath) ---" -ForegroundColor Cyan

# Identifica automações (pastas que contêm run.ps1)
$Automacoes = Get-ChildItem -Path $RootPath -Directory | Where-Object { 
    (Test-Path (Join-Path $_.FullName "run.ps1")) -and ($_.Name -ne "Tools") -and ($_.Name -ne "_Shared") -and ($_.Name -ne "Audit")
}

foreach ($automacao in $Automacoes) {
    Write-Host "`nProcessando: $($automacao.Name)" -ForegroundColor Yellow
    
    foreach ($sharedFile in $SharedFiles) {
        $destPath = Join-Path $automacao.FullName $sharedFile.Name
        
        # Se o arquivo já existe na automação, sincroniza
        if (Test-Path $destPath) {
            $sharedHash = (Get-FileHash $sharedFile.FullName).Hash
            $localHash = (Get-FileHash $destPath).Hash
            
            if ($sharedHash -ne $localHash) {
                Write-Host "  [UPD] $($sharedFile.Name) (Divergencia detectada)" -ForegroundColor Cyan
                Copy-Item $sharedFile.FullName -Destination $destPath -Force
            } else {
                Write-Host "  [OK]  $($sharedFile.Name) (Ja sincronizado)" -ForegroundColor Gray
            }
        } else {
            # Opcional: Se desejar propagar NOVOS arquivos compartilhados para todas
            # Write-Host "  [NEW] $($sharedFile.Name) (Adicionando novo modulo)" -ForegroundColor Green
            # Copy-Item $sharedFile.FullName -Destination $destPath -Force
            Write-Host "  [SKP] $($sharedFile.Name) (Nao presente nesta automacao)" -ForegroundColor DarkGray
        }
    }
}

Write-Host "`n--- Sincronizacao Concluida ---" -ForegroundColor Cyan
