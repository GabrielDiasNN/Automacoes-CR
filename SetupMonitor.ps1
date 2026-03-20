# SetupMonitor.ps1

$ErrorActionPreference = "Stop"

$Utf8Bom = New-Object System.Text.UTF8Encoding($true)
try {
    [Console]::InputEncoding  = $Utf8Bom
    [Console]::OutputEncoding = $Utf8Bom
    $OutputEncoding = $Utf8Bom
} catch {}

$ScriptDir = "C:\Automacoes"
$MonitorScript = "$ScriptDir\MonitorAutomacoes.ps1"
$ConfigFile = "$ScriptDir\config.json"
$StartupFolder = [Environment]::GetFolderPath("Startup")
$ShortcutPath = "$StartupFolder\MonitorAutomacoes.lnk"

Write-Host "Configurando Monitor..." -ForegroundColor Cyan

if (-not (Test-Path $MonitorScript)) {
    Write-Host "[ERRO] MonitorAutomacoes.ps1 não encontrado. Abortando." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $ConfigFile)) {
    Write-Host "[ERRO] config.json não encontrado. Abortando." -ForegroundColor Red
    exit 1
}

try {
    $null = Get-Content $ConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Write-Host "[ERRO] config.json inválido. Abortando." -ForegroundColor Red
    exit 1
}

try {
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)

    $Shortcut.TargetPath = "powershell.exe"
    $Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$MonitorScript`""
    $Shortcut.WorkingDirectory = $ScriptDir
    $Shortcut.Description = "Monitor Central de Automações"
    $Shortcut.Save()

    Write-Host "[OK] Atalho de inicialização criado." -ForegroundColor Green
} catch {
    Write-Host "[ERRO] Falha ao criar atalho: $_" -ForegroundColor Red
    exit 1
}

Write-Host "Reiniciando serviços..." -ForegroundColor Cyan
Get-Process powershell -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*MonitorAutomacoes.ps1*" } |
    Stop-Process -Force -ErrorAction SilentlyContinue

Start-Sleep -Seconds 1

Write-Host "Iniciando processo do Monitor..." -ForegroundColor Cyan
try {
    Start-Process "powershell.exe" -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$MonitorScript`""
    Write-Host "[OK] Processo iniciado em segundo plano." -ForegroundColor Green
} catch {
    Write-Host "[ERRO] Não foi possível iniciar o monitor: $_" -ForegroundColor Red
    exit 1
}

exit 0