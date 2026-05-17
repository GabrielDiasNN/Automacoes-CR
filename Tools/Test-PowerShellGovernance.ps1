param(
    [string]$RootPath = $PSScriptRoot,
    [string[]]$Paths = @()
)

$ErrorActionPreference = "Stop"
Write-Host "=== Governanca PowerShell (PSScriptAnalyzer & Strict Try/Catch) ==="

$ignoredAnalyzerRules = @(
    "PSAvoidOverwritingBuiltInCmdlets",
    "PSAvoidUsingComputerNameHardcoded",
    "PSAvoidUsingEmptyCatchBlock",
    "PSAvoidUsingWriteHost",
    "PSReviewUnusedParameter",
    "PSUseDeclaredVarsMoreThanAssignments",
    "PSUseShouldProcessForStateChangingFunctions",
    "PSUseSingularNouns"
)

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

    if (Get-Command Invoke-ScriptAnalyzer -ErrorAction SilentlyContinue) {
        $analyzerResults = Invoke-ScriptAnalyzer -Path $fullPath -Severity Error,Warning
        $relevantResults = @($analyzerResults | Where-Object { $ignoredAnalyzerRules -notcontains $_.RuleName })
        if ($relevantResults.Count -gt 0) {
            Write-Host "[AVISO] PSScriptAnalyzer encontrou falhas relevantes em '$file':" -ForegroundColor Yellow
            $relevantResults | Format-Table -Property Line, RuleName, Message
        }
    } else {
        Write-Host "[AVISO] Modulo PSScriptAnalyzer nao esta instalado. Instalacao recomendada para validacao de tipagem." -ForegroundColor Yellow
    }

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
