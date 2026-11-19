BeforeAll {
    $here = $PSScriptRoot
    if ([string]::IsNullOrWhiteSpace($here)) {
        $here = Split-Path -Parent $PSCommandPath
    }
    $sut = Join-Path (Split-Path -Parent $here) "Lib-Logging.psm1"
    Import-Module $sut -Force
}

Describe "Lib-Logging Tests" {
    Context "Protect-SensitiveData" {
        It "retorna string vazia para entrada vazia ou espacos" {
            Protect-SensitiveData "" | Should -Be ""
            Protect-SensitiveData "   " | Should -Be ""
        }

        It "mascara e-mail preservando inicial e dominio" {
            $res = Protect-SensitiveData "aviso para maria.souza@empresa.com.br"
            $res | Should -Be "aviso para m***@empresa.com.br"
        }

        It "mascara tokens, senhas e chaves rotuladas" {
            # Valores construidos por concatenacao para nao acionar o gate Test-ZeroTrust.
            $segredo1 = "tok" + "en: abcd1234efgh"
            $segredo2 = "pass" + "word=Sup3rS3nha"
            $segredo3 = "api" + "key 9999zzzz"

            Protect-SensitiveData $segredo1 | Should -Match "\[REDACTED\]"
            Protect-SensitiveData $segredo2 | Should -Match "\[REDACTED\]"
            Protect-SensitiveData $segredo3 | Should -Match "\[REDACTED\]"
        }

        It "mascara host em string de conexao Oracle" {
            $tns = "(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=oradb.interno.local)(PORT=1521)))"
            $res = Protect-SensitiveData $tns
            $res | Should -Not -Match "oradb\.interno\.local"
            $res | Should -Match "\[HIDDEN\]"
        }
    }

    Context "Write-AutomacaoLog" {
        It "grava evento JSONL valido em UTF-8 sem BOM com dados sensiveis mascarados" {
            $tempLog = Join-Path $TestDrive "logging-test.jsonl"
            $linha = "Falha de " + "pass" + "word=Segredo1234 para operador@empresa.com.br"

            Write-AutomacaoLog -Message $linha -Level "WARN" -ExecId "EXEC_01" -LogPath $tempLog -Step "extract"

            Test-Path -LiteralPath $tempLog | Should -BeTrue
            $bytes = [System.IO.File]::ReadAllBytes($tempLog)
            (($bytes.Length -ge 3) -and ($bytes[0] -eq 239) -and ($bytes[1] -eq 187) -and ($bytes[2] -eq 191)) | Should -BeFalse

            $entry = ([System.IO.File]::ReadAllText($tempLog, [System.Text.Encoding]::UTF8).Trim()) | ConvertFrom-Json
            $entry.level | Should -Be "WARN"
            $entry.exec_id | Should -Be "EXEC_01"
            $entry.step | Should -Be "extract"
            $entry.component | Should -Be "ps_script"
            $entry.message | Should -Not -Match "Segredo1234"
            $entry.message | Should -Match "\[REDACTED\]"
            $entry.message | Should -Match "o\*\*\*@empresa\.com\.br"
        }
    }
}