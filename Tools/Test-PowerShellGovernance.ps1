param(
    [string]$RootPath = $PSScriptRoot,
    [string[]]$Paths = @()
)

$ErrorActionPreference = "Stop"
Write-Host "=== Governanca PowerShell (PSScriptAnalyzer & Strict Try/Catch) ==="

$targetFiles = @()
if ($Paths.Count -gt 0) {
    $targetFiles = $Paths | Where-Object { $_ -match '\.(ps1|psm1)$' }
} else {
    $targetFiles = (git ls-files | Where-Object { $_ -match '\.(ps1|psm1)$' })
}

if ($targetFiles.Count -eq 0) {
    Write-Host "Nenhum arquivo PowerShell (.ps1/.psm1) para validar."
    exit 0
}

$hasErrors = $false

foreach ($file in $targetFiles) {
    $file = $file.Trim('"')
    $fullPath = Join-Path $RootPath $file
    if (-not (Test-Path $fullPath)) { continue }

    Write-Host "Analisando: $file"
    
    # Executa PSScriptAnalyzer se o modulo estiver disponivel
    if (Get-Module -ListAvailable -Name PSScriptAnalyzer) {
        $analyzerResults = Invoke-ScriptAnalyzer -Path $fullPath -Severity Error,Warning
        if ($analyzerResults) {
            Write-Host "[AVISO] PSScriptAnalyzer encontrou falhas em '$file':" -ForegroundColor Yellow
            $analyzerResults | Format-Table -Property Line, RuleName, Message
            # Estamos usando warning para nao quebrar imediatamente, mas alertar
        }
    } else {
        Write-Host "[AVISO] Modulo PSScriptAnalyzer nao esta instalado. Instalacao recomendada para validacao de tipagem." -ForegroundColor Yellow
    }

    # Verifica captura generica de excecoes (catch { ... } ao inves de catch [System.Exception] { ... })
    $content = Get-Content $fullPath -Raw
    if ($content -match 'catch\s*\{') {
        Write-Host "[ERRO] Bloco 'catch' generico detectado em '$file'." -ForegroundColor Red
        Write-Host "  Motivo: A diretriz global exige tratamento de excecoes especificas (ex: catch [System.IO.IOException] { ... })." -ForegroundColor Red
        $hasErrors = $true
    }
}

if ($hasErrors) {
    Write-Host "`n[FALHA] Foram encontrados erros na governanca PowerShell. Corrija-os antes de commitar." -ForegroundColor Red
    exit 1
}

Write-Host "Validacao PowerShell concluida com sucesso." -ForegroundColor Green
exit 0