# {
#   "version": "1.0.0",
#   "skill": "ai-native-development-standard",
#   "description": "Valida mecanicamente as diretrizes de agente: tamanho dos CLAUDE.md, frases proibidas, imports @, tools dos subagentes e .gitignore"
# }
[CmdletBinding()]
param(
    [string]$RootPath = "."
)

$ErrorActionPreference = "Stop"

$maxLines = 200
$excludedPathRegex = "[\\/](\.venv[^\\/]*|node_modules|\.git)[\\/]"

# Listas fechadas: pedidos permanentes de "pensar mais" e de "expor raciocinio" nao devem
# morar em arquivo de contexto; para ajustar profundidade usa-se effort (ajuste de sessao).
$forbiddenPhrases = @(
    "think carefully", "think step by step", "think hard",
    "pense com cuidado", "pense muito", "pense passo a passo", "raciocine passo a passo",
    "show your reasoning", "think out loud", "explain your thinking",
    "mostre seu raciocinio", "mostre seu raciocínio", "pense em voz alta",
    "explique seu raciocinio", "explique seu raciocínio"
)
$sessionSettingRegex = "(?i)\beffort\b|/fast\b|\bultrathink\b"

$root = (Resolve-Path -LiteralPath $RootPath).Path
$issues = New-Object System.Collections.Generic.List[object]

function Add-GuidelineIssue {
    param([string]$File, [string]$Rule, [string]$Detail)
    $issues.Add([pscustomobject]@{ File = $File; Rule = $Rule; Detail = $Detail })
}

function Get-RelativeName {
    param([string]$FullName)
    return $FullName.Substring($root.Length).TrimStart('\', '/').Replace('\', '/')
}

function Get-ProseLine {
    # Linhas fora de cerca (``` ou ~~~), com code spans removidos: o que o Claude Code trata como texto.
    param([string[]]$Lines)
    $inFence = $false
    $number = 0
    foreach ($line in $Lines) {
        $number++
        if ($line -match '^\s*(```|~~~)') {
            $inFence = -not $inFence
            continue
        }
        if ($inFence) { continue }
        [pscustomobject]@{ Number = $number; Text = ($line -replace '`[^`]*`', '') }
    }
}

$contextFiles = @(Get-ChildItem -LiteralPath $root -Recurse -File -ErrorAction SilentlyContinue | Where-Object {
        ($_.Name -in @("CLAUDE.md", "CLAUDE.local.md")) -and ($_.FullName -notmatch $excludedPathRegex)
    })
$agentsFile = Join-Path $root "AGENTS.md"
$scanFiles = @($contextFiles | ForEach-Object { $_.FullName })
if (Test-Path -LiteralPath $agentsFile -PathType Leaf) { $scanFiles += $agentsFile }

Write-Host "=== GOVERNANCA DE DIRETRIZES DE AGENTE ===" -ForegroundColor Cyan

foreach ($path in $scanFiles) {
    $name = Get-RelativeName -FullName $path
    $lines = @(Get-Content -LiteralPath $path -Encoding UTF8)

    if (($lines.Count -gt $maxLines) -and ($name -ne "AGENTS.md")) {
        Add-GuidelineIssue -File $name -Rule "GUIDELINE_TOO_LONG" -Detail "$($lines.Count) linhas; recomendado ate $maxLines por CLAUDE.md. Mova detalhe de modulo para CLAUDE.md de subpasta."
    }

    foreach ($prose in (Get-ProseLine -Lines $lines)) {
        $lower = $prose.Text.ToLowerInvariant()
        foreach ($phrase in $forbiddenPhrases) {
            if ($lower.Contains($phrase)) {
                Add-GuidelineIssue -File $name -Rule "GUIDELINE_THINK_PHRASE" -Detail "linha $($prose.Number): '$phrase' nao deve ser pedido permanente em arquivo de contexto."
            }
        }
        if ($prose.Text -match $sessionSettingRegex) {
            Add-GuidelineIssue -File $name -Rule "GUIDELINE_SESSION_SETTING" -Detail "linha $($prose.Number): effort, /fast e ultrathink sao ajustes de sessao do usuario, nao de arquivo de contexto."
        }
        if ($name -like "*CLAUDE*.md") {
            foreach ($m in [regex]::Matches($prose.Text, '(?<![\w/@])@([\w.\-]+(?:/[\w.\-]+)+|[\w\-]+\.[A-Za-z]{2,4})(?![\w@])')) {
                $target = Join-Path (Split-Path -Parent $path) $m.Groups[1].Value
                if (-not (Test-Path -LiteralPath $target)) {
                    Add-GuidelineIssue -File $name -Rule "GUIDELINE_IMPORT_BROKEN" -Detail "linha $($prose.Number): @$($m.Groups[1].Value) nao resolve em disco."
                }
            }
        }
    }
}

$agentsDir = Join-Path $root ".claude/agents"
if (Test-Path -LiteralPath $agentsDir -PathType Container) {
    foreach ($agent in (Get-ChildItem -LiteralPath $agentsDir -Filter "*.md" -File)) {
        $head = @(Get-Content -LiteralPath $agent.FullName -Encoding UTF8 -TotalCount 12)
        if (-not ($head | Where-Object { $_ -match '^tools\s*:' })) {
            Add-GuidelineIssue -File (Get-RelativeName -FullName $agent.FullName) -Rule "SUBAGENT_TOOLS_MISSING" -Detail "frontmatter sem 'tools:'; sem ele o subagente herda todas as ferramentas, inclusive Edit e Write."
        }
    }
}

$gitignore = Join-Path $root ".gitignore"
if (Test-Path -LiteralPath $gitignore -PathType Leaf) {
    $ignored = @(Get-Content -LiteralPath $gitignore -Encoding UTF8)
    foreach ($entry in @("CLAUDE.local.md", "TASKS.md")) {
        if (-not ($ignored | Where-Object { $_.Trim() -eq $entry })) {
            Add-GuidelineIssue -File ".gitignore" -Rule "GUIDELINE_GITIGNORE_ENTRY" -Detail "falta a entrada '$entry' (arquivo pessoal ou checklist local do agente)."
        }
    }
}

Write-Host ("Arquivos de diretriz analisados: {0}" -f $scanFiles.Count)

if ($issues.Count -eq 0) {
    Write-Host "[OK] Diretrizes de agente em conformidade." -ForegroundColor Green
    exit 0
}

foreach ($issue in $issues) {
    Write-Host ("  {0} - {1}" -f $issue.File, $issue.Rule) -ForegroundColor Yellow
    Write-Host ("    > {0}" -f $issue.Detail) -ForegroundColor DarkGray
}
Write-Host ("[ERRO] {0} violacao(oes) de diretriz." -f $issues.Count) -ForegroundColor Red
exit 1
