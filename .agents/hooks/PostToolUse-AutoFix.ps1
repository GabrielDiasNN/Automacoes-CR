#Requires -Version 5.1
<#
.SYNOPSIS
    Hook PostToolUse para o Antigravity: valida e auto-corrige arquivos modificados.

.DESCRIPTION
    Aplica auto-correcoes e validacoes imediatas apos chamadas de escrita:
    1. PowerShell (.ps1, .psm1): garante presenca de UTF-8 with BOM (bytes 0xEF, 0xBB, 0xBF).
    2. Python (.py): executa black e isort para manter conformidade de estilo.
    3. Markdown (.md): valida ausencia de caracteres corrompidos (mojibake).

.INPUTS
    JSON via stdin com o contexto da ferramenta recem-executada.

.OUTPUTS
    JSON vazio {} via stdout (conforme especificacao do Antigravity).
#>
[CmdletBinding()]
param()

# 'Continue', nao 'SilentlyContinue': erro nao-terminante de cmdlet (ex.: a
# descoberta de $repoRoot abaixo, que nao esta sob nenhum try/catch) fica
# visivel em stderr em vez de sumir — o mesmo principio do resto do arquivo,
# que reporta cada falha de auto-fix em vez de engoli-la.
$ErrorActionPreference = 'Continue'

function Read-StdinPayload {
    try {
        $raw = [Console]::In.ReadToEnd()
        if ([string]::IsNullOrWhiteSpace($raw)) {
            return $null
        }
        return ($raw | ConvertFrom-Json)
    }
    catch [System.Exception] {
        [Console]::Error.WriteLine(
            ("[WARN PostToolUse] Payload stdin ilegivel: {0}" -f $_.Exception.Message))
        return $null
    }
}

$payload = Read-StdinPayload

