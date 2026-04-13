# ==============================================================================
# ARQUIVO: Test-VbaPtBrGovernance.ps1
# VERSAO : 1.0
# DESCRICAO: Valida governanca de texto PT-BR em codigo VBA:
#            1) Bloqueia caracteres nao-ASCII em .bas/.cls/.frm
#            2) Sinaliza termos sem acento em strings literais
# ==============================================================================

[CmdletBinding()]
param(
    [string]$BasePath = "C:\Automacoes",
    [switch]$FailOnTermWarnings
)

$ErrorActionPreference = "Stop"

function Get-VbaSourceFiles {
    param([string]$RootPath)

    $skipPathRegex = [regex]'\\(Audit|Logs|node_modules|\.git|\.wwebjs_auth)(\\|$)'

    Get-ChildItem -Path $RootPath -Recurse -File -Include *.bas, *.cls, *.frm |
    Where-Object {
        $full = $_.FullName
        return -not $skipPathRegex.IsMatch($full)
    }
}

function Get-FileTextCp1252 {
    param([string]$FilePath)

    $enc = [System.Text.Encoding]::GetEncoding(1252)
    return [System.IO.File]::ReadAllText($FilePath, $enc)
}

function Test-NonAsciiContent {
    param(
        [string]$FilePath,
        [string]$Content
    )

    $findings = @()
    $lines = [regex]::Split($Content, "`r`n|`n|`r")

    for ($i = 0; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]
        if ($line -cmatch '[^\x00-\x7F]') {
            $match = [regex]::Match($line, '[^\x00-\x7F]')
            $findings += [pscustomobject]@{
                File   = $FilePath
                Line   = $i + 1
                Column = $match.Index + 1
                Char   = $match.Value
                Rule   = "NON_ASCII_IN_VBE"
            }
        }
    }

    return $findings
}

function Get-QuotedLiterals {
    param([string]$Line)

    $results = @()
    $inLiteral = $false
    $startIndex = -1
    $i = 0

    while ($i -lt $Line.Length) {
        $ch = $Line[$i]

        if (-not $inLiteral) {
            if ($ch -eq '"') {
                $inLiteral = $true
                $startIndex = $i
            }

            $i++
            continue
        }

        if ($ch -eq '"') {
            if (($i + 1) -lt $Line.Length -and $Line[$i + 1] -eq '"') {
                # Aspas escapadas no literal VBA ("").
                $i += 2
                continue
            }

            $rawValue = $Line.Substring($startIndex + 1, $i - $startIndex - 1)
            $value = $rawValue.Replace('""', '"')

            $results += [pscustomobject]@{
                Value  = $value
                Column = $startIndex + 1
            }

            $inLiteral = $false
            $startIndex = -1
        }

        $i++
    }

    return $results
}

function Test-IsUserVisibleLiteral {
    param(
        [string]$FilePath,
        [string]$Line,
        [string]$LiteralText
    )

    # Excluir linhas de log tecnico para nao gerar falso positivo.
    if ($Line -match 'GravarLogEx|WriteLog|LOG_(INFO|WARN|WARNING|ERROR|DEBUG)|\bTRACE\b') {
        return $false
    }

    # Nomes tecnicos de colunas/sinonimos (ex.: DESTINATARIO, CONEXAO) nao sao texto exibido ao usuario final.
    if ($LiteralText -match '^[A-Z0-9_ ]+$') {
        return $false
    }

    if ($LiteralText -match '^\s*\|\s*[A-Za-z]+\s*=') {
        return $false
    }

    if ($Line -match 'ObterIndiceColunaPorSinonimos|CONFIG_TABLE_NAME|CONFIG_SHEET_NAME|TryGetRecipientFromConfig') {
        return $false
    }

    # Contextos explicitos de composicao de email/Outlook.
    if ($Line -match '\.Subject\s*=|strAssunto\s*=|GetEmailSubject\s*=|strIntro\s*=|strLegenda\s*=|ComposeHtmlBodyWithSignature|\.htmlBody\s*=|\.HTMLBody\s*=|MontarTemplateEmail|BuildIntroMarkup|BuildLegendaMarkup') {
        return $true
    }

    # Literais HTML em geral sao parte de corpo de email visivel ao usuario.
    if ($LiteralText -match '<[^>]+>') {
        return $true
    }

    # Pistas comuns de texto de interface no email.
    if ($LiteralText -match 'Segue\s+relatorio|Atenciosamente|Aten\w+|Relatorio\s+Semanal|Conferencia|Maquina|Maquinas|Quimicos|Fisica') {
        return $true
    }

    return $false
}

