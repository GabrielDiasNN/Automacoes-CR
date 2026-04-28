[CmdletBinding()]
param(
    [string]$BasePath = "C:\Automacoes"
)

$ErrorActionPreference = "Stop"

$script:AllowedFrontmatterKeys = @(
    "name",
    "description",
    "argument-hint",
    "user-invocable",
    "disable-model-invocation"
)

$script:RequiredSections = @(
    "Purpose",
    "When to Use",
    "Do Not Use When",
    "Related Skills",
    "Non-Negotiable Rules",
    "Repo-Specific Constraints",
    "Validation",
    "Troubleshooting",
    "Pre-Delivery Checklist"
)

function Get-SkillFiles {
    param([string]$RootPath)

    $skillsRoot = Join-Path $RootPath ".github\skills"
    if (-not (Test-Path -LiteralPath $skillsRoot)) {
        throw "Diretorio de skills nao encontrado: $skillsRoot"
    }

    return @(Get-ChildItem -LiteralPath $skillsRoot -Recurse -File -Filter "SKILL.md" | Sort-Object FullName)
}

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

function Get-SkillDocumentParts {
    param([string]$Content)

    $match = [regex]::Match(
        $Content,
        '^(?:\uFEFF)?---\r?\n(?<frontmatter>[\s\S]*?)\r?\n---\r?\n?(?<body>[\s\S]*)$'
    )

    if (-not $match.Success) {
        return $null
    }

    return [pscustomobject]@{
        Frontmatter = $match.Groups['frontmatter'].Value
        Body        = $match.Groups['body'].Value
    }
}

function Get-FrontmatterState {
    param([string]$FrontmatterText)

    $map = [ordered]@{}
    $parseErrors = @()
    $lines = [regex]::Split($FrontmatterText, "`r`n|`n|`r")

    foreach ($rawLine in $lines) {
        $line = $rawLine.Trim()
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        if ($line.StartsWith("#")) {
            continue
        }

        if ($line -notmatch '^(?<key>[A-Za-z][A-Za-z0-9-]*)\s*:\s*(?<value>.*)$') {
            $parseErrors += "Linha de frontmatter invalida: $line"
            continue
        }

        $key = [string]$matches['key']
        $value = ([string]$matches['value']).Trim()

        if ($map.Contains($key)) {
            $parseErrors += ("Chave duplicada no frontmatter: {0}" -f $key)
            continue
        }

        if ($value.Length -ge 2) {
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }

        $map[$key] = $value
    }

    return [pscustomobject]@{
        Map         = $map
        ParseErrors = $parseErrors
    }
}

