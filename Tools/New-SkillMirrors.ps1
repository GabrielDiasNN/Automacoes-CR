[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$BasePath = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

<#
.SYNOPSIS
    Recria os mirrors de skills como junctions apontando para as fontes canonicas.
.DESCRIPTION
    O repositorio tem duas fontes VERSIONADAS de skills:
      - `.github/skills`  -> skills de padrao (norma escrita, taxonomia ativa)
      - `.claude/skills`  -> skills operacionais do projeto (comandos executaveis)

    Cada ferramenta de agente le de um caminho fixo proprio, entao as fontes sao
    expostas por mirrors, que NAO sao versionados (ver .gitignore):
      - `.gemini/skills`  -> junctions para `.github/skills`
      - `.agents/skills`  -> junctions para `.claude/skills`

    Sem este script, um clone limpo nao tem mirror algum e
    `Tools/Test-SkillsGovernance.ps1` reprova com GEMINI_SKILL_MIRROR_MISSING.
    Rode-o apos clonar o repositorio ou depois de criar/renomear uma skill.

    Idempotente: junction ja correta e preservada. Mirror que for copia real ou
    apontar para o alvo errado so e substituido com -Force — mirror e alias da
    fonte canonica, e sobrescrever sem pedir esconderia edicao feita no lugar errado.
.EXAMPLE
    pwsh -File Tools\New-SkillMirrors.ps1
.EXAMPLE
    pwsh -File Tools\New-SkillMirrors.ps1 -Force
#>

if ([string]::IsNullOrWhiteSpace($BasePath)) {
    $BasePath = Split-Path -Parent $PSScriptRoot
    if (-not $BasePath) { $BasePath = "." }
}

$script:ExitCode = 0

# Cada par declara uma fonte versionada e o mirror que a expoe a outro agente.
$mirrorPairs = @(
    [pscustomobject]@{
        SourceRelative = ".github\skills"
        MirrorRelative = ".gemini\skills"
        Description    = "skills de padrao"
    },
    [pscustomobject]@{
        SourceRelative = ".claude\skills"
        MirrorRelative = ".agents\skills"
        Description    = "skills operacionais"
    }
)

function Get-LinkTarget {
    param([string]$Path)

    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if ($null -eq $item) { return $null }
    if ([string]::IsNullOrWhiteSpace($item.LinkType)) { return $null }
    # No PowerShell 5.1 (runtime de producao deste repo) FileSystemInfo.Target de uma
    # junction e uma COLECAO: comparar o array com -ieq devolve os elementos que casam
    # (truthy por acidente) e interpolar imprime com espaco entre eles. @()[0] normaliza
    # para a string do alvo unico, valido tambem no PS 7, onde ja e string.
    return @($item.Target)[0]
}

function Sync-SkillMirror {
    param(
        [string]$SourceRoot,
        [string]$MirrorRoot,
        [string]$SkillName
    )

    $sourcePath = Join-Path $SourceRoot $SkillName
    $mirrorPath = Join-Path $MirrorRoot $SkillName
    $resolvedSource = (Resolve-Path -LiteralPath $sourcePath).Path

    if (Test-Path -LiteralPath $mirrorPath) {
        $target = Get-LinkTarget -Path $mirrorPath

        if ($target -and ($target -ieq $resolvedSource)) {
            Write-Host ("  [ok]     {0}" -f $SkillName)
            return
        }

        $motivo = if ($target) { "aponta para $target" } else { "e copia real, nao link" }

        if (-not $Force) {
            Write-Warning ("  [manter] {0}: {1}. Use -Force para substituir pelo link." -f $SkillName, $motivo)
            $script:ExitCode = 1
            return
        }

        if ($PSCmdlet.ShouldProcess($mirrorPath, "Remover mirror divergente")) {
            # Directory.Delete nao segue a junction: remove o link, nunca o alvo.
            if ($target) {
                [System.IO.Directory]::Delete($mirrorPath, $true)
            } else {
                Remove-Item -LiteralPath $mirrorPath -Recurse -Force
            }
            Write-Host ("  [refeito] {0}: {1}" -f $SkillName, $motivo)
        }
    }

    if ($PSCmdlet.ShouldProcess($mirrorPath, "Criar junction para $resolvedSource")) {
        New-Item -ItemType Junction -Path $mirrorPath -Target $resolvedSource | Out-Null
        Write-Host ("  [criado] {0}" -f $SkillName)
    }
}

Write-Host "=== MIRRORS DE SKILLS ==="

foreach ($pair in $mirrorPairs) {
    $sourceRoot = Join-Path $BasePath $pair.SourceRelative
    $mirrorRoot = Join-Path $BasePath $pair.MirrorRelative

    Write-Host ""
    Write-Host ("{0} -> {1} ({2})" -f $pair.SourceRelative, $pair.MirrorRelative, $pair.Description)

    if (-not (Test-Path -LiteralPath $sourceRoot)) {
        Write-Warning ("  fonte ausente: {0} — nada a espelhar." -f $pair.SourceRelative)
        $script:ExitCode = 1
        continue
    }

    if (-not (Test-Path -LiteralPath $mirrorRoot)) {
        if ($PSCmdlet.ShouldProcess($mirrorRoot, "Criar diretorio de mirror")) {
            New-Item -ItemType Directory -Force -Path $mirrorRoot | Out-Null
        }
    }

    $skills = @(Get-ChildItem -LiteralPath $sourceRoot -Directory | Sort-Object Name)
    if ($skills.Count -eq 0) {
        Write-Warning ("  nenhuma skill em {0}." -f $pair.SourceRelative)
        continue
    }

    foreach ($skill in $skills) {
        Sync-SkillMirror -SourceRoot $sourceRoot -MirrorRoot $mirrorRoot -SkillName $skill.Name
    }

    # Mirror sem fonte correspondente vira achado ORPHAN na governanca; sinalizar aqui
    # evita que o operador descubra so' no gate.
    $orfaos = @(Get-ChildItem -LiteralPath $mirrorRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { -not (Test-Path -LiteralPath (Join-Path $sourceRoot $_.Name)) })
    foreach ($orfao in $orfaos) {
        Write-Warning ("  [orfao]  {0}: sem correspondente em {1}." -f $orfao.Name, $pair.SourceRelative)
        $script:ExitCode = 1
    }
}

Write-Host ""
if ($script:ExitCode -eq 0) {
    Write-Host "[OK] Mirrors de skills sincronizados."
} else {
    Write-Host "[ATENCAO] Ha mirror divergente ou orfao — veja os avisos acima."
}

exit $script:ExitCode
