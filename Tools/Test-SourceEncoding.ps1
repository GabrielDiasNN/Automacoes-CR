# ==============================================================================

# ARQUIVO: Test-SourceEncoding.ps1

# VERSAO : 1.0.0

# DESCRICAO: Guardrail de Codificacao de Fonte (Governanca AI-Native).

#            Verifica se scripts PS1 e PY possuem apenas caracteres ASCII.

#            Isso garante que o codigo-fonte seja imune a variacoes de encoding.

#            Acentuacao PT-BR deve ser feita via Base64 ou Escape Sequences.

# ==============================================================================



[CmdletBinding()]

param(

    [string]$RootPath = "C:\Automacoes",

    [switch]$StagedOnly

)



# Bibliotecas Core

$libLogging = Join-Path $RootPath "lib\Lib-Logging.psm1"

if (Test-Path $libLogging) { Import-Module $libLogging -Force }



function Write-Log {

    param([string]$m, [string]$l = "INFO")

    if (Get-Command Write-AutomacaoLog -ErrorAction SilentlyContinue) {

        Write-AutomacaoLog -Message $m -Level $l -LogPath (Join-Path $RootPath "Logs\Governance_Encoding.log")

    } else {

        Write-Host "[$l] $m"

    }

}



Write-Log "INICIO - Auditoria de Encoding ASCII-Safe. Root=$RootPath"



# Identifica arquivos para auditar

$files = if ($StagedOnly) {

    git diff --cached --name-only --diff-filter=d | Where-Object { $_ -match '\.(ps1|psm1|py)$' } | ForEach-Object { Join-Path $RootPath $_ }

} else {

    Get-ChildItem -Path $RootPath -Recurse -Include *.ps1, *.psm1, *.py | 

    Where-Object { $_.FullName -notmatch 'node_modules|\.venv|\.git' } |

    Select-Object -ExpandProperty FullName

}



if (-not $files) {

    Write-Log "Nenhum arquivo para validar encoding."

    exit 0

}



$violations = 0



foreach ($f in $files) {

    if (-not (Test-Path $f)) { continue }

    

    $bytes = [System.IO.File]::ReadAllBytes($f)

    $hasNonAscii = $false

    $lineNum = 1

    

    # Le o arquivo linha a linha (binario) para achar o caractere exato

    $content = Get-Content $f -Encoding UTF8

    for ($i = 0; $i -lt $content.Count; $i++) {

        $line = $content[$i]

        if ($line -match '[^\x00-\x7F]') {

            $violations++

            $hasNonAscii = $true

            $charMatch = [regex]::Match($line, '[^\x00-\x7F]').Value

            Write-Log "BLOQUEIO: Caractere nao-ASCII ('$charMatch') detectado em $f na linha $($i+1)" -l "ERRO"

        }

    }

}



Write-Log "Auditoria concluida. Violacoes encontradas: $violations"



if ($violations -gt 0) {

    Write-Log "GOVERNANCA DE ENCODING REPROVADA. Use apenas ASCII no fonte." -l "ERRO"

    exit 1

} else {

    Write-Log "GOVERNANCA DE ENCODING APROVADA."

    exit 0

}

