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
using System.Threading.Tasks;

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

public class FakePs7HttpContent
{
    private readonly string _corpo;

    public FakePs7HttpContent(string corpo)
    {
        _corpo = corpo ?? "";
    }

    public Task<string> ReadAsStringAsync()
    {
        return Task.FromResult(_corpo);
    }
}

public class FakePs7HttpResponse
{
    private readonly int _status;
    private readonly FakePs7HttpContent _content;

    public FakePs7HttpResponse(int status, string corpo)
    {
        _status = status;
        _content = new FakePs7HttpContent(corpo);
    }

    public HttpStatusCode StatusCode { get { return (HttpStatusCode)_status; } }

    public FakePs7HttpContent Content { get { return _content; } }
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

    function New-TempDir {
        $dir = Join-Path $TestDrive ("wa_batch_test_" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        return $dir
    }
}

Describe "Lib-WhatsAppBatch" {
    It "valida manifesto de pagina unica e multi-pagina quando todos os arquivos existem" {
        $dir = New-TempDir
        try {
            $png1 = Join-Path $dir "card_01.png"
            $png2 = Join-Path $dir "card_02.png"
            [System.IO.File]::WriteAllBytes($png1, @(137, 80, 78, 71))
            [System.IO.File]::WriteAllBytes($png2, @(137, 80, 78, 71))

            $manifestPath = Join-Path $dir "cards_manifest.json"
            $manifestJson = ConvertTo-Json -InputObject @(
                @{ page = 1; total_pages = 2; phase_key = "page_01"; image_path = "card_01.png"; caption = "Pag 1"; ob_ids = @("101", "102") },
                @{ page = 2; total_pages = 2; phase_key = "page_02"; image_path = "card_02.png"; caption = "Pag 2"; ob_ids = @("103") }
            ) -Depth 5
            [System.IO.File]::WriteAllText($manifestPath, $manifestJson, (New-Object System.Text.UTF8Encoding $false))

            $res = Read-CardsManifest -ManifestPath $manifestPath -BaseDir $dir
            $res.Valid | Should -BeTrue
            $res.Cards.Count | Should -Be 2
            $res.Cards[0].phase_key | Should -Be "page_01"
        }
        finally {
            Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It "rejeita manifesto quando PNG esta ausente ou vazio" {
        $dir = New-TempDir
        try {
            $manifestPath = Join-Path $dir "cards_manifest.json"
            $manifestJson = ConvertTo-Json -InputObject @(
                @{ page = 1; total_pages = 1; phase_key = "page_01"; image_path = "card.png"; caption = "Pag 1"; ob_ids = @("101") }
            ) -Depth 5
            [System.IO.File]::WriteAllText($manifestPath, $manifestJson, (New-Object System.Text.UTF8Encoding $false))

            $res = Read-CardsManifest -ManifestPath $manifestPath -BaseDir $dir
            $res.Valid | Should -BeFalse
            $res.Error | Should -Match "Imagem do card ausente"
        }
        finally {
            Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It "serializa batch_input.json sempre como array JSON sem BOM mesmo com 1 pagina" {
        $dir = New-TempDir
        try {
            $batchInputPath = Join-Path $dir "batch_input.json"
            $cards = @([pscustomobject]@{ phase_key = "page_01"; image_path = "card_01.png"; caption = "Legenda 1" })

            Write-WhatsAppBatchInput -Cards $cards -BaseDir $dir -BatchInputFile $batchInputPath

            $bytes = [System.IO.File]::ReadAllBytes($batchInputPath)
            (($bytes[0] -eq 239) -and ($bytes[1] -eq 187) -and ($bytes[2] -eq 191)) | Should -BeFalse

            $raw = [System.IO.File]::ReadAllText($batchInputPath, [System.Text.Encoding]::UTF8).TrimStart()
            $raw.StartsWith("[") | Should -BeTrue
            $parsed = $raw | ConvertFrom-Json
            @($parsed).Count | Should -Be 1
            $parsed[0].image_path | Should -Be (Join-Path $dir "card_01.png")
        }
        finally {
            Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It "commit parcial remove apenas OBs de paginas com falha e preserva arrays unitarios em orb_state" {
        $dir = New-TempDir
        try {
            $stateTmp = Join-Path $dir "orb_state.json.tmp"
            $batchResult = Join-Path $dir "batch_result.json"

            $stateRaw = '{"notified":{"101":{"timestamp":"2026-11-13 10:00:00","reduzido":17,"restricoes":[4]},"102":{"timestamp":"2026-11-13 10:00:00","reduzido":18,"restricoes":[3,4]},"999":{"timestamp":"2026-11-12 09:00:00","reduzido":11,"restricoes":[4]}},"updated_at":"2026-11-13 10:00:00"}'
            [System.IO.File]::WriteAllText($stateTmp, $stateRaw, (New-Object System.Text.UTF8Encoding $false))

            $batchJson = ConvertTo-Json -InputObject @(
                @{ phase_key = "page_01"; success = $true; error = $null },
                @{ phase_key = "page_02"; success = $false; error = "timeout" }
            ) -Depth 5
            [System.IO.File]::WriteAllText($batchResult, $batchJson, (New-Object System.Text.UTF8Encoding $false))

            $cards = @(
                [pscustomobject]@{ phase_key = "page_01"; ob_ids = @("101") },
                [pscustomobject]@{ phase_key = "page_02"; ob_ids = @("102") }
            )

            $outcome = Resolve-WhatsAppBatchDelivery -Cards $cards -BatchResultFile $batchResult -StateTmpPath $stateTmp -WaExitCode 4
            $outcome.Status | Should -Be "PartialSent"
            $outcome.ShouldCommitState | Should -BeTrue
            $outcome.SentCount | Should -Be 1
            $outcome.TotalCount | Should -Be 2
            $outcome.DeliveredObCount | Should -Be 1
            $outcome.FailedObCount | Should -Be 1

            $updatedBytes = [System.IO.File]::ReadAllBytes($stateTmp)
            (($updatedBytes[0] -eq 239) -and ($updatedBytes[1] -eq 187) -and ($updatedBytes[2] -eq 191)) | Should -BeFalse

            $updatedState = (Get-Content -LiteralPath $stateTmp -Raw -Encoding UTF8) | ConvertFrom-Json
            ($updatedState.notified.PSObject.Properties.Name -contains "101") | Should -BeTrue
            ($updatedState.notified.PSObject.Properties.Name -contains "999") | Should -BeTrue
            ($updatedState.notified.PSObject.Properties.Name -contains "102") | Should -BeFalse
            # Array unitario [4] preservado como array no JSON
            $updatedRaw = [System.IO.File]::ReadAllText($stateTmp, [System.Text.Encoding]::UTF8)
            $updatedRaw | Should -Match '"restricoes":\s*\[\s*4\s*\]'
        }
        finally {
            Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It "falha total (0 paginas enviadas) nao altera state e bloqueia commit" {
        $dir = New-TempDir
        try {
            $stateTmp = Join-Path $dir "ofst_state.json.tmp"
            $batchResult = Join-Path $dir "batch_result.json"
            $orig = '{"notified":{"201":"2026-11-13 10:00:00"},"updated_at":"2026-11-13 10:00:00"}'
            [System.IO.File]::WriteAllText($stateTmp, $orig, (New-Object System.Text.UTF8Encoding $false))
            [System.IO.File]::WriteAllText($batchResult, '[{"phase_key":"page_01","success":false,"error":"offline"}]', (New-Object System.Text.UTF8Encoding $false))

            $cards = @([pscustomobject]@{ phase_key = "page_01"; ob_ids = @("201") })
            $outcome = Resolve-WhatsAppBatchDelivery -Cards $cards -BatchResultFile $batchResult -StateTmpPath $stateTmp -WaExitCode 4

            $outcome.Status | Should -Be "NoneSent"
            $outcome.DeliveredObCount | Should -Be 0
            $outcome.ShouldCommitState | Should -BeFalse
            ([System.IO.File]::ReadAllText($stateTmp, [System.Text.Encoding]::UTF8)) | Should -Be $orig
        }
        finally {
            Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It "rejeita manifesto com phase_key duplicado" {
        $dir = New-TempDir
        try {
            $png1 = Join-Path $dir "card_01.png"
            $png2 = Join-Path $dir "card_02.png"
            [System.IO.File]::WriteAllBytes($png1, @(137, 80, 78, 71))
            [System.IO.File]::WriteAllBytes($png2, @(137, 80, 78, 71))

            $manifestPath = Join-Path $dir "cards_manifest.json"
            $manifestJson = ConvertTo-Json -InputObject @(
                @{ page = 1; total_pages = 2; phase_key = "page_01"; image_path = "card_01.png"; caption = "Pag 1"; ob_ids = @("101") },
                @{ page = 2; total_pages = 2; phase_key = "page_01"; image_path = "card_02.png"; caption = "Pag 2"; ob_ids = @("102") }
            ) -Depth 5
            [System.IO.File]::WriteAllText($manifestPath, $manifestJson, (New-Object System.Text.UTF8Encoding $false))

            $res = Read-CardsManifest -ManifestPath $manifestPath -BaseDir $dir
            $res.Valid | Should -BeFalse
            $res.Error | Should -Match "phase_key duplicado"
        }
        finally {
            Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It "rejeita manifesto quando ob_ids esta ausente, vazio ou contem item vazio" {
        $dir = New-TempDir
        try {
            $png1 = Join-Path $dir "card_01.png"
            [System.IO.File]::WriteAllBytes($png1, @(137, 80, 78, 71))
            $manifestPath = Join-Path $dir "cards_manifest.json"

            foreach ($caso in @(
                    '[{"page":1,"total_pages":1,"phase_key":"page_01","image_path":"card_01.png","caption":"Pag 1"}]',
                    '[{"page":1,"total_pages":1,"phase_key":"page_01","image_path":"card_01.png","caption":"Pag 1","ob_ids":[]}]',
                    '[{"page":1,"total_pages":1,"phase_key":"page_01","image_path":"card_01.png","caption":"Pag 1","ob_ids":["101","  "]}]'
                )) {
                [System.IO.File]::WriteAllText($manifestPath, $caso, (New-Object System.Text.UTF8Encoding $false))
                $res = Read-CardsManifest -ManifestPath $manifestPath -BaseDir $dir
                $res.Valid | Should -BeFalse
                $res.Error | Should -Match "ob_ids"
            }
        }
        finally {
            Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It "conta OBs unicas entregues em DeliveredObCount e atualiza record_counts sem BOM" {
        $dir = New-TempDir
        try {
            $resultPath = Join-Path $dir "orb_result.json"
            $resultRaw = '{"rows":[],"total":3,"record_counts":{"read":10,"validated":10,"rejected":0,"qualified":3,"notified":3,"skipped":7,"suppressed":0}}'
            [System.IO.File]::WriteAllText($resultPath, $resultRaw, (New-Object System.Text.UTF8Encoding $false))

            $batchResult = Join-Path $dir "batch_result.json"
            $batchJson = ConvertTo-Json -InputObject @(
                @{ phase_key = "page_01"; success = $true; error = $null },
                @{ phase_key = "page_02"; success = $true; error = $null },
                @{ phase_key = "page_03"; success = $false; error = "timeout" }
            ) -Depth 5
            [System.IO.File]::WriteAllText($batchResult, $batchJson, (New-Object System.Text.UTF8Encoding $false))

            $cards = @(
                [pscustomobject]@{ phase_key = "page_01"; ob_ids = @("101", "102") },
                [pscustomobject]@{ phase_key = "page_02"; ob_ids = @("102", "103") },
                [pscustomobject]@{ phase_key = "page_03"; ob_ids = @("104") }
            )

            $outcome = Resolve-WhatsAppBatchDelivery -Cards $cards -BatchResultFile $batchResult -StateTmpPath (Join-Path $dir "inexistente.tmp") -WaExitCode 4
            $outcome.Status | Should -Be "PartialSent"
            $outcome.DeliveredObCount | Should -Be 3

            Update-WhatsAppResultRecordCounts -ResultPath $resultPath -DeliveredObCount $outcome.DeliveredObCount -SentPages $outcome.SentCount -TotalPages $outcome.TotalCount
            $bytes = [System.IO.File]::ReadAllBytes($resultPath)
            (($bytes[0] -eq 239) -and ($bytes[1] -eq 187) -and ($bytes[2] -eq 191)) | Should -BeFalse
            $updated = (Get-Content -LiteralPath $resultPath -Raw -Encoding UTF8) | ConvertFrom-Json
            $updated.record_counts.notified | Should -Be 3
            $updated.record_counts.pages_sent | Should -Be 2
            $updated.record_counts.pages_total | Should -Be 3
        }
        finally {
            Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
        }
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

    It "o corpo do lote leva client_id do perfil e items planos sem aninhamento no PS 5.1" {
        $fx = New-FixturesDaemon
        Mock Invoke-WebRequest -ModuleName Lib-WhatsAppBatch {
            [pscustomobject]@{ StatusCode = 200; Content = '{"results":[{"phase_key":"page_01","success":true,"error":null},{"phase_key":"page_02","success":true,"error":null}]}' }
        }

        Invoke-LoteDaemonTeste -Entrada $fx.Entrada -Saida $fx.Saida | Should -Be 0
        Should -Invoke Invoke-WebRequest -ModuleName Lib-WhatsAppBatch -Times 1 -Exactly -ParameterFilter {
            $payload = ConvertFrom-Json ([System.Text.Encoding]::UTF8.GetString($Body))
            ($payload.client_id -eq "hub-global") -and ($payload.items[0].phase_key -eq "page_01")
        }
    }

    It "HTTP 200 com item success=false devolve 4 (paridade com WhatsApp-Core.js)" {
        $fx = New-FixturesDaemon
        Mock Invoke-WebRequest -ModuleName Lib-WhatsAppBatch {
            [pscustomobject]@{
                StatusCode = 200
                Content    = '{"results":[{"phase_key":"page_01","success":true,"error":null},{"phase_key":"page_02","success":false,"error":"timeout"}]}'
            }
        }

        $codigo = Invoke-LoteDaemonTeste -Entrada $fx.Entrada -Saida $fx.Saida
        $codigo | Should -Be 4
        Test-Path -LiteralPath $fx.Saida | Should -BeTrue
    }

    It "HTTP 200 com results vazio devolve 4" {
        $fx = New-FixturesDaemon
        Mock Invoke-WebRequest -ModuleName Lib-WhatsAppBatch {
            [pscustomobject]@{ StatusCode = 200; Content = '{"results":[]}' }
        }

        $codigo = Invoke-LoteDaemonTeste -Entrada $fx.Entrada -Saida $fx.Saida
        $codigo | Should -Be 4
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

Describe "Get-WhatsAppDaemonEnvironment" {
    It "descarta segredos do Orchestrator/Oracle/SMTP e mantem apenas allowlist e variaveis do daemon" {
        # Valor em variavel separada para o fixture nao disparar o gate Test-ZeroTrust,
        # e caminhos sobre $TestDrive para nao violar Test-PortablePaths.
        $valorFalso = "ficticio-" + "nao-deve-vazar"
        $fakePath = Join-Path $TestDrive "bin"
        $fakeSysRoot = Join-Path $TestDrive "win"
        $fakeAuth = Join-Path $TestDrive "wa_auth"
        $origem = @{
            PATH                     = $fakePath
            SystemRoot               = $fakeSysRoot
            WHATSAPP_AUTH_PATH       = $fakeAuth
            ORCHESTRATOR_API_KEY     = $valorFalso
            ORACLE_READONLY_PASSWORD = $valorFalso
            MT_EMAIL_TO              = "lista@empresa.local"
            SMTP_PASSWORD            = $valorFalso
        }

        $filtrado = Get-WhatsAppDaemonEnvironment `
            -Token ("t" * 40) `
            -Port "8765" `
            -ClientId "hub-global" `
            -MaxNotReadyMs "60000" `
            -SourceEnvironment $origem

        $filtrado.ContainsKey("ORCHESTRATOR_API_KEY") | Should -BeFalse
        $filtrado.ContainsKey("ORACLE_READONLY_PASSWORD") | Should -BeFalse
        $filtrado.ContainsKey("MT_EMAIL_TO") | Should -BeFalse
        $filtrado.ContainsKey("SMTP_PASSWORD") | Should -BeFalse

        $filtrado["PATH"] | Should -Be $fakePath
        $filtrado["SystemRoot"] | Should -Be $fakeSysRoot
        $filtrado["WHATSAPP_AUTH_PATH"] | Should -Be $fakeAuth
        $filtrado["WHATSAPP_DAEMON_TOKEN"] | Should -Be ("t" * 40)
        $filtrado["WHATSAPP_DAEMON_PORT"] | Should -Be "8765"
        $filtrado["WHATSAPP_DAEMON_CLIENT_ID"] | Should -Be "hub-global"
        $filtrado["WHATSAPP_DAEMON_MAX_NOT_READY_MS"] | Should -Be "60000"
    }
}

Describe "Read-WhatsAppHttpErrorBody e compatibilidade PS 5.1 / PS 7" {
    It "le o corpo a partir de HttpWebResponse (PS 5.1 GetResponseStream)" {
        $resp = [FakeHttpResponse]::new(500, '{"error":"ps51"}')
        Read-WhatsAppHttpErrorBody -Resposta $resp | Should -Be '{"error":"ps51"}'
    }

    It "le o corpo a partir de ErrorDetails.Message (PS 7) e Content.ReadAsStringAsync" {
        $erroComDetalhes = [pscustomobject]@{
            ErrorDetails = [pscustomobject]@{ Message = '{"error":"ps7-details"}' }
        }
        Read-WhatsAppHttpErrorBody -ErrorRecord $erroComDetalhes -Resposta $null | Should -Be '{"error":"ps7-details"}'

        $respPs7 = [FakePs7HttpResponse]::new(500, '{"error":"ps7-content"}')
        Read-WhatsAppHttpErrorBody -ErrorRecord $null -Resposta $respPs7 | Should -Be '{"error":"ps7-content"}'
    }

    It "Invoke-WhatsAppDaemonBatch em resposta estilo PS 7 (sem GetResponseStream): 503 vira 22 e 500 grava results parciais" {
        $fx = New-FixturesDaemon
        Mock Invoke-WebRequest -ModuleName Lib-WhatsAppBatch {
            throw ([FakeHttpErrorException]::new("HTTP 503", [FakePs7HttpResponse]::new(503, '{"error":"not_connected"}')))
        }
        (Invoke-LoteDaemonTeste -Entrada $fx.Entrada -Saida $fx.Saida) | Should -Be 22

        $fx2 = New-FixturesDaemon
        Mock Invoke-WebRequest -ModuleName Lib-WhatsAppBatch {
            throw ([FakeHttpErrorException]::new("HTTP 500", [FakePs7HttpResponse]::new(500, '{"error":"boom","results":[{"phase_key":"page_01","success":true,"error":null}]}')))
        }
        (Invoke-LoteDaemonTeste -Entrada $fx2.Entrada -Saida $fx2.Saida) | Should -Be 24
        Test-Path -LiteralPath $fx2.Saida | Should -BeTrue
        $parsed = [System.IO.File]::ReadAllText($fx2.Saida, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
        @($parsed).Count | Should -Be 1
        $parsed[0].phase_key | Should -Be "page_01"
    }
}

Describe "Get-WhatsAppDaemonProcess (-ThrowOnError)" {
    It "sem -ThrowOnError devolve vazio se CIM falhar; com -ThrowOnError relanca a excecao" {
        Mock Get-CimInstance -ModuleName Lib-WhatsAppBatch { throw [System.InvalidOperationException]::new("cim indisponivel") }

        @(Get-WhatsAppDaemonProcess).Count | Should -Be 0
        { Get-WhatsAppDaemonProcess -ThrowOnError } | Should -Throw "*cim indisponivel*"
    }
}
