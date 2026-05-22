[CmdletBinding()]
param(
    [string]$BasePath = "."
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

$script:ActiveSkillNames = @(
    "ai-native-development-standard",
    "automation-runtime-safety",
    "enterprise-orchestration-contract",
    "html-css-enterprise-standard",
    "nodejs-communications",
    "powershell-automation-monitor",
    "python-enterprise-standard"
)

$script:LegacySkillNames = @(
    "python-oracle-migration",
    "vba-enterprise-core"
)

$script:GlobalSharedSkillNames = @(
    "ai-engineering-discipline",
    "protocolo-valeg",
    "git-ide-governance-skill"
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

function Get-SectionContent {
    param(
        [string]$Body,
        [string]$SectionName
    )

    $pattern = '(?ms)^##\s+' + [regex]::Escape($SectionName) + '\s*$\r?\n(?<content>.*?)(?=^##\s+|\z)'
    $match = [regex]::Match($Body, $pattern)
    if (-not $match.Success) {
        return ""
    }

    return $match.Groups['content'].Value.Trim()
}

function Get-BulletItems {
    param([string]$SectionContent)

    $items = New-Object System.Collections.Generic.List[string]
    $lines = [regex]::Split($SectionContent, "`r`n|`n|`r")
    foreach ($rawLine in $lines) {
        $line = $rawLine.Trim()
        if ($line -match '^-+\s+(.+)$') {
            $items.Add($matches[1].Trim())
        }
    }

    return @($items)
}

function New-Finding {
    param(
        [string]$File,
        [string]$Rule,
        [string]$Detail,
        [string]$Severity = "ERROR"
    )

    return [pscustomobject]@{
        File     = $File
        Rule     = $Rule
        Severity = $Severity
        Detail   = $Detail
    }
}

function Resolve-LinkTargetPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LinkPath,
        [Parameter(Mandatory = $true)]
        [string]$RootForRelativeTarget
    )

    $item = Get-Item -LiteralPath $LinkPath -Force
    if (-not $item.LinkType -and -not ($item.Attributes -match "ReparsePoint")) {
        return [pscustomobject]@{
            IsLinked       = $false
            ResolvedTarget = ""
        }
    }

    # Resolução recursiva robusta compatível com PowerShell 5.1 e 7.x
    $currentPath = $LinkPath
    $resolvedTarget = ""
    for ($i = 0; $i -lt 10; $i++) {
        if (Test-Path -LiteralPath $currentPath) {
            $currItem = Get-Item -LiteralPath $currentPath -Force
            if ($currItem.LinkType -or ($currItem.Attributes -match "ReparsePoint")) {
                $t = $currItem.ResolvedTarget
                if ([string]::IsNullOrWhiteSpace($t) -and $currItem.Target) {
                    if ($currItem.Target -is [System.Array]) {
                        $t = [string]$currItem.Target[0]
                    } else {
                        $t = [string]$currItem.Target
                    }
                }
                if (-not [string]::IsNullOrWhiteSpace($t)) {
                    if (-not [System.IO.Path]::IsPathRooted($t)) {
                        $t = [System.IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $currentPath) $t))
                    }
                    $currentPath = $t
                    $resolvedTarget = $t
                } else {
                    break
                }
            } else {
                break
            }
        } else {
            break
        }
    }

    return [pscustomobject]@{
        IsLinked       = $true
        ResolvedTarget = $resolvedTarget
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

    if ($content -match 'Conforme diretrizes globais\.') {
        $findings += New-Finding -File $relativePath -Rule "PLACEHOLDER_CONTENT_DETECTED" -Detail "Placeholder proibido detectado: 'Conforme diretrizes globais.'"
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

    $relatedSkillsContent = Get-SectionContent -Body $parts.Body -SectionName "Related Skills"
    $relatedSkills = @(Get-BulletItems -SectionContent $relatedSkillsContent)
    foreach ($relatedSkillItem in $relatedSkills) {
        $referencedSkills = [regex]::Matches($relatedSkillItem, '`(?<skill>[-a-z0-9]+)`')
        foreach ($skillMatch in $referencedSkills) {
            $referencedSkill = $skillMatch.Groups['skill'].Value
            if ($script:ActiveSkillNames -notcontains $referencedSkill) {
                $findings += New-Finding -File $relativePath -Rule "RELATED_SKILL_INVALID" -Detail ("Related Skills referencia skill inexistente ou inativa: {0}" -f $referencedSkill)
            }
        }
    }

    $doNotUseWhenContent = Get-SectionContent -Body $parts.Body -SectionName "Do Not Use When"
    if ([string]::IsNullOrWhiteSpace($doNotUseWhenContent)) {
        $findings += New-Finding -File $relativePath -Rule "DO_NOT_USE_EMPTY" -Detail "Secao Do Not Use When sem conteudo operacional." -Severity "WARN"
    } elseif ($doNotUseWhenContent -match '(?i)\bconforme\b|\bdiretrizes globais\b|\bgenerico\b') {
        $findings += New-Finding -File $relativePath -Rule "DO_NOT_USE_GENERIC" -Detail "Secao Do Not Use When esta generica demais." -Severity "WARN"
    }

    $validationContent = Get-SectionContent -Body $parts.Body -SectionName "Validation"
    if ([string]::IsNullOrWhiteSpace($validationContent) -or $validationContent -notmatch '(Tools/|`.+?`|\.ps1|\.py|\.json|\.md|pwsh\s|powershell\s)') {
        $findings += New-Finding -File $relativePath -Rule "VALIDATION_NOT_ACTIONABLE" -Detail "Secao Validation nao cita comando, teste ou arquivo concreto." -Severity "WARN"
    }

    $repoSpecificContent = Get-SectionContent -Body $parts.Body -SectionName "Repo-Specific Constraints"
    $troubleshootingContent = Get-SectionContent -Body $parts.Body -SectionName "Troubleshooting"
    $hasRepoReference = ($repoSpecificContent + "`n" + $validationContent + "`n" + $troubleshootingContent) -match '([A-Za-z0-9_. -]+/|[A-Za-z0-9_. -]+\\)'
    if (-not $hasRepoReference) {
        $findings += New-Finding -File $relativePath -Rule "REPO_REFERENCE_MISSING" -Detail "Skill nao referencia artefato real do repo em Repo-Specific Constraints, Validation ou Troubleshooting." -Severity "WARN"
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

function Test-SkillsReadme {
    param([string]$RootPath)

    $findings = @()
    $readmePath = Join-Path $RootPath ".github\skills\README.md"
    if (-not (Test-Path -LiteralPath $readmePath)) {
        $findings += New-Finding -File ".github/skills/README.md" -Rule "SKILLS_README_MISSING" -Detail "README canonico das skills nao encontrado."
        return $findings
    }

    $relativePath = Convert-ToRelativePath -Path $readmePath -Root $RootPath
    $content = Get-Utf8FileText -FilePath $readmePath

    foreach ($legacySkill in $script:LegacySkillNames) {
        if ($content -match [regex]::Escape($legacySkill)) {
            $findings += New-Finding -File $relativePath -Rule "LEGACY_SKILL_REFERENCED" -Detail ("README de skills ainda referencia skill legada: {0}" -f $legacySkill)
        }
    }

    foreach ($activeSkill in $script:ActiveSkillNames) {
        if ($content -notmatch [regex]::Escape($activeSkill)) {
            $findings += New-Finding -File $relativePath -Rule "ACTIVE_SKILL_MISSING_IN_README" -Detail ("README de skills nao lista skill ativa: {0}" -f $activeSkill)
        }
    }

    $tickMatches = [regex]::Matches($content, '`(?<skill>[-a-z0-9]+)`')
    foreach ($match in $tickMatches) {
        $skill = $match.Groups['skill'].Value
        if (($script:ActiveSkillNames -notcontains $skill) -and ($script:AllowedFrontmatterKeys -notcontains $skill)) {
            $findings += New-Finding -File $relativePath -Rule "README_SKILL_REFERENCE_INVALID" -Detail ("README de skills referencia skill fora da taxonomia ativa: {0}" -f $skill)
        }
    }

    return $findings
}

function Test-GeminiSkillMirrors {
    param([string]$RootPath)

    $findings = @()
    $geminiSkillsRoot = Join-Path $RootPath ".gemini\skills"
    if (-not (Test-Path -LiteralPath $geminiSkillsRoot)) {
        $findings += New-Finding -File ".gemini/skills" -Rule "GEMINI_SKILLS_ROOT_MISSING" -Detail "Diretorio .gemini/skills nao encontrado." -Severity "WARN"
        return $findings
    }

    foreach ($skillName in $script:ActiveSkillNames) {
        $mirrorPath = Join-Path $geminiSkillsRoot $skillName
        $canonicalPath = Join-Path (Join-Path $RootPath ".github\skills") $skillName

        if (-not (Test-Path -LiteralPath $mirrorPath)) {
            $findings += New-Finding -File ".gemini/skills/$skillName" -Rule "GEMINI_SKILL_MIRROR_MISSING" -Detail ("Mirror da skill nao encontrado em .gemini/skills: {0}" -f $skillName)
            continue
        }

        $targetState = Resolve-LinkTargetPath -LinkPath $mirrorPath -RootForRelativeTarget $geminiSkillsRoot
        if (-not $targetState.IsLinked) {
            $findings += New-Finding -File ".gemini/skills/$skillName" -Rule "GEMINI_SKILL_MIRROR_NOT_LINKED" -Detail ("Mirror existe, mas nao e link simbolico ou junction: {0}" -f $skillName) -Severity "WARN"
            continue
        }

        $resolvedMirror = $targetState.ResolvedTarget
        $resolvedCanonical = (Resolve-Path -LiteralPath $canonicalPath).Path
        if ([string]::IsNullOrWhiteSpace($resolvedMirror)) {
            $findings += New-Finding -File ".gemini/skills/$skillName" -Rule "GEMINI_SKILL_MIRROR_UNRESOLVED" -Detail ("Mirror nao expoe ResolvedTarget para validacao: {0}" -f $skillName) -Severity "WARN"
            continue
        }

        if ($resolvedMirror -ne $resolvedCanonical) {
            $findings += New-Finding -File ".gemini/skills/$skillName" -Rule "GEMINI_SKILL_MIRROR_TARGET_INVALID" -Detail ("Mirror nao aponta para a skill canonica em .github/skills: {0}" -f $skillName)
        }
    }

    return $findings
}

function Test-CodexGlobalSharedSkillMirrors {
    $findings = @()
    $userProfile = [Environment]::GetFolderPath("UserProfile")
    $codexSkillsRoot = Join-Path $userProfile ".codex\skills"
    $globalSharedRoot = Join-Path $userProfile ".gemini\antigravity\skills"

    if (-not (Test-Path -LiteralPath $globalSharedRoot)) {
        $findings += New-Finding -File $globalSharedRoot -Rule "GLOBAL_SHARED_SKILLS_ROOT_MISSING" -Detail "Diretorio canonico das skills globais compartilhadas nao encontrado no ambiente atual." -Severity "WARN"
        return $findings
    }

    if (-not (Test-Path -LiteralPath $codexSkillsRoot)) {
        $findings += New-Finding -File $codexSkillsRoot -Rule "CODEX_SKILLS_ROOT_MISSING" -Detail "Diretorio de skills globais do Codex nao encontrado no ambiente atual." -Severity "WARN"
        return $findings
    }

    foreach ($skillName in $script:GlobalSharedSkillNames) {
        $mirrorPath = Join-Path $codexSkillsRoot $skillName
        $canonicalPath = Join-Path $globalSharedRoot $skillName

        if (-not (Test-Path -LiteralPath $canonicalPath)) {
            $findings += New-Finding -File $canonicalPath -Rule "GLOBAL_SHARED_SKILL_CANONICAL_MISSING" -Detail ("Skill global canonica obrigatoria nao encontrada: {0}" -f $skillName)
            continue
        }

        if (-not (Test-Path -LiteralPath $mirrorPath)) {
            $findings += New-Finding -File $mirrorPath -Rule "CODEX_SHARED_SKILL_MIRROR_MISSING" -Detail ("Mirror da skill global obrigatoria nao encontrado no Codex: {0}" -f $skillName)
            continue
        }

        $targetState = Resolve-LinkTargetPath -LinkPath $mirrorPath -RootForRelativeTarget $codexSkillsRoot
        if (-not $targetState.IsLinked) {
            $findings += New-Finding -File $mirrorPath -Rule "CODEX_SHARED_SKILL_MIRROR_NOT_LINKED" -Detail ("Skill global existe no Codex, mas nao e link simbolico ou junction: {0}" -f $skillName)
            continue
        }

        $resolvedMirror = $targetState.ResolvedTarget

        $canonicalTargetState = Resolve-LinkTargetPath -LinkPath $canonicalPath -RootForRelativeTarget $globalSharedRoot
        if ($canonicalTargetState.IsLinked -and -not [string]::IsNullOrWhiteSpace($canonicalTargetState.ResolvedTarget)) {
            $resolvedCanonical = $canonicalTargetState.ResolvedTarget
        } else {
            $resolvedCanonical = (Resolve-Path -LiteralPath $canonicalPath).Path
        }

        if ([string]::IsNullOrWhiteSpace($resolvedMirror)) {
            $findings += New-Finding -File $mirrorPath -Rule "CODEX_SHARED_SKILL_MIRROR_UNRESOLVED" -Detail ("Mirror do Codex nao expoe ResolvedTarget para validacao: {0}" -f $skillName) -Severity "WARN"
            continue
        }

        if ($resolvedMirror -ne $resolvedCanonical) {
            $findings += New-Finding -File $mirrorPath -Rule "CODEX_SHARED_SKILL_MIRROR_TARGET_INVALID" -Detail ("Mirror do Codex nao aponta para a skill global canonica: {0}" -f $skillName)
        }
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
$allFindings += @(Test-SkillsReadme -RootPath $BasePath)
$allFindings += @(Test-GeminiSkillMirrors -RootPath $BasePath)
$allFindings += @(Test-CodexGlobalSharedSkillMirrors)

foreach ($skillName in @($skillNameIndex.Keys | Sort-Object)) {
    $locations = @($skillNameIndex[$skillName])
    if ($locations.Count -le 1) {
        continue
    }

    foreach ($location in $locations) {
        $allFindings += New-Finding -File $location -Rule "SKILL_NAME_DUPLICATED" -Detail ("Nome de skill duplicado: {0}" -f $skillName)
    }
}

$errorFindings = @($allFindings | Where-Object { $_.Severity -ne "WARN" })
$warningFindings = @($allFindings | Where-Object { $_.Severity -eq "WARN" })

Write-Host "=== GOVERNANCA DE SKILLS ==="
Write-Host ("Arquivos analisados: " + $skillFiles.Count)
Write-Host ("Erros: " + $errorFindings.Count)
Write-Host ("Warnings: " + $warningFindings.Count)
Write-Host ""

if ($skillFiles.Count -eq 0) {
    Write-Host "[ERRO] Nenhuma SKILL.md encontrada em .github/skills." -ForegroundColor Red
    exit 2
}

if ($allFindings.Count -eq 0) {
    Write-Host "[OK] Skills em conformidade com a governanca canonica."
    exit 0
}

if ($errorFindings.Count -gt 0) {
    Write-Host "-- ERROS --" -ForegroundColor Red
    $errorFindings |
    Sort-Object File, Rule, Detail |
    Select-Object File, Rule, Detail |
    Format-Table -Wrap -AutoSize |
    Out-Host
}

if ($warningFindings.Count -gt 0) {
    Write-Host "-- WARNINGS --" -ForegroundColor Yellow
    $warningFindings |
    Sort-Object File, Rule, Detail |
    Select-Object File, Rule, Detail |
    Format-Table -Wrap -AutoSize |
    Out-Host
}

if ($errorFindings.Count -gt 0) {
    exit 2
}

exit 0
