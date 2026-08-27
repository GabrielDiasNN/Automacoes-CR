# ==============================================================================
# ARQUIVO: Test-DateConformidade.ps1
# VERSAO: 1.0.1
# DESCRICAO: Guardrail de conformidade de formato de datas. Detecta padroes 
#            de datas ISO-8601 (YYYY-MM-DD) proibidos em documentacao (.md) e
#            formatacoes de logs/exibicao em arquivos de codigo (.py, .js, .ps1, .psm1).
#
# MODOS:
#   -StagedOnly   Varre apenas arquivos staged no git (para pre-commit)
#   -All          Varre todos os arquivos do repositorio
#   -Paths        Varre apenas os arquivos informados explicitamente
# ==============================================================================
[CmdletBinding()]
param(
    [string]$RootPath,
    [switch]$StagedOnly,
    [switch]$All,
    [string[]]$Paths = @()
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RootPath)) {
    $RootPath = if ($PSScriptRoot) { $PSScriptRoot } else { Get-Location }
    if ($RootPath -match '\\Tools$') {
        $RootPath = Split-Path -Parent $RootPath
    }
}

# Se nenhum modo especificado, assume -StagedOnly
if (-not $StagedOnly -and -not $All -and $Paths.Count -eq 0) {
    $StagedOnly = $true
}

$resolvedRoot = (Resolve-Path -LiteralPath $RootPath).Path

# Padroes proibidos de formatacao de data para exibicao/logs em codigos
$codePatterns = @(
    # Python
    @{ Pattern = '\.strftime\s*\(\s*[''"]%Y[-/]%m[-/]%d'; Desc = "Formato de data ISO no strftime de Python (usar %d/%m/%Y para exibicao/logs)" },
    # PowerShell
    @{ Pattern = 'Get-Date\s+-Format\s+[''"]yyyy[-/]MM[-/]dd'; Desc = "Formato de data ISO no Get-Date de PowerShell (usar dd/MM/yyyy para exibicao/logs)" }
)

$allowedExtensions = @(".md", ".py", ".js", ".ps1", ".psm1")

$skipPathFragments = @(
    "\.git\",
    "\.venv\",
    "\node_modules\",
    "\Logs\",
    "\.wwebjs_auth\",
    "\Backups\",
    "\Tools\",
    "\tests\",
    "CHANGELOG.md",
    "receitas_state.json",
    "delivery_state.json",
    "email_state.json"
)