function Test-UnaccentedTermsInStrings {
    param(
        [string]$FilePath,
        [string]$Content
    )

    # Regras de negocio: texto visivel deve sair PT-BR correto.
    $termRules = @(
        @{ Pattern = '\bRelatorio\b'; Suggestion = 'Relatorio -> Relatorio (usar ChrW no plain text ou entidade HTML)'; Canonical = 'Relatorio' },
        @{ Pattern = '\bConferencia\b'; Suggestion = 'Conferencia -> Conferencia (usar ChrW no plain text ou entidade HTML)'; Canonical = 'Conferencia' },
        @{ Pattern = '\bMaquina\b'; Suggestion = 'Maquina -> Maquina (usar ChrW ou entidade HTML)'; Canonical = 'Maquina' },
        @{ Pattern = '\bMaquinas\b'; Suggestion = 'Maquinas -> Maquinas (usar ChrW ou entidade HTML)'; Canonical = 'Maquinas' },
        @{ Pattern = '\bQuimicos\b'; Suggestion = 'Quimicos -> Quimicos (usar ChrW ou entidade HTML)'; Canonical = 'Quimicos' },
        @{ Pattern = '\bFisica\b'; Suggestion = 'Fisica -> Fisica (usar ChrW ou entidade HTML)'; Canonical = 'Fisica' },
        @{ Pattern = '\bDestinatario\b'; Suggestion = 'Destinatario -> Destinatario (usar ChrW ou entidade HTML)'; Canonical = 'Destinatario' },
        @{ Pattern = '\bDestinatarios\b'; Suggestion = 'Destinatarios -> Destinatarios (usar ChrW ou entidade HTML)'; Canonical = 'Destinatarios' },
        @{ Pattern = '\bConexao\b'; Suggestion = 'Conexao -> Conexao (usar ChrW ou entidade HTML)'; Canonical = 'Conexao' },
        @{ Pattern = '\bnao\b'; Suggestion = 'nao -> nao (avaliar contexto e acentuar na saida)'; Canonical = 'nao' },
        @{ Pattern = '\bvalido\b'; Suggestion = 'valido -> valido (avaliar contexto e acentuar na saida)'; Canonical = 'valido' },
        @{ Pattern = '\binvalido\b'; Suggestion = 'invalido -> invalido (avaliar contexto e acentuar na saida)'; Canonical = 'invalido' }
    )

    $findings = @()
    $lines = [regex]::Split($Content, "`r`n|`n|`r")

    for ($i = 0; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]

        if ($line.TrimStart().StartsWith("'")) {
            continue
        }

        $literals = Get-QuotedLiterals -Line $line
        foreach ($literal in $literals) {
            $text = $literal.Value

            if (-not (Test-IsUserVisibleLiteral -FilePath $FilePath -Line $line -LiteralText $text)) {
                continue
            }

            foreach ($rule in $termRules) {
                if ($text -match $rule.Pattern) {
                    $findings += [pscustomobject]@{
                        File       = $FilePath
                        Line       = $i + 1
                        Column     = $literal.Column
                        Rule       = "PTBR_UNACCENTED_TERM"
                        Term       = $rule.Canonical
                        Suggestion = $rule.Suggestion
                        Snippet    = $text
                    }
                }
            }
        }
    }

    return $findings
}

function Convert-ToRelativePath {
    param([string]$Path, [string]$Root)

    $rootNorm = [System.IO.Path]::GetFullPath($Root)
    $fileNorm = [System.IO.Path]::GetFullPath($Path)

    if ($fileNorm.StartsWith($rootNorm, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $fileNorm.Substring($rootNorm.Length).TrimStart('\\')
    }

    return $Path
}

$files = Get-VbaSourceFiles -RootPath $BasePath

$nonAsciiFindings = @()
$termFindings = @()

foreach ($file in $files) {
    $content = Get-FileTextCp1252 -FilePath $file.FullName

    $nonAsciiFindings += Test-NonAsciiContent -FilePath $file.FullName -Content $content
    $termFindings += Test-UnaccentedTermsInStrings -FilePath $file.FullName -Content $content
}

foreach ($f in $nonAsciiFindings) {
    $f.File = Convert-ToRelativePath -Path $f.File -Root $BasePath
}

foreach ($f in $termFindings) {
    $f.File = Convert-ToRelativePath -Path $f.File -Root $BasePath
}

Write-Host "=== GOVERNANCA PT-BR VBA ==="
Write-Host ("Arquivos analisados: " + $files.Count)
Write-Host ("Nao-ASCII em VBE: " + $nonAsciiFindings.Count)
Write-Host ("Termos sem acento (warning): " + $termFindings.Count)
Write-Host ""

if ($nonAsciiFindings.Count -gt 0) {
    Write-Host "-- BLOQUEIOS: NON_ASCII_IN_VBE --" -ForegroundColor Red
    $nonAsciiFindings |
    Select-Object File, Line, Column, Char, Rule |
    Format-Table -AutoSize |
    Out-Host
    Write-Host ""
}

if ($termFindings.Count -gt 0) {
    Write-Host "-- ALERTAS: PTBR_UNACCENTED_TERM --" -ForegroundColor Yellow
    $termFindings |
    Select-Object File, Line, Term, Snippet |
    Format-Table -AutoSize |
    Out-Host
    Write-Host ""
}

if ($nonAsciiFindings.Count -gt 0) {
    exit 2
}

if ($FailOnTermWarnings -and $termFindings.Count -gt 0) {
    exit 3
}

exit 0
