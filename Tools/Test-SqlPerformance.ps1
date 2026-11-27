param(
    [string]$RootPath = "",
    [string[]]$Paths = @()
)

if ([string]::IsNullOrWhiteSpace($RootPath)) {
    $RootPath = Split-Path -Parent $PSScriptRoot
    if (-not $RootPath) { $RootPath = "." }
}
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) }
catch [System.IO.IOException] { Write-Verbose "Sem console para ajustar a codificacao: $($_.Exception.Message)" }
Write-Host "=== Governanca SQL (Performance Oracle) ==="

$explicitPaths = $Paths.Count -gt 0
$targetFiles = @()
if ($explicitPaths) {
    $targetFiles = @($Paths | Where-Object { $_ -match '\.sql$' })
} else {
    $targetFiles = @(git -C $RootPath -c core.quotepath=false ls-files "*.sql")
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERRO] Falha ao listar arquivos .sql via git ls-files (exit $LASTEXITCODE)." -ForegroundColor Red
        exit 1
    }
}

if ($targetFiles.Count -eq 0) {
    Write-Host "Nenhum arquivo SQL (.sql) para validar."
    exit 0
}

function Remove-SqlCommentsAndLiterals {
    param([string]$Sql)
    if ([string]::IsNullOrEmpty($Sql)) { return "" }
    $sb = New-Object System.Text.StringBuilder($Sql.Length)
    $n = $Sql.Length
    $i = 0
    while ($i -lt $n) {
        $c = $Sql[$i]
        if ($c -eq '-' -and ($i + 1) -lt $n -and $Sql[$i + 1] -eq '-') {
            $end = $Sql.IndexOf("`n", $i + 2)
            [void]$sb.Append(' ')
            if ($end -lt 0) { break }
            $i = $end + 1
            continue
        }
        if ($c -eq '/' -and ($i + 1) -lt $n -and $Sql[$i + 1] -eq '*') {
            $end = $Sql.IndexOf('*/', $i + 2, [System.StringComparison]::Ordinal)
            [void]$sb.Append(' ')
            if ($end -lt 0) { break }
            $i = $end + 2
            continue
        }
        $inicioToken = ($i -eq 0) -or (-not ($Sql[$i - 1] -match '[A-Za-z0-9_$#]'))
        if ($inicioToken -and ($c -eq 'q' -or $c -eq 'Q' -or $c -eq 'n' -or $c -eq 'N')) {
            $qStart = -1
            if (($c -eq 'n' -or $c -eq 'N') -and ($i + 2) -lt $n -and ($Sql[$i + 1] -eq 'q' -or $Sql[$i + 1] -eq 'Q') -and $Sql[$i + 2] -eq "'") {
                $qStart = $i + 1
            } elseif (($c -eq 'q' -or $c -eq 'Q') -and ($i + 1) -lt $n -and $Sql[$i + 1] -eq "'") {
                $qStart = $i
            }
            if ($qStart -ge 0 -and ($qStart + 2) -lt $n) {
                $delim = $Sql[$qStart + 2]
                if (-not [char]::IsWhiteSpace($delim)) {
                    $closer = switch ($delim) {
                        '[' { ']' }
                        '{' { '}' }
                        '(' { ')' }
                        '<' { '>' }
                        default { [string]$delim }
                    }
                    $end = $Sql.IndexOf(($closer + "'"), $qStart + 3, [System.StringComparison]::Ordinal)
                    if ($end -ge 0) {
                        [void]$sb.Append("''")
                        $i = $end + 2
                        continue
                    }
                }
            }
        }
        if ($c -eq "'") {
            $j = $i + 1
            while ($j -lt $n) {
                $j = $Sql.IndexOf("'", $j)
                if ($j -lt 0) {
                    $j = $n
                    break
                }
                if (($j + 1) -lt $n -and $Sql[$j + 1] -eq "'") {
                    $j += 2
                    continue
                }
                $j += 1
                break
            }
            [void]$sb.Append("''")
            $i = $j
            continue
        }
        if ($c -eq '"') {
            $end = $Sql.IndexOf('"', $i + 1)
            if ($end -lt 0) {
                [void]$sb.Append($Sql.Substring($i))
                break
            }
            [void]$sb.Append($Sql.Substring($i, ($end - $i + 1)))
            $i = $end + 1
            continue
        }
        [void]$sb.Append($c)
        $i++
    }
    return $sb.ToString()
}

$hasErrors = $false
$bannedSelectStarRegex = '(?i)\bSELECT\s+(?:(?:DISTINCT|ALL|UNIQUE)\s+)?\*'
$bannedAliasStarRegex = '(?i)(?<![\w$#])[A-Za-z_"][\w$#"]*(?:\s*\.\s*[A-Za-z_"][\w$#"]*)?\s*\.\s*\*'

foreach ($file in $targetFiles) {
    $file = $file.Trim('"')
    $fullPath = if ([System.IO.Path]::IsPathRooted($file)) { $file } else { Join-Path $RootPath $file }
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        if ($explicitPaths) {
            Write-Host "[ERRO] Arquivo SQL explicitado nao encontrado: $file" -ForegroundColor Red
            $hasErrors = $true
        }
        continue
    }

    $content = Get-Content -LiteralPath $fullPath -Raw
    $cleanContent = Remove-SqlCommentsAndLiterals -Sql $content
    if (($cleanContent -match $bannedSelectStarRegex) -or ($cleanContent -match $bannedAliasStarRegex)) {
        Write-Host "[ERRO] A query em '$file' contem 'SELECT *' ou 'alias.*'." -ForegroundColor Red
        Write-Host "  Motivo: 'SELECT *' viola a diretriz de Performance O(n) e Custo de Plano de Execucao." -ForegroundColor Red
        Write-Host "  Acao: Especifique as colunas explicitamente." -ForegroundColor Red
        $hasErrors = $true
    }
}

if ($hasErrors) {
    Write-Host "`n[FALHA] Foram encontrados erros de performance SQL. Corrija-os antes de commitar." -ForegroundColor Red
    exit 1
}

Write-Host "Validacao SQL concluida com sucesso." -ForegroundColor Green
exit 0

