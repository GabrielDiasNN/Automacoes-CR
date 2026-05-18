# ==============================================================================
# ARQUIVO: Test-PlaywrightEvidence.ps1
# DESCRICAO: Valida evidencias documentais da etapa E2E final com Playwright.
# ==============================================================================

[CmdletBinding()]
param(
    [string]$RootPath = "."
)

$ErrorActionPreference = "Stop"

function Get-Utf8FileText {
    param([string]$FilePath)

    return [System.IO.File]::ReadAllText(
        $FilePath,
        (New-Object System.Text.UTF8Encoding($false))
    )
}

function Convert-ToRelativePath {
    param(
        [string]$Path,
        [string]$Root
    )

    $rootNorm = [System.IO.Path]::GetFullPath($Root)
    $pathNorm = [System.IO.Path]::GetFullPath($Path)

    if ($pathNorm.StartsWith($rootNorm, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $pathNorm.Substring($rootNorm.Length).TrimStart([char[]]@('\', '/'))
    }

    return $Path
}

function New-Finding {
    param(
        [string]$File,
        [string]$Rule,
        [string]$Detail
    )

    return [pscustomobject]@{
        File   = $File
        Rule   = $Rule
        Detail = $Detail
    }
}

function Test-RequiredPattern {
    param(
        [System.Collections.Generic.List[object]]$Findings,
        [string]$File,
        [string]$Content,
        [string]$Pattern,
        [string]$Rule,
        [string]$Detail
    )

    if (-not [regex]::IsMatch($Content, $Pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)) {
        $Findings.Add((New-Finding -File $File -Rule $Rule -Detail $Detail))
    }
}

$resolvedRoot = (Resolve-Path -LiteralPath $RootPath).Path
$docsPath = Join-Path $resolvedRoot "docs"
$standardPath = Join-Path $docsPath "playwright-e2e-standard.md"
$templatePath = Join-Path $docsPath "playwright-e2e-evidence-template.md"
$findings = New-Object System.Collections.Generic.List[object]

if (-not (Test-Path -LiteralPath $standardPath)) {
    $findings.Add((New-Finding -File "docs/playwright-e2e-standard.md" -Rule "STANDARD_MISSING" -Detail "Padrao oficial de Playwright E2E nao encontrado."))
}

if (-not (Test-Path -LiteralPath $templatePath)) {
    $findings.Add((New-Finding -File "docs/playwright-e2e-evidence-template.md" -Rule "TEMPLATE_MISSING" -Detail "Template oficial de evidencia Playwright nao encontrado."))
}

if (Test-Path -LiteralPath $standardPath) {
    $standard = Get-Utf8FileText -FilePath $standardPath
    Test-RequiredPattern -Findings $findings -File "docs/playwright-e2e-standard.md" -Content $standard -Pattern "Playwright.*(ultima|última|ultimo|último).*etapa|etapa.*Playwright" -Rule "FINAL_STEP_NOT_DOCUMENTED" -Detail "Padrao deve declarar Playwright E2E como ultima etapa."
    Test-RequiredPattern -Findings $findings -File "docs/playwright-e2e-standard.md" -Content $standard -Pattern "http://127\.0\.0\.1:8000/dashboard/" -Rule "DASHBOARD_URL_MISSING" -Detail "Padrao deve apontar para a tela real servida pelo Orchestrator."
}

$evidenceFiles = @(
    Get-ChildItem -LiteralPath $docsPath -Filter "playwright-e2e-*.md" -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -notin @("playwright-e2e-standard.md", "playwright-e2e-evidence-template.md") } |
    Sort-Object FullName
)

if ($evidenceFiles.Count -eq 0) {
    $findings.Add((New-Finding -File "docs" -Rule "EVIDENCE_MISSING" -Detail "Nenhum arquivo de evidencia Playwright encontrado."))
}

foreach ($file in $evidenceFiles) {
    $relative = Convert-ToRelativePath -Path $file.FullName -Root $resolvedRoot
    $content = Get-Utf8FileText -FilePath $file.FullName

    Test-RequiredPattern -Findings $findings -File $relative -Content $content -Pattern "Evid.ncia E2E Final" -Rule "EVIDENCE_SECTION_MISSING" -Detail "Arquivo deve conter a secao de evidencia E2E final."
    Test-RequiredPattern -Findings $findings -File $relative -Content $content -Pattern "http://127\.0\.0\.1:8000/dashboard/" -Rule "EVIDENCE_URL_MISSING" -Detail "Evidencia deve registrar a URL real validada."
    Test-RequiredPattern -Findings $findings -File $relative -Content $content -Pattern "Playwright E2E \((ultimo|último)\)" -Rule "FINAL_ORDER_MISSING" -Detail "Evidencia deve registrar Playwright como ultima etapa."
    Test-RequiredPattern -Findings $findings -File $relative -Content $content -Pattern "Erros:\s*0" -Rule "CONSOLE_ERRORS_NOT_ZERO" -Detail "Evidencia deve registrar zero erros de console."
    Test-RequiredPattern -Findings $findings -File $relative -Content $content -Pattern "Warnings:\s*0" -Rule "CONSOLE_WARNINGS_NOT_ZERO" -Detail "Evidencia deve registrar zero warnings de console."
    Test-RequiredPattern -Findings $findings -File $relative -Content $content -Pattern "Resultado final:[\s\S]{0,80}Aprovado" -Rule "RESULT_NOT_APPROVED" -Detail "Evidencia deve registrar resultado final aprovado."
}

Write-Host "=== GOVERNANCA PLAYWRIGHT E2E ==="
Write-Host ("Evidencias analisadas: " + $evidenceFiles.Count)
Write-Host ("Erros: " + $findings.Count)
Write-Host ""

if ($findings.Count -eq 0) {
    Write-Host "[OK] Evidencias Playwright em conformidade."
    exit 0
}

$findings |
Sort-Object File, Rule, Detail |
Select-Object File, Rule, Detail |
Format-Table -Wrap -AutoSize |
Out-Host

exit 2