function Get-Level2Headings {
    param([string]$Body)

    $headings = @()
    $headingMatches = [regex]::Matches($Body, '(?m)^##\s+(?<heading>.+?)\s*$')
    foreach ($match in $headingMatches) {
        $headings += $match.Groups['heading'].Value.Trim()
    }

    return $headings
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

function Test-SkillFile {
    param(
        [string]$FilePath,
        [string]$RootPath
    )

    $findings = @()
    $relativePath = Convert-ToRelativePath -Path $FilePath -Root $RootPath
    $folderName = Split-Path -Leaf (Split-Path -Parent $FilePath)

    if ($relativePath -notmatch '^(?:\.github[\\/])skills[\\/][^\\/]+[\\/]SKILL\.md$') {
        $findings += New-Finding -File $relativePath -Rule "SKILL_PATH_INVALID" -Detail "Skill fora do caminho canonico .github/skills/<nome>/SKILL.md"
    }

    $content = Get-Utf8FileText -FilePath $FilePath
    $parts = Get-SkillDocumentParts -Content $content
    if ($null -eq $parts) {
        $findings += New-Finding -File $relativePath -Rule "FRONTMATTER_MISSING" -Detail "Arquivo sem bloco YAML valido no topo"
        return [pscustomobject]@{
            SkillName = ""
            Findings  = $findings
        }
    }

    $frontmatterState = Get-FrontmatterState -FrontmatterText $parts.Frontmatter
    foreach ($parseError in @($frontmatterState.ParseErrors)) {
        $findings += New-Finding -File $relativePath -Rule "FRONTMATTER_INVALID" -Detail $parseError
    }

    $frontmatter = $frontmatterState.Map
    foreach ($key in @($frontmatter.Keys)) {
        if ($script:AllowedFrontmatterKeys -notcontains $key) {
            $findings += New-Finding -File $relativePath -Rule "FRONTMATTER_KEY_NOT_ALLOWED" -Detail ("Chave nao suportada: {0}" -f $key)
        }
    }

    foreach ($requiredKey in @("name", "description")) {
        if (-not $frontmatter.Contains($requiredKey) -or [string]::IsNullOrWhiteSpace([string]$frontmatter[$requiredKey])) {
            $findings += New-Finding -File $relativePath -Rule "REQUIRED_FRONTMATTER_MISSING" -Detail ("Chave obrigatoria ausente: {0}" -f $requiredKey)
        }
    }

    $skillName = ""
    if ($frontmatter.Contains("name")) {
        $skillName = [string]$frontmatter["name"]
        if (-not [string]::IsNullOrWhiteSpace($skillName) -and $skillName -ne $folderName) {
            $findings += New-Finding -File $relativePath -Rule "NAME_FOLDER_MISMATCH" -Detail ("name='{0}' difere da pasta '{1}'" -f $skillName, $folderName)
        }
    }

    if ($frontmatter.Contains("description")) {
        $description = [string]$frontmatter["description"]
        if (-not [string]::IsNullOrWhiteSpace($description) -and $description -notmatch '^Use when\b') {
            $findings += New-Finding -File $relativePath -Rule "DESCRIPTION_DISCOVERY_INVALID" -Detail "description deve comecar com 'Use when'"
        }
    }

    $headings = @(Get-Level2Headings -Body $parts.Body)
    foreach ($requiredSection in $script:RequiredSections) {
        if ($headings -notcontains $requiredSection) {
            $findings += New-Finding -File $relativePath -Rule "REQUIRED_SECTION_MISSING" -Detail ("Secao obrigatoria ausente: {0}" -f $requiredSection)
        }
    }

    $duplicateSections = $headings | Group-Object | Where-Object { $_.Count -gt 1 }
    foreach ($duplicateSection in $duplicateSections) {
        $findings += New-Finding -File $relativePath -Rule "SECTION_DUPLICATED" -Detail ("Secao repetida: {0}" -f [string]$duplicateSection.Name)
    }

    return [pscustomobject]@{
        SkillName = $skillName
        Findings  = $findings
    }
}

function Test-LegacySkillPaths {
    param([string]$RootPath)

    $findings = @()
    $legacyRoot = Join-Path $RootPath ".agents\skills"
    if (-not (Test-Path -LiteralPath $legacyRoot)) {
        return $findings
    }

    $legacyFiles = @(Get-ChildItem -LiteralPath $legacyRoot -Recurse -File -Filter "SKILL.md" | Sort-Object FullName)
    foreach ($legacyFile in $legacyFiles) {
        $findings += New-Finding -File (Convert-ToRelativePath -Path $legacyFile.FullName -Root $RootPath) -Rule "LEGACY_SKILL_LOCATION" -Detail "Skill encontrada em .agents/skills; mover para .github/skills"
    }

    return $findings
}

$skillFiles = @(Get-SkillFiles -RootPath $BasePath)
$allFindings = @()
$skillNameIndex = @{}

foreach ($skillFile in $skillFiles) {
    $result = Test-SkillFile -FilePath $skillFile.FullName -RootPath $BasePath
    $allFindings += @($result.Findings)

    if ([string]::IsNullOrWhiteSpace($result.SkillName)) {
        continue
    }

    if (-not $skillNameIndex.ContainsKey($result.SkillName)) {
        $skillNameIndex[$result.SkillName] = New-Object System.Collections.Generic.List[string]
    }

    $skillNameIndex[$result.SkillName].Add((Convert-ToRelativePath -Path $skillFile.FullName -Root $BasePath))
}

$allFindings += @(Test-LegacySkillPaths -RootPath $BasePath)

foreach ($skillName in @($skillNameIndex.Keys | Sort-Object)) {
    $locations = @($skillNameIndex[$skillName])
    if ($locations.Count -le 1) {
        continue
    }

    foreach ($location in $locations) {
        $allFindings += New-Finding -File $location -Rule "SKILL_NAME_DUPLICATED" -Detail ("Nome de skill duplicado: {0}" -f $skillName)
    }
}

Write-Host "=== GOVERNANCA DE SKILLS ==="
Write-Host ("Arquivos analisados: " + $skillFiles.Count)
Write-Host ("Achados: " + $allFindings.Count)
Write-Host ""

if ($skillFiles.Count -eq 0) {
    Write-Host "[ERRO] Nenhuma SKILL.md encontrada em .github/skills." -ForegroundColor Red
    exit 2
}

if ($allFindings.Count -eq 0) {
    Write-Host "[OK] Skills em conformidade com a governanca canonica."
    exit 0
}

$allFindings |
Sort-Object File, Rule, Detail |
Select-Object File, Rule, Detail |
Format-Table -Wrap -AutoSize |
Out-Host

exit 2
