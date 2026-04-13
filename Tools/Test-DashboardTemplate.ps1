# ==============================================================================
# ARQUIVO: Test-DashboardTemplate.ps1
# DESCRICAO: Valida contrato HTML/CSS do template de dashboard moderno.
# ==============================================================================

[CmdletBinding()]
param(
    [string]$BasePath = "C:\Automacoes",
    [switch]$FailOnWarnings
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
        return $pathNorm.Substring($rootNorm.Length).TrimStart([char[]]@([char]'\', [char]'/' ))
    }

    return $Path
}

function New-Finding {
    param(
        [string]$File,
        [string]$Rule,
        [string]$Severity,
        [string]$Detail,
        [bool]$IsBlocking = $false
    )

    return [pscustomobject]@{
        File     = $File
        Rule     = $Rule
        Severity = $Severity
        Blocking = $IsBlocking
        Detail   = $Detail
    }
}

function Test-ContainsPattern {
    param(
        [string]$Content,
        [string]$Pattern
    )

    return [regex]::IsMatch($Content, $Pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
}

$templatePath = Join-Path $BasePath ".github\templates\dashboard-modern.html"
$findings = New-Object System.Collections.Generic.List[object]

if (-not (Test-Path -LiteralPath $templatePath)) {
    $findings.Add((New-Finding -File ".github/templates/dashboard-modern.html" -Rule "DASHBOARD_TEMPLATE_MISSING" -Severity "ERRO" -Detail "Template do dashboard moderno nao encontrado." -IsBlocking $true))
    $findings | Format-Table -AutoSize | Out-Host
    exit 2
}

$templateText = Get-Utf8FileText -FilePath $templatePath
$relTemplate = Convert-ToRelativePath -Path $templatePath -Root $BasePath

# Contrato minimo de placeholders e data binding.
if ($templateText -notmatch "__DASHBOARD_JSON__") {
    $findings.Add((New-Finding -File $relTemplate -Rule "PLACEHOLDER_JSON_MISSING" -Severity "ERRO" -Detail "Placeholder __DASHBOARD_JSON__ ausente." -IsBlocking $true))
}

if ($templateText -notmatch "__REFRESH_SECONDS__") {
    $findings.Add((New-Finding -File $relTemplate -Rule "PLACEHOLDER_REFRESH_MISSING" -Severity "ERRO" -Detail "Placeholder __REFRESH_SECONDS__ ausente." -IsBlocking $true))
}

if (-not (Test-ContainsPattern -Content $templateText -Pattern '<script\s+id="dashboard-data"\s+type="application/json">')) {
    $findings.Add((New-Finding -File $relTemplate -Rule "JSON_SCRIPT_TAG_MISSING" -Severity "ERRO" -Detail "Tag de dados JSON (id=dashboard-data) ausente." -IsBlocking $true))
}

if (-not (Test-ContainsPattern -Content $templateText -Pattern 'JSON\.parse\(')) {
    $findings.Add((New-Finding -File $relTemplate -Rule "JSON_PARSE_MISSING" -Severity "ERRO" -Detail "Template nao faz parse do JSON de estado." -IsBlocking $true))
}

if (-not (Test-ContainsPattern -Content $templateText -Pattern 'function\s+escapeHtml\s*\(')) {
    $findings.Add((New-Finding -File $relTemplate -Rule "ESCAPE_HELPER_MISSING" -Severity "ERRO" -Detail "Funcao escapeHtml nao encontrada." -IsBlocking $true))
}

# Tokens e qualidade visual minima.
if (-not (Test-ContainsPattern -Content $templateText -Pattern ':root\s*\{')) {
    $findings.Add((New-Finding -File $relTemplate -Rule "TOKENS_ROOT_MISSING" -Severity "ERRO" -Detail "Bloco :root para design tokens nao encontrado." -IsBlocking $true))
}

$requiredTokens = @('--brand', '--ok', '--warn', '--err', '--text')
foreach ($token in $requiredTokens) {
    if ($templateText -notmatch [regex]::Escape($token)) {
        $findings.Add((New-Finding -File $relTemplate -Rule "TOKEN_MISSING" -Severity "ERRO" -Detail ("Token obrigatorio ausente: {0}" -f $token) -IsBlocking $true))
    }
}

# Criterios obrigatorios de acessibilidade/manutenibilidade.
if (-not (Test-ContainsPattern -Content $templateText -Pattern ':focus|:focus-visible')) {
    $findings.Add((New-Finding -File $relTemplate -Rule "FOCUS_STYLE_MISSING" -Severity "ERRO" -Detail "Sem estilo explicito de foco para navegacao por teclado." -IsBlocking $true))
}

if (-not (Test-ContainsPattern -Content $templateText -Pattern 'aria-label|aria-labelledby|aria-describedby')) {
    $findings.Add((New-Finding -File $relTemplate -Rule "ARIA_METADATA_MISSING" -Severity "ERRO" -Detail "Nenhum atributo ARIA encontrado no template." -IsBlocking $true))
}

if (-not (Test-ContainsPattern -Content $templateText -Pattern '@media')) {
    $findings.Add((New-Finding -File $relTemplate -Rule "RESPONSIVE_MEDIA_QUERY_MISSING" -Severity "ERRO" -Detail "Nenhuma media query encontrada para responsividade." -IsBlocking $true))
}

# Output esperado opcional: warn quando nao existir.
$outputPath = Join-Path $BasePath "Dashboard\dashboard.html"
if (-not (Test-Path -LiteralPath $outputPath)) {
    $findings.Add((New-Finding -File "Dashboard/dashboard.html" -Rule "DASHBOARD_OUTPUT_MISSING" -Severity "WARN" -Detail "Arquivo de output do dashboard ainda nao existe."))
}

$blockingFindings = @($findings | Where-Object { $_.Blocking })
$warningFindings = @($findings | Where-Object { -not $_.Blocking })

Write-Host "=== VALIDACAO DASHBOARD TEMPLATE ==="
Write-Host ("Arquivo base: " + $relTemplate)
Write-Host ("Bloqueios: " + $blockingFindings.Count)
Write-Host ("Alertas : " + $warningFindings.Count)
Write-Host ""

if ($blockingFindings.Count -gt 0) {
    Write-Host "-- BLOQUEIOS --" -ForegroundColor Red
    $blockingFindings | Select-Object File, Rule, Detail | Format-Table -AutoSize | Out-Host
    Write-Host ""
}

if ($warningFindings.Count -gt 0) {
    Write-Host "-- ALERTAS --" -ForegroundColor Yellow
    $warningFindings | Select-Object File, Rule, Detail | Format-Table -AutoSize | Out-Host
    Write-Host ""
}

if ($blockingFindings.Count -gt 0) {
    exit 2
}

if ($FailOnWarnings -and $warningFindings.Count -gt 0) {
    exit 3
}

exit 0
