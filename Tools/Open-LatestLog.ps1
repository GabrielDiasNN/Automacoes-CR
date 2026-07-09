?<#
.SYNOPSIS
    Localiza e abre o arquivo de log mais recente do projeto Automacoes.

.DESCRIPTION
    Busca recursivamente por arquivos .log em todas as pastas 'Logs' do projeto.
    Ordena por data de modificacao e abre o arquivo mais recente usando o editor padrao.

.PARAMETER Slug
    Filtro opcional para buscar por uma automacao especifica (ex: "Montagem", "Bloqueadas").

.EXAMPLE
    pwsh -File Tools/Open-LatestLog.ps1
    Abre o ultimo log modificado em todo o projeto.

.EXAMPLE
    pwsh -File Tools/Open-LatestLog.ps1 -Slug "Montagem"
    Abre o ultimo log que contenha "Montagem" no nome.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Slug = ""
)

$ErrorActionPreference = "Stop"

# -- Definir raiz do projeto --
$RootPath = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path $RootPath)) {
    $RootPath = "."
}

Write-Host "Buscando logs em $RootPath..." -ForegroundColor Cyan

# -- Localizar todas as pastas 'Logs' --
$LogFolders = Get-ChildItem -Path $RootPath -Directory -Recurse -Filter "Logs" -ErrorAction SilentlyContinue

if ($null -eq $LogFolders -or $LogFolders.Count -eq 0) {
    Write-Host "Nenhuma pasta 'Logs' encontrada." -ForegroundColor Red
    exit 1
}

# -- Buscar arquivos .log dentro dessas pastas --
$Filter = if ([string]::IsNullOrWhiteSpace($Slug)) { "*.log" } else { "*$Slug*.log" }

$AllLogs = @()
foreach ($Folder in $LogFolders) {
    $Logs = Get-ChildItem -Path $Folder.FullName -File -Filter $Filter -ErrorAction SilentlyContinue
    if ($Logs) {
        $AllLogs += $Logs
    }
}

if ($AllLogs.Count -eq 0) {
    Write-Host "Nenhum arquivo de log encontrado correspondente ao filtro: $Filter" -ForegroundColor Yellow
    exit 0
}

# -- Ordenar por data de modificacao descendente --
$LatestLog = $AllLogs | Sort-Object LastWriteTime -Descending | Select-Object -First 1

$RelativePath = $LatestLog.FullName.Replace($RootPath, "")
$LastUpdate = $LatestLog.LastWriteTime.ToString("dd/MM/yyyy HH:mm:ss")

Write-Host "--------------------------------------------------------------------------------" -ForegroundColor Gray
Write-Host "Log mais recente localizado:" -ForegroundColor Green
Write-Host "Arquivo: $($LatestLog.Name)" -ForegroundColor White
Write-Host "Pasta:   $($LatestLog.DirectoryName)" -ForegroundColor White
Write-Host "Modificado em: $LastUpdate" -ForegroundColor Gray
Write-Host "--------------------------------------------------------------------------------" -ForegroundColor Gray

# -- Abrir o arquivo --
Write-Host "Abrindo log..." -ForegroundColor Cyan
Invoke-Item $LatestLog.FullName

