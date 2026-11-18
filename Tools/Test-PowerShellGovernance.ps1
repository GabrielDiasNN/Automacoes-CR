param(
    [string]$RootPath = $PSScriptRoot,
    [string[]]$Paths = @(),

    # PSScriptAnalyzer so' no diff: com -LintChangedOnly ele roda apenas nos arquivos
    # de -LintScopePaths. O PSScriptAnalyzer so' emite [AVISO] e nunca muda o codigo
    # de saida, mas custava ~34 s na varredura completa (18/11/2026). A regex
    # bloqueante de catch generico (sem tipo) continua sobre TODO o alvo.
    [string[]]$LintScopePaths = @(),
    [switch]$LintChangedOnly
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) }
catch [System.IO.IOException] { Write-Verbose "Sem console para ajustar a codificacao: $($_.Exception.Message)" }
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
    $targetFiles = (git -C $RootPath -c core.quotepath=false ls-files | Where-Object { $_ -match '\.(ps1|psm1)$' })
}

if ($targetFiles.Count -eq 0) {
    Write-Host "Nenhum arquivo PowerShell (.ps1/.psm1) para validar."
    exit 0
}

$hasErrors = $false

$analyzerScope = $null
if ($LintChangedOnly) {
    $analyzerScope = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($scopePath in $LintScopePaths) {
        [void]$analyzerScope.Add(($scopePath.Trim('"') -replace '/', '\'))
    }
}

foreach ($file in $targetFiles) {
    $file = $file.Trim('"')
    $fullPath = Join-Path $RootPath $file
    if (-not (Test-Path -LiteralPath $fullPath)) {
        Write-Host "[AVISO] Arquivo listado mas nao encontrado, ignorado: $file" -ForegroundColor Yellow
        continue
    }

    Write-Host "Analisando: $file"

    # Fora do escopo do diff so' a regex de catch abaixo roda; o import do
    # PSScriptAnalyzer (~3 s) nem acontece quando nenhum arquivo do diff e' PowerShell.
    $runAnalyzer = ($null -eq $analyzerScope) -or $analyzerScope.Contains(($file -replace '/', '\'))
    if ($runAnalyzer -and (Get-Command Invoke-ScriptAnalyzer -ErrorAction SilentlyContinue)) {
        $analyzerResults = Invoke-ScriptAnalyzer -Path $fullPath -Severity Error,Warning
        $relevantResults = @($analyzerResults | Where-Object { $ignoredAnalyzerRules -notcontains $_.RuleName })
        if ($relevantResults.Count -gt 0) {
            Write-Host "[AVISO] PSScriptAnalyzer encontrou falhas relevantes em '$file':" -ForegroundColor Yellow
            $relevantResults | Format-Table -Property Line, RuleName, Message
        }
    } elseif ($runAnalyzer) {
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
