[CmdletBinding()]
param(
    [string]$RootPath = (Join-Path $PSScriptRoot ".."),
    [switch]$StagedOnly,
    [string[]]$Paths = @()
)

$ErrorActionPreference = "Stop"

$resolvedRoot = (Resolve-Path -LiteralPath $RootPath).Path
$auditPath = Join-Path $resolvedRoot "Audit\vba"

function Write-HookLog {
    param([string]$Level, [string]$Message)
    Write-Host "[$Level] $Message"
}

function Convert-ToRepoRelativePath {
    param(
        [string]$Path,
        [string]$RepositoryRoot
    )

    $rootNorm = [System.IO.Path]::GetFullPath($RepositoryRoot)
    $pathNorm = [System.IO.Path]::GetFullPath($Path)

    if ($pathNorm.StartsWith($rootNorm, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $pathNorm.Substring($rootNorm.Length).TrimStart('\', '/').Replace('\', '/')
    }

    return $Path.Replace('\', '/')
}

# Compara conteudo ignorando diferencas de line ending (CRLF vs LF)
function Get-NormalizedHash {
    param([string]$FilePath)
    if (-not (Test-Path -LiteralPath $FilePath)) { return $null }
    try {
        $raw = [System.IO.File]::ReadAllBytes($FilePath)
        # Remove todos os CR (0x0D) - normaliza CRLF/CR para LF
        $cleaned = [byte[]]($raw | Where-Object { $_ -ne 13 })
        $sha = [System.Security.Cryptography.SHA256]::Create()
        $hash = $sha.ComputeHash($cleaned)
        return ([BitConverter]::ToString($hash)) -replace '-', ''
    }
    catch [System.Exception] { return $null }
}

# ------------------------------------------------------------------
# 1. Obter lista de arquivos staged (apenas se -StagedOnly)
# ------------------------------------------------------------------
$targetFiles = @()
if ($Paths.Count -gt 0) {
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
        if ($ext -notin @('.bas', '.cls')) {
            continue
        }

        $targetFiles += (Convert-ToRepoRelativePath -Path $candidate -RepositoryRoot $resolvedRoot)
    }

    $targetFiles = @($targetFiles | Sort-Object -Unique)
    if ($targetFiles.Count -eq 0) {
        Write-HookLog "INFO" "Nenhum arquivo .bas/.cls selecionado em -Paths. Verificacao VBA ignorada."
        exit 0
    }

    Write-HookLog "INFO" "$($targetFiles.Count) arquivo(s) VBA recebidos via -Paths: $($targetFiles -join ', ')"
}
elseif ($StagedOnly) {
    $gitOut = git diff --cached --name-only --diff-filter=ACM 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-HookLog "WARN" "Nao foi possivel obter staged files via git. Verificando todos."
        $StagedOnly = $false
    }
    else {
        $targetFiles = @($gitOut | Where-Object { $_ -match '\.(bas|cls)$' } | ForEach-Object { $_.Trim().Replace('\', '/') })
        if ($targetFiles.Count -eq 0) {
            Write-HookLog "INFO" "Nenhum arquivo .bas/.cls staged. Verificacao VBA ignorada."
            exit 0
        }
        Write-HookLog "INFO" "$($targetFiles.Count) arquivo(s) VBA staged: $($targetFiles -join ', ')"
    }
}

# ------------------------------------------------------------------
# 2. Coletar manifests de Audit/vba/
# ------------------------------------------------------------------
if (-not (Test-Path -LiteralPath $auditPath)) {
    Write-HookLog "WARN" "Audit/vba/ nao encontrado em: $auditPath. Verificacao ignorada."
    exit 0
}

$manifests = Get-ChildItem -LiteralPath $auditPath -Recurse -File -Filter "vba-manifest.json" -ErrorAction SilentlyContinue
if (-not $manifests -or $manifests.Count -eq 0) {
    Write-HookLog "WARN" "Nenhum vba-manifest.json encontrado. Verificacao ignorada."
    exit 2
}

# ------------------------------------------------------------------
# 3. Comparar modulos por hash SHA-256
# ------------------------------------------------------------------
$driftItems = @()

foreach ($manifestFile in $manifests) {
    $manifest = Get-Content -LiteralPath $manifestFile.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    $sourceRel = [string]$manifest.sourcePath
    $sourceDir = Split-Path $sourceRel -Parent
    $repoFolder = if ([string]::IsNullOrWhiteSpace($sourceDir)) { $resolvedRoot } else { Join-Path $resolvedRoot $sourceDir }
    $auditFolder = Split-Path -Parent $manifestFile.FullName

    # Classes canonicas compartilhadas via _Shared/VBA/ - presentes nos xlsm
    # mas sem copia local nos projetos RB/RE (Montagem mantem copia direta).
    $sharedVbaDir = Join-Path $resolvedRoot "_Shared\VBA"

    foreach ($component in $manifest.components) {
        if ($component.type -notin @("StdModule", "ClassModule")) { continue }

        $fileName = "{0}{1}" -f $component.name, $component.extension
        $repoFile = Join-Path $repoFolder $fileName
        $auditFile = Join-Path $auditFolder $fileName

        # Quando -StagedOnly, ignorar arquivos nao staged
        if ($StagedOnly -or $Paths.Count -gt 0) {
            $relPath = $repoFile.Replace($resolvedRoot, "").TrimStart("\", "/").Replace("\", "/")
            $isSelected = $targetFiles | Where-Object { $_ -eq $relPath -or $_ -like "*$fileName" }
            if (-not $isSelected) { continue }
        }

        if (-not (Test-Path -LiteralPath $repoFile)) {
            # Ignorar classe canonica que existe em _Shared/VBA/
            $sharedFile = Join-Path $sharedVbaDir $fileName
            if (Test-Path -LiteralPath $sharedFile) { continue }
            $driftItems += [PSCustomObject]@{ Status = "MissingInRepo"; Module = $fileName; Source = $sourceRel }
            continue
        }
        if (-not (Test-Path -LiteralPath $auditFile)) {
            $driftItems += [PSCustomObject]@{ Status = "MissingInAudit"; Module = $fileName; Source = $sourceRel }
            continue
        }

        $hashRepo = Get-NormalizedHash -FilePath $repoFile
        $hashAudit = Get-NormalizedHash -FilePath $auditFile

        if ($hashRepo -ne $hashAudit) {
            $driftItems += [PSCustomObject]@{ Status = "Different"; Module = $fileName; Source = $sourceRel }
        }
    }
}

# ------------------------------------------------------------------
# 4. Resultado
# ------------------------------------------------------------------
if ($driftItems.Count -eq 0) {
    Write-HookLog "OK" "VBA sincronizado com Audit/vba/. Nenhum drift detectado."
    exit 0
}

Write-HookLog "ERRO" "Drift VBA detectado - arquivos .bas/.cls nao sincronizados com o XLSM:"
foreach ($item in $driftItems) {
    Write-HookLog "ERRO" "  [$($item.Status)] $($item.Source) :: $($item.Module)"
}

Write-Host ""
Write-Host "Para corrigir, execute o workflow de sincronizacao:"
Write-Host "  1. Importe no XLSM:  pwsh -File Tools\SincronizarProjetoVba.ps1 -WorkbookPath 'arquivo.xlsm'"
Write-Host "  2. Exporte Auditoria: pwsh -File Tools\ExportarAuditoriaXlsm.ps1"
Write-Host "  3. Stage os arqs:    git add Audit/vba/"
Write-Host ""
exit 1

<#
.SYNOPSIS
    Detecta drift entre os arquivos .bas/.cls no repositorio e as capturas em Audit/vba/.

.DESCRIPTION
    Verifica se os arquivos VBA (.bas/.cls) que estao staged para commit diferem dos
    snapshots exportados em Audit/vba/. Um "diff" indica que houve edicao na fonte
    sem o workflow completo: importar no xlsm -> exportar auditoria.

    Usa o compare-report.json gerado por CompararVbaModulos.ps1 como base de comparacao.

.PARAMETER RootPath
    Caminho raiz do repositorio. Padrao: pasta-pai do script.

.PARAMETER StagedOnly
    Quando informado, verifica drift somente para arquivos .bas/.cls staged no git.
    Sem esta flag, verifica todos os modulos rastreados pelos manifests.

.PARAMETER Paths
    Lista explicita de arquivos para verificar no lugar do modo staged. Aceita caminhos
    relativos ao repositorio ou absolutos. Em CI, use esta opcao para espelhar o
    comportamento do pre-commit sobre os arquivos alterados do PR/push.

.OUTPUTS
    Exit 0 = nenhum drift detectado.
    Exit 1 = drift detectado (commit deve ser bloqueado).
    Exit 2 = pre-condicao falhou (ex.: sem manifests).

.EXAMPLE
    pwsh -File Tools\Test-VbaDrift.ps1 -StagedOnly

.EXAMPLE
    pwsh -File Tools\Test-VbaDrift.ps1 -Paths "Montagem de Terceirizados/modMain.bas"

.NOTES
    A ferramenta valida a integridade do codigo VBA antes do commit.
    Certifique-se de usar caminhos relativos ao repositorio.
#>