function Test-ShouldSkipFile {
    param([string]$FilePath)
    $normalized = $FilePath.Replace('/', '\')
    foreach ($fragment in $skipPathFragments) {
        if ($normalized.IndexOf($fragment, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            return $true
        }
    }
    return $false
}

function Get-TargetFiles {
    if ($Paths.Count -gt 0) {
        $files = @()
        foreach ($item in $Paths) {
            if ([string]::IsNullOrWhiteSpace($item)) { continue }
            $candidate = $item.Trim()
            if (-not [System.IO.Path]::IsPathRooted($candidate)) {
                $candidate = Join-Path $resolvedRoot $candidate
            }
            if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
            $ext = [System.IO.Path]::GetExtension($candidate).ToLowerInvariant()
            if ($ext -notin $allowedExtensions) { continue }
            if (Test-ShouldSkipFile -FilePath $candidate) { continue }
            $files += (Resolve-Path -LiteralPath $candidate).Path
        }
        return @($files | Sort-Object -Unique)
    }

    if ($StagedOnly) {
        $stagedRaw = git diff --cached --name-only --diff-filter=ACMR 2>$null
        if (-not $stagedRaw) { return @() }
        $files = @()
        foreach ($rel in ($stagedRaw -split "`n")) {
            $rel = $rel.Trim()
            if (-not $rel) { continue }
            $full = Join-Path $resolvedRoot $rel
            if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { continue }
            $ext = [System.IO.Path]::GetExtension($full).ToLowerInvariant()
            if ($ext -in $allowedExtensions) {
                if (-not (Test-ShouldSkipFile -FilePath $full)) {
                    $files += $full
                }
            }
        }
        return $files
    }
    else {
        # Modo -All
        $files = @()
        foreach ($ext in $allowedExtensions) {
            $files += Get-ChildItem -Path $resolvedRoot -Filter "*$ext" -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { -not (Test-ShouldSkipFile -FilePath $_.FullName) }
        }
        return $files | Select-Object -ExpandProperty FullName
    }
}

$files = Get-TargetFiles
if ($files.Count -eq 0) {
    Write-Host "[PASS] Test-DateConformidade: nenhum arquivo relevante para verificar." -ForegroundColor Green
    exit 0
}

$violations = @()

foreach ($filePath in $files) {
    $ext = [System.IO.Path]::GetExtension($filePath).ToLowerInvariant()
    $lines = Get-Content -LiteralPath $filePath -ErrorAction SilentlyContinue
    if (-not $lines) { continue }

    $relPath = $filePath
    if ($filePath.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        $relPath = $filePath.Substring($resolvedRoot.Length).TrimStart('\', '/')
    }

    if ($ext -eq ".md") {
        # Analise de Markdown (.md)
        $inCodeBlock = $false
        for ($i = 0; $i -lt $lines.Count; $i++) {
            $line = $lines[$i]
            
            # Detecta entrada/saida de bloco de código markdown
            if ($line -match '^\s*```') {
                $inCodeBlock = -not $inCodeBlock
                continue
            }

            # Pula verificacao se estiver dentro de um bloco de codigo
            if ($inCodeBlock) { continue }

            # Procura por datas do tipo YYYY-MM-DD ou YYYY/MM/DD no texto
            # Ignora caminhos de arquivos de logs conhecidos ou URLs
            if ($line -match '\b\d{4}[-/]\d{2}[-/]\d{2}\b') {
                if ($line -match 'http[s]?://' -or $line -match '\bplaywright-e2e-') {
                    continue
                }
                $violations += [PSCustomObject]@{
                    File    = $relPath
                    Line    = $i + 1
                    Rule    = "Formato de data ISO em Markdown (usar DD/MM/YYYY na documentacao)"
                    Content = $line.Trim()
                }
            }
        }
    }
    else {
        # Analise de arquivos de codigo (.py, .js, .ps1, .psm1)
        for ($i = 0; $i -lt $lines.Count; $i++) {
            $line = $lines[$i]
            foreach ($p in $codePatterns) {
                if ($line -match $p.Pattern) {
                    # Excecao do padrao de logging estruturado (docs/logging-standard.md):
                    # o campo `ts` do evento e ISO-8601 UTC 'Z' POR CONTRATO. Um
                    # formato terminado em 'Z' (ex.: %Y-%m-%dT%H:%M:%SZ ou
                    # yyyy-MM-ddTHH:mm:ssZ) e timestamp de maquina, nao data BR de
                    # exibicao.
                    if ($line -match "(%Y-%m-%dT%H:%M:%SZ|yyyy-MM-ddTHH:mm:ssZ|%Y%m%dT%H%M%SZ)") {
                        continue
                    }
                    $violations += [PSCustomObject]@{
                        File    = $relPath
                        Line    = $i + 1
                        Rule    = $p.Desc
                        Content = $line.Trim()
                    }
                }
            }
        }
    }
}

if ($violations.Count -eq 0) {
    Write-Host "[PASS] Test-DateConformidade: $($files.Count) arquivo(s) verificado(s), 0 violacoes de data." -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Red
Write-Host " VIOLACOES DE CONFORMIDADE DE DATAS ($($violations.Count) encontrada(s))" -ForegroundColor Red
Write-Host "============================================================" -ForegroundColor Red
Write-Host ""

foreach ($v in $violations) {
    Write-Host "  $($v.File):$($v.Line)" -ForegroundColor Yellow -NoNewline
    Write-Host " - $($v.Rule)" -ForegroundColor Red
    Write-Host "    > $($v.Content)" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "[FAIL] Corrija as violacoes de formato de data antes de prosseguir." -ForegroundColor Red
exit 1
