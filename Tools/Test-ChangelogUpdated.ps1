<#
.SYNOPSIS
    Valida que mudancas de codigo em PR vem acompanhadas de atualizacao do CHANGELOG.md.

.DESCRIPTION
    Recebe a lista de arquivos alterados no diff. Se houver arquivo de codigo
    (extensoes governadas) e o CHANGELOG.md nao estiver no diff, falha com
    orientacao. Mudancas exclusivas de documentacao, configuracao de CI ou
    testes nao exigem CHANGELOG.

    Override: passar -AllowSkip (usado pelo CI quando o titulo do PR contem
    o marcador [skip-changelog]).

.NOTES
    Skill: protocolo-valeg | Versao: 1.0.0
#>
[CmdletBinding()]
param(
    [string[]]$Paths = @(),
    [switch]$AllowSkip
)

$ErrorActionPreference = "Stop"

Write-Host "=== GOVERNANCA DE CHANGELOG ==="

if ($AllowSkip) {
    Write-Host "[SKIP] Override de changelog autorizado ([skip-changelog])."
    exit 0
}

$normalizedPaths = @(
    $Paths |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
        ForEach-Object { $_.Trim().Replace('\', '/') }
)

if ($normalizedPaths.Count -eq 0) {
    Write-Host "[OK] Nenhum arquivo alterado informado; validacao de changelog nao se aplica."
    exit 0
}

$codePatterns = @(
    '\.py$',
    '\.(ps1|psm1|psd1)$',
    '\.(js|mjs|cjs)$',
    '\.sql$'
)

$exemptPatterns = @(
    '^\.github/',
    '^docs/',
    '^lib/tests/',
    '/tests?/',
    '^Orchestrator/tests/',
    '\.Tests\.ps1$',
    '^_Template/'
)

$codeChanges = @(
    $normalizedPaths | Where-Object {
        $path = $_
        $isCode = $false
        foreach ($pattern in $codePatterns) {
            if ($path -match $pattern) {
                $isCode = $true
                break
            }
        }

        if (-not $isCode) {
            return $false
        }

        foreach ($pattern in $exemptPatterns) {
            if ($path -match $pattern) {
                return $false
            }
        }

        return $true
    }
)

if ($codeChanges.Count -eq 0) {
    Write-Host "[OK] Nenhuma mudanca de codigo elegivel; CHANGELOG.md nao e exigido."
    exit 0
}

$changelogTouched = @($normalizedPaths | Where-Object { $_ -eq 'CHANGELOG.md' }).Count -gt 0

if ($changelogTouched) {
    Write-Host "[OK] CHANGELOG.md atualizado junto com as mudancas de codigo."
    exit 0
}

Write-Host "[ERRO] Mudancas de codigo detectadas sem atualizacao do CHANGELOG.md:"
foreach ($file in $codeChanges) {
    Write-Host (" - " + $file)
}
Write-Host ""
Write-Host "Adicione uma entrada ao CHANGELOG.md ou inclua [skip-changelog] no titulo do PR."
exit 1