if ($null -ne $payload) {
    $targetFile = ""
    $toolArgs = $null
    if ($payload.PSObject.Properties.Name -contains "toolCall" -and $null -ne $payload.toolCall.args) {
        $toolArgs = $payload.toolCall.args
    } elseif ($payload.PSObject.Properties.Name -contains "args" -and $null -ne $payload.args) {
        $toolArgs = $payload.args
    }

    if ($null -ne $toolArgs) {
        if ($toolArgs.PSObject.Properties.Name -contains "TargetFile") {
            $targetFile = [string]$toolArgs.TargetFile
        } elseif ($toolArgs.PSObject.Properties.Name -contains "targetFile") {
            $targetFile = [string]$toolArgs.targetFile
        } elseif ($toolArgs.PSObject.Properties.Name -contains "target_file") {
            $targetFile = [string]$toolArgs.target_file
        } elseif ($toolArgs.PSObject.Properties.Name -contains "file_path") {
            $targetFile = [string]$toolArgs.file_path
        }
    }

    $repoRoot = $PSScriptRoot
    while (-not (Test-Path (Join-Path $repoRoot ".git")) -and -not [string]::IsNullOrEmpty($repoRoot)) {
        $parent = [System.IO.Path]::GetDirectoryName($repoRoot)
        if ($parent -eq $repoRoot) { break }
        $repoRoot = $parent
    }
    if ([string]::IsNullOrEmpty($repoRoot)) { $repoRoot = "." }

    if (-not [string]::IsNullOrWhiteSpace($targetFile)) {
        if (-not [System.IO.Path]::IsPathRooted($targetFile)) {
            $targetFile = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $targetFile))
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($targetFile) -and (Test-Path -LiteralPath $targetFile -PathType Leaf)) {
        $ext = [System.IO.Path]::GetExtension($targetFile).ToLowerInvariant()

        # 1. PowerShell: Auto-correcao de BOM segura (sem corromper UTF-16)
        if ($ext -in @(".ps1", ".psm1")) {
            try {
                $bytes = [System.IO.File]::ReadAllBytes($targetFile)
                $hasUtf8Bom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
                if (-not $hasUtf8Bom) {
                    $isUtf16Le = ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE)
                    $isUtf16Be = ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFE -and $bytes[1] -eq 0xFF)
                    if ($isUtf16Le) {
                        $text = [System.Text.Encoding]::Unicode.GetString($bytes, 2, $bytes.Length - 2)
                        [System.IO.File]::WriteAllText($targetFile, $text, [System.Text.UTF8Encoding]::new($true))
                    } elseif ($isUtf16Be) {
                        $text = [System.Text.Encoding]::BigEndianUnicode.GetString($bytes, 2, $bytes.Length - 2)
                        [System.IO.File]::WriteAllText($targetFile, $text, [System.Text.UTF8Encoding]::new($true))
                    } elseif ($bytes.Length -eq 0) {
                        # Arquivo vazio: nada para carimbar. Prefixar BOM
                        # sozinho criaria um arquivo de 3 bytes que deixa de
                        # ser detectavel como vazio por qualquer logica
                        # downstream que confira Length -eq 0.
                    } else {
                        # So' carimba BOM se o corpo ja' decodifica como UTF-8
                        # valido. Sem esta checagem, um .ps1 gravado por
                        # `Set-Content` do PS 5.1 sem `-Encoding` (que grava
                        # acentos como CP-1252 de 1 byte, nao UTF-8) recebia o
                        # BOM colado na frente sem transcodificar: o arquivo
                        # passava a se ANUNCIAR UTF-8 com corpo que nao e' —
                        # pior do que nao ter BOM, porque mascara
                        # POWERSHELL_BOM_MISSING sem corrigir o encoding real.
                        # Mesmo decoder estrito de Tools/Test-SourceEncoding.ps1.
                        $utf8Strict = New-Object System.Text.UTF8Encoding($false, $true)
                        try {
                            [void]$utf8Strict.GetString($bytes)
                            $bom = [byte[]]@(0xEF, 0xBB, 0xBF)
                            $newBytes = New-Object byte[] ($bom.Length + $bytes.Length)
                            [System.Buffer]::BlockCopy($bom, 0, $newBytes, 0, $bom.Length)
                            [System.Buffer]::BlockCopy($bytes, 0, $newBytes, $bom.Length, $bytes.Length)
                            [System.IO.File]::WriteAllBytes($targetFile, $newBytes)
                        }
                        catch [System.Text.DecoderFallbackException] {
                            [Console]::Error.WriteLine(
                                ("[WARN PostToolUse] {0} nao decodifica como UTF-8 valido; BOM NAO foi adicionado para nao mascarar a corrupcao de encoding." -f $targetFile))
                        }
                    }
                }
            }
            catch [System.Exception] {
                [Console]::Error.WriteLine(
                    ("[WARN PostToolUse] Falha ao normalizar BOM de {0}: {1}" -f $targetFile, $_.Exception.Message))
            }
        }

        # 2. Python: Formatacao via black e isort do ambiente virtual
        if ($ext -eq ".py") {
            try {
                $py = Join-Path $repoRoot ".venv\Scripts\python.exe"
                if (Test-Path -LiteralPath $py) {
                    # Ordem canonica: isort primeiro (ordena imports), black
                    # depois (formata o resultado). O inverso deixa o black
                    # reprovar o que o isort ainda vai mexer.
                    #
                    # Falha de processo nativo nao lanca excecao: sem checar o
                    # exit code, um black que rejeita o arquivo (sintaxe
                    # incompleta no meio de uma sequencia de edicoes) passaria
                    # despercebido justamente quando o aviso importa.
                    foreach ($tool in @("isort", "black")) {
                        $toolOut = & $py -m $tool -q $targetFile 2>&1
                        if ($LASTEXITCODE -ne 0) {
                            [Console]::Error.WriteLine(
                                ("[WARN PostToolUse] {0} retornou {1} em {2}: {3}" -f $tool, $LASTEXITCODE, $targetFile, ($toolOut -join " ")))
                        }
                    }
                }
            }
            catch [System.Exception] {
                [Console]::Error.WriteLine(
                    ("[WARN PostToolUse] black/isort falhou em {0}: {1}" -f $targetFile, $_.Exception.Message))
            }
        }

        # 3. Markdown: Verificacao de integridade contra caracteres mojibake
        if ($ext -eq ".md") {
            try {
                $bytes = [System.IO.File]::ReadAllBytes($targetFile)
                $text = [System.Text.Encoding]::UTF8.GetString($bytes)
                $clean = [regex]::Replace($text, '(?s)```.*?```', '')
                $clean = [regex]::Replace($clean, '`[^`]*`', '')
                $c3 = [string][char]0x00C3
                $c2Space = [string]([char]0x00C2) + " "
                $e2euro = [string]([char]0x00E2) + [char]0x20AC
                if ($clean -match ([regex]::Escape($c3) + '[\x80-\xBF]') -or $clean.Contains($c2Space) -or $clean.Contains($e2euro)) {
                    [Console]::Error.WriteLine(("[WARN PostToolUse] Caracteres corrompidos (mojibake) detectados em: {0}" -f $targetFile))
                }
            }
            catch [System.Exception] {
                [Console]::Error.WriteLine(
                    ("[WARN PostToolUse] Falha ao checar mojibake em {0}: {1}" -f $targetFile, $_.Exception.Message))
            }
        }
    }
}

# Retorna objeto JSON vazio no stdout conforme o contrato do Antigravity
[Console]::Out.WriteLine("{}")
exit 0
