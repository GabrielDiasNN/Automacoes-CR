BeforeAll {
    $here = $PSScriptRoot
    if ([string]::IsNullOrWhiteSpace($here)) {
        $here = Split-Path -Parent $PSCommandPath
    }
    $repoRoot = Split-Path -Parent (Split-Path -Parent $here)
    Import-Module (Join-Path $repoRoot "lib\Lib-WhatsAppBatch.psm1") -Force

    # Simula o erro HTTP do PS 5.1 (WebException.Response) sem rede. Tipos C# para as mocks,
    # que rodam no escopo do modulo e enxergam apenas tipos globais.
    if (-not ('FakeHttpResponse' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Net;
using System.Text;

public class FakeHttpResponse
{
    private readonly int _status;
    private readonly string _corpo;

    public FakeHttpResponse(int status, string corpo)
    {
        _status = status;
        _corpo = corpo ?? "";
    }

    public HttpStatusCode StatusCode { get { return (HttpStatusCode)_status; } }

    public Stream GetResponseStream()
    {
        return new MemoryStream(Encoding.UTF8.GetBytes(_corpo));
    }
}

public class FakeHttpErrorException : Exception
{
    private readonly object _response;

    public FakeHttpErrorException(string mensagem, object response) : base(mensagem)
    {
        _response = response;
    }

    public object Response { get { return _response; } }
}
'@
    }

    function New-FixturesDaemon {
        $dir = Join-Path $TestDrive ("wa_daemon_" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        $entrada = Join-Path $dir "batch_input.json"
        $json = '[{"phase_key":"page_01","image_path":"card_01.png","caption":"Pag 1"},{"phase_key":"page_02","image_path":"card_02.png","caption":"Pag 2"}]'
        [System.IO.File]::WriteAllText($entrada, $json, (New-Object System.Text.UTF8Encoding $false))
        return [pscustomobject]@{ Entrada = $entrada; Saida = (Join-Path $dir "batch_result.json") }
    }

    function Invoke-LoteDaemonTeste {
        param([string]$Entrada, [string]$Saida)
        return Invoke-WhatsAppDaemonBatch -Port "8765" -Token ("t" * 40) -ExecId "exec-teste" -ClientId "hub-global" -ChatTarget "5511999999999" -BatchInputFile $Entrada -BatchResultFile $Saida
    }
}

Describe "Get-WhatsAppDaemonRoute" {
    It "devolve 'spawn' quando nenhum processo do daemon esta vivo (WHATSAPP_DAEMON_ENABLED nao e' entrada da regra)" {
        Get-WhatsAppDaemonRoute -DaemonRunning $false -ClientId "hub-global" -HealthState "" -HealthClientId "" | Should -Be "spawn"
        Get-WhatsAppDaemonRoute -DaemonRunning $false -ClientId "hub-global" -HealthState "ready" -HealthClientId "hub-global" | Should -Be "spawn"
    }

    It "devolve 'spawn' quando o daemon vivo segura OUTRO perfil (perfis diferentes nao conflitam)" {
        Get-WhatsAppDaemonRoute -DaemonRunning $true -ClientId "hub-global" -HealthState "ready" -HealthClientId "outro-perfil" | Should -Be "spawn"
        Get-WhatsAppDaemonRoute -DaemonRunning $true -ClientId "hub-global" -HealthState "starting" -HealthClientId "outro-perfil" | Should -Be "spawn"
    }

    It "devolve 'defer' quando o daemon vivo e do MESMO perfil mas nao esta pronto" {
        Get-WhatsAppDaemonRoute -DaemonRunning $true -ClientId "hub-global" -HealthState "starting" -HealthClientId "hub-global" | Should -Be "defer"
        Get-WhatsAppDaemonRoute -DaemonRunning $true -ClientId "hub-global" -HealthState "warming" -HealthClientId "hub-global" | Should -Be "defer"
        Get-WhatsAppDaemonRoute -DaemonRunning $true -ClientId "hub-global" -HealthState "reconnecting" -HealthClientId "hub-global" | Should -Be "defer"
    }

    It "devolve 'defer' quando o health esta indisponivel ou recusou o token (401), sem client_id conhecido" {
        Get-WhatsAppDaemonRoute -DaemonRunning $true -ClientId "hub-global" -HealthState "" -HealthClientId "" | Should -Be "defer"
        Get-WhatsAppDaemonRoute -DaemonRunning $true -ClientId "hub-global" -HealthState "unauthorized" -HealthClientId "" | Should -Be "defer"
    }

    It "devolve 'daemon' quando o daemon vivo e do mesmo perfil e esta 'ready'" {
        Get-WhatsAppDaemonRoute -DaemonRunning $true -ClientId "hub-global" -HealthState "ready" -HealthClientId "hub-global" | Should -Be "daemon"
    }
}

Describe "Invoke-WhatsAppDaemonBatch" {
    It "HTTP 200 devolve 0 e grava o arquivo de resultado em UTF-8 sem BOM" {
        $fx = New-FixturesDaemon
        Mock Invoke-WebRequest -ModuleName Lib-WhatsAppBatch {
            [pscustomobject]@{
                StatusCode = 200
                Content    = '{"results":[{"phase_key":"page_01","success":true,"error":null},{"phase_key":"page_02","success":true,"error":null}]}'
            }
        }

        $codigo = Invoke-LoteDaemonTeste -Entrada $fx.Entrada -Saida $fx.Saida
        $codigo | Should -Be 0
        Test-Path -LiteralPath $fx.Saida | Should -BeTrue

        $bytes = [System.IO.File]::ReadAllBytes($fx.Saida)
        (($bytes[0] -eq 239) -and ($bytes[1] -eq 187) -and ($bytes[2] -eq 191)) | Should -BeFalse
        $parsed = [System.IO.File]::ReadAllText($fx.Saida, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
        @($parsed).Count | Should -Be 2
        Should -Invoke Invoke-WebRequest -ModuleName Lib-WhatsAppBatch -Times 1 -Exactly -ParameterFilter { "$Uri" -eq "http://127.0.0.1:8765/batch" }
    }

    It "HTTP 503 devolve 22 e nao grava arquivo de resultado" {
        $fx = New-FixturesDaemon
        Mock Invoke-WebRequest -ModuleName Lib-WhatsAppBatch {
            throw ([FakeHttpErrorException]::new("HTTP 503", [FakeHttpResponse]::new(503, '{"error":"not_connected"}')))
        }

        $codigo = Invoke-LoteDaemonTeste -Entrada $fx.Entrada -Saida $fx.Saida
        $codigo | Should -Be 22
        Test-Path -LiteralPath $fx.Saida | Should -BeFalse
    }

    It "HTTP 500 com results devolve 24 e grava os results parciais" {
        $fx = New-FixturesDaemon
        Mock Invoke-WebRequest -ModuleName Lib-WhatsAppBatch {
            throw ([FakeHttpErrorException]::new("HTTP 500", [FakeHttpResponse]::new(500, '{"error":"boom","results":[{"phase_key":"page_01","success":true,"error":null},{"phase_key":"page_02","success":false,"error":"DAEMON_ERROR"}]}')))
        }

        $codigo = Invoke-LoteDaemonTeste -Entrada $fx.Entrada -Saida $fx.Saida
        $codigo | Should -Be 24
        Test-Path -LiteralPath $fx.Saida | Should -BeTrue
        $parsed = [System.IO.File]::ReadAllText($fx.Saida, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
        @($parsed).Count | Should -Be 2
        $parsed[0].success | Should -BeTrue
        $parsed[1].error | Should -Be "DAEMON_ERROR"
    }

    It "o corpo do lote leva client_id do perfil (contrato do daemon exige o mesmo perfil)" {
        $fx = New-FixturesDaemon
        Mock Invoke-WebRequest -ModuleName Lib-WhatsAppBatch {
            [pscustomobject]@{ StatusCode = 200; Content = '{"results":[]}' }
        }

        Invoke-LoteDaemonTeste -Entrada $fx.Entrada -Saida $fx.Saida | Should -Be 0
        Should -Invoke Invoke-WebRequest -ModuleName Lib-WhatsAppBatch -Times 1 -Exactly -ParameterFilter {
            ([System.Text.Encoding]::UTF8.GetString($Body)) -match '"client_id":\s*"hub-global"'
        }
    }

    It "sem resposta HTTP devolve 24 e nao grava arquivo de resultado" {
        $fx = New-FixturesDaemon
        Mock Invoke-WebRequest -ModuleName Lib-WhatsAppBatch {
            throw ([FakeHttpErrorException]::new("conexao recusada", $null))
        }

        $codigo = Invoke-LoteDaemonTeste -Entrada $fx.Entrada -Saida $fx.Saida
        $codigo | Should -Be 24
        Test-Path -LiteralPath $fx.Saida | Should -BeFalse
    }
}

Describe "Get-WhatsAppDaemonHealth" {
    It "HTTP 401 no health devolve State 'unauthorized' e ClientId vazio" {
        Mock Invoke-RestMethod -ModuleName Lib-WhatsAppBatch {
            throw ([FakeHttpErrorException]::new("HTTP 401", [FakeHttpResponse]::new(401, '{"error":"unauthorized"}')))
        }
        $saude = Get-WhatsAppDaemonHealth -Port "8765" -Token ("t" * 40)
        $saude.State | Should -Be "unauthorized"
        $saude.ClientId | Should -Be ""
    }

    It "health ok devolve o state e o client_id do daemon" {
        Mock Invoke-RestMethod -ModuleName Lib-WhatsAppBatch {
            [pscustomobject]@{ state = "ready"; client_id = "hub-global" }
        }
        $saude = Get-WhatsAppDaemonHealth -Port "8765" -Token ("t" * 40)
        $saude.State | Should -Be "ready"
        $saude.ClientId | Should -Be "hub-global"
    }

    It "health sem campo client_id devolve ClientId vazio sem quebrar" {
        Mock Invoke-RestMethod -ModuleName Lib-WhatsAppBatch {
            [pscustomobject]@{ state = "starting" }
        }
        $saude = Get-WhatsAppDaemonHealth -Port "8765" -Token ("t" * 40)
        $saude.State | Should -Be "starting"
        $saude.ClientId | Should -Be ""
    }

    It "sem resposta HTTP devolve State e ClientId vazios" {
        Mock Invoke-RestMethod -ModuleName Lib-WhatsAppBatch {
            throw ([FakeHttpErrorException]::new("conexao recusada", $null))
        }
        $saude = Get-WhatsAppDaemonHealth -Port "8765" -Token ("t" * 40)
        $saude.State | Should -Be ""
        $saude.ClientId | Should -Be ""
    }
}

Describe "Invoke-WhatsAppDaemonSend" {
    BeforeAll {
        function Invoke-EnvioDaemonTeste {
            param([string]$Anexo = "")
            return Invoke-WhatsAppDaemonSend -Port "8765" -Token ("t" * 40) -ExecId "exec-teste" -ClientId "hub-global" -ChatTarget "5511999999999" -Caption "Mensagem de teste" -AttachmentPath $Anexo
        }
    }

    It "HTTP 200 devolve 0 e envia POST /send com client_id, chat_id e attachment_path null (so texto)" {
        Mock Invoke-WebRequest -ModuleName Lib-WhatsAppBatch {
            [pscustomobject]@{ StatusCode = 200; Content = '{"ok":true}' }
        }
        Invoke-EnvioDaemonTeste | Should -Be 0
        Should -Invoke Invoke-WebRequest -ModuleName Lib-WhatsAppBatch -Times 1 -Exactly -ParameterFilter {
            ("$Uri" -eq "http://127.0.0.1:8765/send") -and
            (([System.Text.Encoding]::UTF8.GetString($Body)) -match '"client_id":\s*"hub-global"') -and
            (([System.Text.Encoding]::UTF8.GetString($Body)) -match '"chat_id":\s*"5511999999999@c\.us"') -and
            (([System.Text.Encoding]::UTF8.GetString($Body)) -match '"attachment_path":\s*null')
        }
    }

    It "com anexo envia attachment_path com o caminho informado" {
        Mock Invoke-WebRequest -ModuleName Lib-WhatsAppBatch {
            [pscustomobject]@{ StatusCode = 200; Content = '{"ok":true}' }
        }
        Invoke-EnvioDaemonTeste -Anexo "card_01.png" | Should -Be 0
        Should -Invoke Invoke-WebRequest -ModuleName Lib-WhatsAppBatch -Times 1 -Exactly -ParameterFilter {
            ([System.Text.Encoding]::UTF8.GetString($Body)) -match '"attachment_path":\s*"card_01\.png"'
        }
    }

    It "HTTP 503 devolve 22 (daemon nao pronto ou sem CONNECTED)" {
        Mock Invoke-WebRequest -ModuleName Lib-WhatsAppBatch {
            throw ([FakeHttpErrorException]::new("HTTP 503", [FakeHttpResponse]::new(503, '{"error":"not_connected"}')))
        }
        Invoke-EnvioDaemonTeste | Should -Be 22
    }

    It "HTTP 409 (client_mismatch) devolve 24, nunca 22 nem spawn" {
        Mock Invoke-WebRequest -ModuleName Lib-WhatsAppBatch {
            throw ([FakeHttpErrorException]::new("HTTP 409", [FakeHttpResponse]::new(409, '{"error":"client_mismatch"}')))
        }
        Invoke-EnvioDaemonTeste | Should -Be 24
    }

    It "HTTP 500 devolve 24" {
        Mock Invoke-WebRequest -ModuleName Lib-WhatsAppBatch {
            throw ([FakeHttpErrorException]::new("HTTP 500", [FakeHttpResponse]::new(500, '{"error":"falha simulada"}')))
        }
        Invoke-EnvioDaemonTeste | Should -Be 24
    }

    It "sem resposta HTTP devolve 24" {
        Mock Invoke-WebRequest -ModuleName Lib-WhatsAppBatch {
            throw ([FakeHttpErrorException]::new("conexao recusada", $null))
        }
        Invoke-EnvioDaemonTeste | Should -Be 24
    }
}

Describe "Select-WhatsAppStaleProcessIds" {
    BeforeAll {
        function New-ProcessoFake {
            param([int]$Id, [int]$Pai, [string]$Nome, [string]$Cmd, [string]$Caminho, $Criacao)
            return [pscustomobject]@{
                ProcessId       = $Id
                ParentProcessId = $Pai
                Name            = $Nome
                CommandLine     = $Cmd
                ExecutablePath  = $Caminho
                CreationDate    = $Criacao
            }
        }

        # Arvore: daemon (100) -> chrome 101 -> chrome 102 (neto) e chrome 103; orfaos e casos de borda.
        function Get-ProcessosFixture {
            param([datetime]$Agora)
            $antigo = $Agora.AddMinutes(-5)
            return @(
                New-ProcessoFake -Id 100 -Pai 1 -Nome "node.exe" -Cmd 'node Automacoes\lib\whatsapp-daemon.js' -Caminho 'Program Files\nodejs\node.exe' -Criacao $antigo
                New-ProcessoFake -Id 101 -Pai 100 -Nome "chrome.exe" -Cmd 'chrome --type=browser --user-data-dir=Automacoes\lib\auth' -Caminho 'Chrome\chrome.exe' -Criacao $antigo
                New-ProcessoFake -Id 102 -Pai 101 -Nome "chrome.exe" -Cmd 'chrome --type=renderer' -Caminho 'Chrome\chrome.exe' -Criacao $antigo
                New-ProcessoFake -Id 103 -Pai 100 -Nome "chrome.exe" -Cmd 'chrome --type=gpu' -Caminho 'Chrome\chrome.exe' -Criacao $antigo
                New-ProcessoFake -Id 200 -Pai 1 -Nome "chrome.exe" -Cmd 'chrome --user-data-dir=Automacoes\Logs' -Caminho 'Chrome\chrome.exe' -Criacao $antigo
                New-ProcessoFake -Id 201 -Pai 1 -Nome "chrome.exe" -Cmd 'chrome --user-data-dir=Automacoes\recente' -Caminho 'Chrome\chrome.exe' -Criacao $Agora.AddSeconds(-3)
                New-ProcessoFake -Id 202 -Pai 1 -Nome "node.exe" -Cmd 'node Automacoes\x.js' -Caminho 'Program Files\nodejs\node.exe' -Criacao $antigo
                New-ProcessoFake -Id 203 -Pai 1 -Nome "chrome_crashpad_handler.exe" -Cmd 'handler Automacoes' -Caminho 'Chrome\handler.exe' -Criacao $antigo
                New-ProcessoFake -Id 204 -Pai 1 -Nome "chrome.exe" -Cmd 'chrome --user-data-dir=Automacoes\sem-data' -Caminho 'Chrome\chrome.exe' -Criacao $null
                New-ProcessoFake -Id 300 -Pai 1 -Nome "chrome.exe" -Cmd 'chrome --user-data-dir=Outro' -Caminho 'Outro\chrome.exe' -Criacao $antigo
            )
        }
    }

    It "protege o daemon e toda a arvore de descendentes e encerra so' os orfaos antigos do repositorio" {
        $agora = [datetime]"2026-11-18 12:00:00"
        $ids = @(Select-WhatsAppStaleProcessIds -Processes (Get-ProcessosFixture -Agora $agora) -DaemonPids @(100) -Now $agora)
        (($ids | Sort-Object) -join ",") | Should -Be "200,202,204"
    }

    It "sem PID do daemon informado, o filho direto vira candidato (a protecao vem da arvore, nao do nome)" {
        $agora = [datetime]"2026-11-18 12:00:00"
        $ids = @(Select-WhatsAppStaleProcessIds -Processes (Get-ProcessosFixture -Agora $agora) -DaemonPids @() -Now $agora)
        (($ids | Sort-Object) -join ",") | Should -Be "101,200,202,204"
    }

    It "devolve lista vazia quando nao ha processos" {
        $agora = [datetime]"2026-11-18 12:00:00"
        $ids = @(Select-WhatsAppStaleProcessIds -Processes @() -DaemonPids @() -Now $agora)
        $ids.Count | Should -Be 0
    }
}
