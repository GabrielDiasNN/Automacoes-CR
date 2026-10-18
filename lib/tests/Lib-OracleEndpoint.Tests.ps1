$here = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($here)) {
    $here = Split-Path -Parent $PSCommandPath
}

Import-Module ((Split-Path -Parent $here) + "\Lib-OracleEndpoint.psm1") -Force

Describe "Resolve-OracleEndpoint" {
    BeforeAll {
        $script:dirTns = Join-Path $TestDrive "tns"
        New-Item -ItemType Directory -Path $script:dirTns -Force | Out-Null
        $conteudo = @"
DBPRD_TESTE =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = 10.62.0.3)(PORT = 15210))
    (CONNECT_DATA = (SERVICE_NAME = dbprd))
  )
OUTRO_ALIAS =
  (DESCRIPTION = (ADDRESS = (PROTOCOL = TCP)(HOST = 10.0.0.9)))
DOMINIO.WORLD =
  (DESCRIPTION = (ADDRESS = (PROTOCOL = TCP)(HOST = 10.0.0.7)(PORT = 1521)))
"@
        Set-Content -LiteralPath (Join-Path $script:dirTns "tnsnames.ora") -Value $conteudo -Encoding ASCII
        $env:TNS_ADMIN = $script:dirTns
    }

    AfterAll {
        Remove-Item Env:\TNS_ADMIN -ErrorAction SilentlyContinue
    }

    It "Resolve o alias do tnsnames para o host e a porta reais" {
        $r = Resolve-OracleEndpoint -ConnectString "DBPRD_TESTE"
        $r.Servidor | Should -Be "10.62.0.3"
        $r.Porta | Should -Be 15210
        $r.Origem | Should -Be "TNS"
    }

    It "Usa a porta 1521 quando o alias nao informa PORT" {
        $r = Resolve-OracleEndpoint -ConnectString "OUTRO_ALIAS"
        $r.Servidor | Should -Be "10.0.0.9"
        $r.Porta | Should -Be 1521
    }

    It "Nao casa nome parcial e alias ausente nao vira host (antes gerava Oracle Off falso)" {
        Resolve-OracleEndpoint -ConnectString "DBPRD" | Should -BeNullOrEmpty
    }

    It "Aceita alias com sufixo de dominio no tnsnames" {
        $r = Resolve-OracleEndpoint -ConnectString "DOMINIO"
        $r.Servidor | Should -Be "10.0.0.7"
        $r.Origem | Should -Be "TNS"
    }

    It "Aceita EZ Connect sem porta quando tem servico" {
        $r = Resolve-OracleEndpoint -ConnectString "banco.exemplo.local/SVC"
        $r.Servidor | Should -Be "banco.exemplo.local"
        $r.Porta | Should -Be 1521
    }

    It "Aceita EZ Connect com porta e servico" {
        $r = Resolve-OracleEndpoint -ConnectString "banco.exemplo.local:1600/SVC"
        $r.Servidor | Should -Be "banco.exemplo.local"
        $r.Porta | Should -Be 1600
        $r.Origem | Should -Be "EZConnect"
    }
}
