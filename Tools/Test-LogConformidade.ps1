# ==============================================================================

# ARQUIVO: Test-LogConformidade.ps1

# VERSAO: 1.0

# DESCRICAO: Guardrail de formato de log. Detecta padroes proibidos em arquivos

#            staged (ou todos) que regredem a convencao de data BR dd/MM/yyyy

#            ou reintroduzem nomes de arquivo diarios com data.

#

# MODOS:

#   -StagedOnly   Varre apenas arquivos staged no git (para pre-commit)

#   -All          Varre todos os .ps1, .psm1, .bas do repositorio

#   -Paths        Varre apenas os arquivos informados explicitamente (para CI)

#

# EXIT CODES:

#   0  - Conforme (nenhuma violacao)

#   1  - Violacoes encontradas

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

    $RootPath = if ($PSScriptRoot) { Split-Path -Parent $PSScriptRoot } else { Get-Location }

}

# Se nenhum modo especificado, assume -StagedOnly

if (-not $StagedOnly -and -not $All -and $Paths.Count -eq 0) {

    $StagedOnly = $true

}

$resolvedRoot = (Resolve-Path -LiteralPath $RootPath).Path

# ==============================================================================

# Padroes proibidos

# ==============================================================================

# PS: formato ISO em chamadas de log

$psPatterns = @(

    @{ Pattern = "Get-Date\s+-Format\s+['""]yyyy-MM-dd"; Desc = "Formato ISO yyyy-MM-dd em Get-Date (usar dd/MM/yyyy)" },

    @{ Pattern = 'T\d{2}:\d{2}:\d{2}'; Desc = "Formato ISO com T separador (usar espaco)" },

    @{ Pattern = "yyyy-MM-dd[^']*(\.log|\.txt)"; Desc = "Nome de arquivo com data ISO + extensao de log" }

)

# VBA: montagem de nome de arquivo diario

$vbaPatterns = @(

    @{ Pattern = 'log_["'']?\s*&\s*(Right|Day|Month|Format)'; Desc = "Nome de arquivo diario montado com data (log_ & dd-mm)" },

    @{ Pattern = 'log_["'']?\s*&\s*Format\$?\(Now'; Desc = 'Nome de arquivo diario com Format$(Now)' }

)

# PS: nome de arquivo diario com data

$psDailyPatterns = @(

    @{ Pattern = "log_.*Get-Date\s+-Format\s+['""]dd-MM"; Desc = "Nome de arquivo diario PS (log_ + dd-MM-yyyy)" },

    @{ Pattern = '"\$\(\s*Get-Date\s+-Format\s+[''"]dd-MM-yyyy[''"]'; Desc = "Interpolacao de data diaria em nome de log" }

)

$allPatterns = @{

    ".ps1"  = $psPatterns + $psDailyPatterns

    ".psm1" = $psPatterns + $psDailyPatterns

    ".bas"  = $vbaPatterns

    ".cls"  = $vbaPatterns

}

# ==============================================================================

# Coletar arquivos

# ==============================================================================

function Get-TargetFiles {

    if ($Paths.Count -gt 0) {

        $files = @()

        foreach ($item in $Paths) {

            if ([string]::IsNullOrWhiteSpace($item)) {

                continue

            }

            $candidate = $item.Trim()

            if (-not [System.IO.Path]::IsPathRooted($candidate)) {

                $candidate = Join-Path $resolvedRoot $candidate

            }

            if (-not (Test-Path -LiteralPath $candidate)) {

                continue

            }

            $ext = [System.IO.Path]::GetExtension($candidate).ToLowerInvariant()

            if (-not $allPatterns.ContainsKey($ext)) {

                continue

            }

            if ($candidate -match '\\Tools\\') {

                continue

            }

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

            # Excluir diretorios Tools/ do escopo de validacao

            if ($rel -match '^Tools/') { continue }

            $ext = [System.IO.Path]::GetExtension($rel).ToLowerInvariant()

            if ($allPatterns.ContainsKey($ext)) {

                $full = Join-Path $resolvedRoot $rel

                if (Test-Path $full) { $files += $full }

            }

        }

        return $files

    }

    else {

        $extensions = @("*.ps1", "*.psm1", "*.bas", "*.cls")

        $files = @()

        foreach ($ext in $extensions) {

            $files += Get-ChildItem -Path $RootPath -Filter $ext -Recurse -File -ErrorAction SilentlyContinue |

            Where-Object { $_.FullName -notmatch '\\node_modules\\|\\\.git\\|\\Tools\\' }

        }

        return $files | Select-Object -ExpandProperty FullName

    }

}

# ==============================================================================

# Varredura

# ==============================================================================

$files = Get-TargetFiles

if ($files.Count -eq 0) {

    Write-Host "[PASS] Test-LogConformidade: nenhum arquivo relevante para verificar." -ForegroundColor Green

    exit 0

}

$violations = @()

foreach ($filePath in $files) {

    $ext = [System.IO.Path]::GetExtension($filePath).ToLowerInvariant()

    $patterns = $allPatterns[$ext]

    if (-not $patterns) { continue }

    $lines = Get-Content -LiteralPath $filePath -ErrorAction SilentlyContinue

    if (-not $lines) { continue }

    for ($i = 0; $i -lt $lines.Count; $i++) {

        $line = $lines[$i]

        foreach ($p in $patterns) {

            if ($line -match $p.Pattern) {

                # Padrao de logging estruturado (docs/logging-standard.md): o
                # campo `ts` do evento e ISO-8601 UTC 'Z' POR CONTRATO. Uma linha
                # que contenha `"ts":"...Z"` (envelope JSON) ou a string de
                # formato `yyyy-MM-ddTHH:mm:ssZ` nao e regressao da data BR.
                if ($p.Desc -like '*T separador*' -and
                    $line -match '("ts"\s*:\s*"[0-9]|yyyy-MM-ddTHH:mm:ssZ)') {
                    continue
                }

                $relPath = $filePath

                if ($filePath.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {

                    $relPath = $filePath.Substring($resolvedRoot.Length).TrimStart('\', '/')

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

# ==============================================================================

# Resultado

# ==============================================================================

if ($violations.Count -eq 0) {

    Write-Host "[PASS] Test-LogConformidade: $($files.Count) arquivo(s) verificado(s), 0 violacoes." -ForegroundColor Green

    exit 0

}

Write-Host ""

Write-Host "============================================================" -ForegroundColor Red

Write-Host " VIOLACOES DE CONFORMIDADE DE LOG ($($violations.Count) encontrada(s))" -ForegroundColor Red

Write-Host "============================================================" -ForegroundColor Red

Write-Host ""

foreach ($v in $violations) {

    Write-Host "  $($v.File):$($v.Line)" -ForegroundColor Yellow -NoNewline

    Write-Host " - $($v.Rule)" -ForegroundColor Red

    Write-Host "    > $($v.Content)" -ForegroundColor DarkGray

}

Write-Host ""

Write-Host "[FAIL] Corrija as violacoes acima antes de commitar." -ForegroundColor Red

exit 1

