#
# Lib-WhatsAppBatch.psm1 — manifesto paginado e reconciliacao parcial de lote WhatsApp.
#
# Compartilhado entre ORB-07 (OBs Restricao Branco) e OFST-06 (OBs Fluxo Sem Tingimento)
# para evitar duplicacao no fluxo de manifesto (`cards_manifest.json`), serializacao de
# `batch_input.json` (UTF-8 sem BOM) e commit parcial de `*_state.json` via `batch_result.json`.
#

Set-StrictMode -Version Latest

function Get-JsonPropValue {
    param(
        $Object,
        [Parameter(Mandatory)]
        [string]$Name
    )

    if ($null -eq $Object) { return $null }
    if ($Object -is [System.Collections.IDictionary]) {
        if ($Object.Contains($Name)) { return $Object[$Name] }
        return $null
    }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -ne $prop) { return $prop.Value }
    return $null
}

function Write-Utf8NoBomFile {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [Parameter(Mandatory)]
        [string]$Content
    )

    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Read-CardsManifest {
    <#
    .SYNOPSIS
        Le e valida `cards_manifest.json` gerado pelo `format_message.py`.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)]
        [string]$ManifestPath,

        [Parameter(Mandatory)]
        [string]$BaseDir,

        [string]$MessageFile = "",
        [string]$CardFile = ""
    )

    if (-not (Test-Path -LiteralPath $ManifestPath)) {
        return [pscustomobject]@{ Valid = $false; Cards = @(); Error = "cards_manifest.json nao encontrado." }
    }

    $cards = @()
    try {
        $raw = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($raw)) {
            return [pscustomobject]@{ Valid = $false; Cards = @(); Error = "cards_manifest.json vazio." }
        }
        $parsed = $raw | ConvertFrom-Json
        if ($null -ne $parsed) {
            $cards = @($parsed)
        }
    }
    catch [System.Exception] {
        return [pscustomobject]@{ Valid = $false; Cards = @(); Error = "Falha ao ler cards_manifest.json: $($_.Exception.Message)" }
    }

    if ($cards.Count -lt 1) {
        return [pscustomobject]@{ Valid = $false; Cards = @(); Error = "cards_manifest.json sem paginas." }
    }

    $seenPhaseKeys = @{}
    foreach ($card in $cards) {
        $phaseKey = [string](Get-JsonPropValue $card "phase_key")
        $imageRel = [string](Get-JsonPropValue $card "image_path")
        $caption = [string](Get-JsonPropValue $card "caption")

        if ([string]::IsNullOrWhiteSpace($phaseKey) -or
            [string]::IsNullOrWhiteSpace($imageRel) -or
            [string]::IsNullOrWhiteSpace($caption)) {
            return [pscustomobject]@{ Valid = $false; Cards = @(); Error = "Entrada invalida em cards_manifest.json (phase_key/image_path/caption)." }
        }

        if ($seenPhaseKeys.ContainsKey($phaseKey)) {
            return [pscustomobject]@{ Valid = $false; Cards = @(); Error = "phase_key duplicado em cards_manifest.json: $phaseKey" }
        }
        $seenPhaseKeys[$phaseKey] = $true

        $obIdsRaw = $null
        if ($card -is [System.Collections.IDictionary]) {
            if ($card.Contains("ob_ids")) {
                $obIdsRaw = $card["ob_ids"]
            }
        }
        else {
            $obIdsProp = $card.PSObject.Properties["ob_ids"]
            if ($null -ne $obIdsProp) {
                $obIdsRaw = $obIdsProp.Value
            }
        }
        if ($null -eq $obIdsRaw -or ($obIdsRaw -is [string]) -or ($obIdsRaw -is [System.Collections.IDictionary]) -or -not ($obIdsRaw -is [System.Collections.IEnumerable])) {
            return [pscustomobject]@{ Valid = $false; Cards = @(); Error = "Entrada invalida em cards_manifest.json: ob_ids ausente ou invalido em '$phaseKey'." }
        }
        $obIdsList = @($obIdsRaw)
        if ($obIdsList.Count -lt 1) {
            return [pscustomobject]@{ Valid = $false; Cards = @(); Error = "Entrada invalida em cards_manifest.json: ob_ids vazio em '$phaseKey'." }
        }
        foreach ($obId in $obIdsList) {
            if ($null -eq $obId -or [string]::IsNullOrWhiteSpace([string]$obId)) {
                return [pscustomobject]@{ Valid = $false; Cards = @(); Error = "Entrada invalida em cards_manifest.json: ob_ids contem ID vazio em '$phaseKey'." }
            }
        }

        $imageFull = if ([System.IO.Path]::IsPathRooted($imageRel)) { $imageRel } else { Join-Path $BaseDir $imageRel }
        if (-not (Test-Path -LiteralPath $imageFull) -or (Get-Item -LiteralPath $imageFull).Length -le 0) {
            return [pscustomobject]@{ Valid = $false; Cards = @(); Error = "Imagem do card ausente ou vazia: $imageRel" }
        }
    }

    if ($cards.Count -eq 1) {
        if (-not [string]::IsNullOrWhiteSpace($MessageFile)) {
            if (-not (Test-Path -LiteralPath $MessageFile) -or (Get-Item -LiteralPath $MessageFile).Length -le 0) {
                return [pscustomobject]@{ Valid = $false; Cards = @(); Error = "message.txt nao foi gerado ou esta vazio." }
            }
        }
        if (-not [string]::IsNullOrWhiteSpace($CardFile)) {
            if (-not (Test-Path -LiteralPath $CardFile) -or (Get-Item -LiteralPath $CardFile).Length -le 0) {
                return [pscustomobject]@{ Valid = $false; Cards = @(); Error = "card.png nao foi gerado ou esta vazio." }
            }
        }
    }

    return [pscustomobject]@{ Valid = $true; Cards = @($cards); Error = "" }
}

function Write-WhatsAppBatchInput {
    <#
    .SYNOPSIS
        Gera `batch_input.json` (UTF-8 sem BOM) no contrato do `Send-WhatsApp.ps1 -Mode BATCH`.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [array]$Cards,

        [Parameter(Mandatory)]
        [string]$BaseDir,

        [Parameter(Mandatory)]
        [string]$BatchInputFile
    )

    $batchInput = @(
        foreach ($card in $Cards) {
            $imgRel = [string](Get-JsonPropValue $card "image_path")
            $imgFull = if ([System.IO.Path]::IsPathRooted($imgRel)) { $imgRel } else { Join-Path $BaseDir $imgRel }
            @{
                phase_key  = [string](Get-JsonPropValue $card "phase_key")
                image_path = $imgFull
                caption    = [string](Get-JsonPropValue $card "caption")
            }
        }
    )

    $json = ConvertTo-Json -InputObject @($batchInput) -Depth 5
    Write-Utf8NoBomFile -Path $BatchInputFile -Content $json
}

function Resolve-WhatsAppBatchDelivery {
    <#
    .SYNOPSIS
        Reconcilia `batch_result.json` com `*_state.json.tmp` para commit total, parcial ou nulo.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)]
        [array]$Cards,

        [Parameter(Mandatory)]
        [string]$BatchResultFile,

        [Parameter(Mandatory)]
        [string]$StateTmpPath,

        [Parameter(Mandatory)]
        [int]$WaExitCode,

        [scriptblock]$OnWarn
    )

    $batchResults = @()
    if (Test-Path -LiteralPath $BatchResultFile) {
        try {
            $raw = Get-Content -LiteralPath $BatchResultFile -Raw -Encoding UTF8
            if (-not [string]::IsNullOrWhiteSpace($raw)) {
                $parsed = $raw | ConvertFrom-Json
                if ($null -ne $parsed) {
                    $batchResults = @($parsed)
                }
            }
        }
        catch [System.Exception] {
            if ($OnWarn) {
                & $OnWarn "Falha ao ler batch_result.json para reconciliacao: $($_.Exception.Message)"
            }
        }
    }

    $succeededKeys = @{}
    foreach ($item in $batchResults) {
        $ok = (Get-JsonPropValue $item "success") -eq $true
        $key = [string](Get-JsonPropValue $item "phase_key")
        if ($ok -and -not [string]::IsNullOrWhiteSpace($key)) {
            $succeededKeys[$key] = $true
        }
    }

    $sentPages = @($Cards | Where-Object { $succeededKeys.ContainsKey([string](Get-JsonPropValue $_ "phase_key")) })
    $failedPages = @($Cards | Where-Object { -not $succeededKeys.ContainsKey([string](Get-JsonPropValue $_ "phase_key")) })

    $totalCount = $Cards.Count
    $sentCount = $sentPages.Count

    $deliveredObSet = @{}
    foreach ($sp in $sentPages) {
        $ids = Get-JsonPropValue $sp "ob_ids"
        if ($null -ne $ids) {
            foreach ($obId in @($ids)) {
                $obKey = [string]$obId
                if (-not [string]::IsNullOrWhiteSpace($obKey)) {
                    $deliveredObSet[$obKey] = $true
                }
            }
        }
    }
    $deliveredObCount = $deliveredObSet.Count

    if ($WaExitCode -eq 0 -and $failedPages.Count -eq 0) {
        return [pscustomobject]@{
            Status            = "AllSent"
            SentCount         = $sentCount
            TotalCount        = $totalCount
            DeliveredObCount  = $deliveredObCount
            FailedObCount     = 0
            ShouldCommitState = $true
        }
    }

    $failedObIds = @(
        foreach ($fp in $failedPages) {
            $ids = Get-JsonPropValue $fp "ob_ids"
            if ($null -ne $ids) {
                foreach ($obId in @($ids)) {
                    $obKey = [string]$obId
                    if (-not [string]::IsNullOrWhiteSpace($obKey) -and -not $deliveredObSet.ContainsKey($obKey)) {
                        $obKey
                    }
                }
            }
        }
    )

    if ($sentCount -eq 0) {
        return [pscustomobject]@{
            Status            = "NoneSent"
            SentCount         = 0
            TotalCount        = $totalCount
            DeliveredObCount  = 0
            FailedObCount     = $failedObIds.Count
            ShouldCommitState = $false
        }
    }

    if (Test-Path -LiteralPath $StateTmpPath) {
        $stateRaw = Get-Content -LiteralPath $StateTmpPath -Raw -Encoding UTF8
        $stateObj = $stateRaw | ConvertFrom-Json
        $notified = Get-JsonPropValue $stateObj "notified"
        if ($null -ne $notified) {
            foreach ($failedObId in $failedObIds) {
                $null = $notified.PSObject.Properties.Remove([string]$failedObId)
            }
        }
        $updatedJson = $stateObj | ConvertTo-Json -Depth 10
        Write-Utf8NoBomFile -Path $StateTmpPath -Content $updatedJson
    }

    return [pscustomobject]@{
        Status            = "PartialSent"
        SentCount         = $sentCount
        TotalCount        = $totalCount
        DeliveredObCount  = $deliveredObCount
        FailedObCount     = $failedObIds.Count
        ShouldCommitState = $true
    }
}

function Update-WhatsAppResultRecordCounts {
    <#
    .SYNOPSIS
        Atualiza `record_counts` em `*_result.json` apos envio parcial em lote, mantendo UTF-8 sem BOM.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$ResultPath,

        [Parameter(Mandatory)]
        [int]$DeliveredObCount,

        [Parameter(Mandatory)]
        [int]$SentPages,

        [Parameter(Mandatory)]
        [int]$TotalPages
    )

    if (-not (Test-Path -LiteralPath $ResultPath)) { return }
    $raw = Get-Content -LiteralPath $ResultPath -Raw -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace($raw)) { return }
    $resultObj = $raw | ConvertFrom-Json
    $rc = Get-JsonPropValue $resultObj "record_counts"
    if ($null -eq $rc) { return }

    $rc | Add-Member -NotePropertyName "notified" -NotePropertyValue $DeliveredObCount -Force
    if ($null -ne $rc.PSObject.Properties["sent"]) {
        $rc.sent = $DeliveredObCount
    }
    $rc | Add-Member -NotePropertyName "pages_sent" -NotePropertyValue $SentPages -Force
    $rc | Add-Member -NotePropertyName "pages_total" -NotePropertyValue $TotalPages -Force

    $json = $resultObj | ConvertTo-Json -Depth 10
    Write-Utf8NoBomFile -Path $ResultPath -Content $json
}

function Get-WhatsAppDaemonRoute {
    <#
    .SYNOPSIS
        Decide por qual rota um envio WhatsApp deve seguir (funcao pura, sem I/O).
    .DESCRIPTION
        'spawn'  : nenhum processo do daemon vivo, ou daemon vivo de OUTRO perfil (client_id do health
                   diferente do perfil deste envio) -> fluxo atual (sobe node + WhatsApp-Core.js).
        'defer'  : daemon vivo no MESMO perfil e nao pronto (estado diferente de 'ready'), ou health
                   indisponivel / 401 -> nao sobe node (conflitaria com o perfil do daemon); exit 22.
        'daemon' : daemon vivo, mesmo perfil e 'ready' -> envia pelo daemon (POST /batch ou POST /send).
        WHATSAPP_DAEMON_ENABLED nao e' entrada desta regra: ele governa apenas a subida do daemon.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)]
        [bool]$DaemonRunning,

        [string]$ClientId = "",

        [string]$HealthState = "",

        [string]$HealthClientId = ""
    )

    if (-not $DaemonRunning) { return "spawn" }
    if (-not [string]::IsNullOrEmpty($HealthClientId) -and $HealthClientId -ne $ClientId) { return "spawn" }
    if ($HealthState -ne "ready") { return "defer" }
    return "daemon"
}

function Get-WhatsAppHttpErrorInfo {
    <#
    .SYNOPSIS
        Extrai status HTTP e objeto de resposta de um erro de Invoke-WebRequest/Invoke-RestMethod.
    .DESCRIPTION
        No PS 5.1 o erro HTTP chega como System.Net.WebException com a propriedade Response.
        A leitura usa PSObject.Properties: com Set-StrictMode, ler propriedade inexistente lanca erro.
        Sem resposta HTTP (queda de conexao, sem Response) devolve Resposta = $null e Status = 0.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)]
        $ErrorRecord
    )

    $excecao = $ErrorRecord.Exception
    $respostaProp = $null
    if ($null -ne $excecao) { $respostaProp = $excecao.PSObject.Properties['Response'] }
    $resposta = $null
    if ($null -ne $respostaProp) { $resposta = $respostaProp.Value }

    $status = 0
    if ($null -ne $resposta) {
        $statusProp = $resposta.PSObject.Properties['StatusCode']
        if ($null -ne $statusProp -and $null -ne $statusProp.Value) {
            $status = [int]$statusProp.Value
        }
    }

    return [pscustomobject]@{ Status = $status; Resposta = $resposta }
}

function Read-WhatsAppHttpErrorBody {
    <#
    .SYNOPSIS
        Le o corpo textual de uma resposta de erro HTTP tanto em PS 5.1 quanto em PS 7+.
    .DESCRIPTION
        No PS 7+, Invoke-WebRequest costuma preencher ErrorDetails.Message e a resposta e'
        HttpResponseMessage (Content.ReadAsStringAsync); no PS 5.1 a resposta e'
        HttpWebResponse (GetResponseStream). Em qualquer falha de leitura devolve "".
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        $ErrorRecord = $null,
        $Resposta = $null
    )

    if ($null -ne $ErrorRecord) {
        $detalhesProp = $ErrorRecord.PSObject.Properties['ErrorDetails']
        if ($null -ne $detalhesProp -and $null -ne $detalhesProp.Value) {
            $msgProp = $detalhesProp.Value.PSObject.Properties['Message']
            if ($null -ne $msgProp -and -not [string]::IsNullOrWhiteSpace([string]$msgProp.Value)) {
                return [string]$msgProp.Value
            }
        }
    }

    if ($null -eq $Resposta) { return "" }

    $metodoStream = $Resposta.PSObject.Methods['GetResponseStream']
    if ($null -ne $metodoStream) {
        try {
            $stream = $Resposta.GetResponseStream()
            if ($null -ne $stream) {
                $leitor = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8)
                try { return $leitor.ReadToEnd() } finally { $leitor.Dispose() }
            }
        }
        catch [System.Exception] {
            return ""
        }
        return ""
    }

    $contentProp = $Resposta.PSObject.Properties['Content']
    if ($null -ne $contentProp -and $null -ne $contentProp.Value) {
        $readAsync = $contentProp.Value.PSObject.Methods['ReadAsStringAsync']
        if ($null -ne $readAsync) {
            try {
                return [string]$contentProp.Value.ReadAsStringAsync().GetAwaiter().GetResult()
            }
            catch [System.Exception] {
                return ""
            }
        }
    }

    return ""
}

function Get-WhatsAppDaemonEnvironment {
    <#
    .SYNOPSIS
        Monta o ambiente minimo (Zero Trust) para o processo node do daemon WhatsApp.
    .DESCRIPTION
        Filtra o ambiente do processo pai por uma allowlist estrita de variaveis de
        sistema, Node e Chrome/WhatsApp, descartando credenciais do Orchestrator e do
        Oracle (ORCHESTRATOR_API_KEY, ORACLE_*, etc.) e anexando WHATSAPP_DAEMON_*.
    #>
    [CmdletBinding()]
    [OutputType([hashtable])]
    param(
        [Parameter(Mandatory)]
        [string]$Token,

        [Parameter(Mandatory)]
        [string]$Port,

        [Parameter(Mandatory)]
        [string]$ClientId,

        [string]$MaxNotReadyMs = "",

        [string]$AuthPath = "",

        [System.Collections.IDictionary]$SourceEnvironment = $null
    )

    if ($null -eq $SourceEnvironment) {
        $SourceEnvironment = [Environment]::GetEnvironmentVariables()
    }

    $allowlist = [System.Collections.Generic.HashSet[string]]::new(
        [System.StringComparer]::OrdinalIgnoreCase
    )
    foreach ($nomePermitido in @(
            "SystemRoot", "SystemDrive", "WINDIR", "ComSpec", "PATHEXT", "PATH",
            "TEMP", "TMP", "USERPROFILE", "HOME", "HOMEDRIVE", "HOMEPATH",
            "LOCALAPPDATA", "APPDATA", "PROGRAMDATA", "PROGRAMFILES",
            "PROGRAMFILES(X86)", "COMMONPROGRAMFILES", "COMMONPROGRAMFILES(X86)",
            "COMPUTERNAME", "USERNAME", "USERDOMAIN", "NUMBER_OF_PROCESSORS",
            "OS", "PROCESSOR_ARCHITECTURE",
            "NODE_PATH", "NODE_OPTIONS", "NODE_ENV",
            "CHROME_PATH", "PUPPETEER_EXECUTABLE_PATH", "WHATSAPP_CHROME_PATH",
            "WHATSAPP_AUTH_PATH"
        )) {
        $null = $allowlist.Add($nomePermitido)
    }

    $filtradas = [hashtable]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($chaveObj in $SourceEnvironment.Keys) {
        $chave = [string]$chaveObj
        if ($allowlist.Contains($chave)) {
            $valor = $SourceEnvironment[$chaveObj]
            if ($null -ne $valor) {
                $filtradas[$chave] = [string]$valor
            }
        }
    }

    $filtradas["WHATSAPP_DAEMON_TOKEN"] = $Token
    $filtradas["WHATSAPP_DAEMON_PORT"] = $Port
    $filtradas["WHATSAPP_DAEMON_CLIENT_ID"] = $ClientId
    if (-not [string]::IsNullOrWhiteSpace($MaxNotReadyMs)) {
        $filtradas["WHATSAPP_DAEMON_MAX_NOT_READY_MS"] = $MaxNotReadyMs
    }
    if (-not [string]::IsNullOrWhiteSpace($AuthPath)) {
        $filtradas["WHATSAPP_AUTH_PATH"] = $AuthPath
    }

    return $filtradas
}

function Get-WhatsAppDaemonProcess {
    <#
    .SYNOPSIS
        Lista os node.exe cujo CommandLine referencia whatsapp-daemon.js.
    .DESCRIPTION
        Usa CIM: Get-Process nao expoe CommandLine no PS 5.1. Sem -ThrowOnError, falha de consulta devolve lista vazia.
    #>
    [CmdletBinding()]
    [OutputType([object[]])]
    param(
        [switch]$ThrowOnError
    )

    try {
        $errorAction = if ($ThrowOnError) { "Stop" } else { "SilentlyContinue" }
        $candidatos = Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" -ErrorAction $errorAction
        return @($candidatos | Where-Object { $_.CommandLine -and $_.CommandLine -like "*whatsapp-daemon.js*" })
    }
    catch [System.Exception] {
        if ($ThrowOnError) { throw }
        return @()
    }
}

function Get-WhatsAppDaemonHealth {
    <#
    .SYNOPSIS
        Consulta GET /health do daemon: estado e perfil (client_id) que ele segura.
    .DESCRIPTION
        State    : campo 'state' quando o health responde; 'unauthorized' quando responde HTTP 401
                   (token do daemon nao confere); vazio nos demais casos (sem resposta ou erro).
        ClientId : campo 'client_id' quando presente; vazio nos demais casos.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [string]$Port,
        [string]$Token
    )

    try {
        $saude = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -Method Get -Headers @{ "X-Hub-Daemon-Token" = $Token } -TimeoutSec 5
        $perfilProp = $saude.PSObject.Properties["client_id"]
        $perfil = ""
        if ($null -ne $perfilProp) { $perfil = [string]$perfilProp.Value }
        return [pscustomobject]@{ State = [string]$saude.state; ClientId = $perfil }
    }
    catch [System.Exception] {
        $erro = Get-WhatsAppHttpErrorInfo -ErrorRecord $_
        if ($erro.Status -eq 401) { return [pscustomobject]@{ State = "unauthorized"; ClientId = "" } }
        return [pscustomobject]@{ State = ""; ClientId = "" }
    }
}

function Invoke-WhatsAppDaemonBatch {
    <#
    .SYNOPSIS
        Envia o lote ao daemon (POST /batch) e grava $BatchResultFile com o array results quando houver.
    .DESCRIPTION
        Devolve o exit code do fluxo atual: 200 -> 0; 503 -> 22; qualquer outro status ou falha de
        conexao -> 24. Results parciais de respostas de erro (ex.: 500) tambem sao gravados.
        O token nunca e' escrito em log.
    #>
    [CmdletBinding()]
    [OutputType([int])]
    param(
        [string]$Port,
        [string]$Token,
        [string]$ExecId,
        [string]$ClientId = "",
        [string]$ChatTarget,
        [string]$BatchInputFile,
        [string]$BatchResultFile
    )

    try {
        $lidos = Get-Content -LiteralPath $BatchInputFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $itens = if ($null -ne $lidos) { @($lidos) } else { @() }
        $chatId = if ($ChatTarget.Contains("@")) { $ChatTarget } else { (($ChatTarget -replace '\D', '') + "@c.us") }
        $corpo = [pscustomobject]@{ exec_id = $ExecId; client_id = $ClientId; chat_id = $chatId; items = $itens } | ConvertTo-Json -Depth 6
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($corpo)

        $status = 0
        $texto = ""
        try {
            $resposta = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/batch" -Method Post -Headers @{ "X-Hub-Daemon-Token" = $Token } -Body $bytes -ContentType "application/json; charset=utf-8" -TimeoutSec 1800 -UseBasicParsing
            $status = [int]$resposta.StatusCode
            $texto = [string]$resposta.Content
        }
        catch [System.Exception] {
            $erro = Get-WhatsAppHttpErrorInfo -ErrorRecord $_
            if ($null -eq $erro.Resposta) {
                Write-Host "Daemon WhatsApp nao respondeu ao lote (sem resposta HTTP)." -ForegroundColor Red
                return 24
            }
            $status = $erro.Status
            $texto = Read-WhatsAppHttpErrorBody -ErrorRecord $_ -Resposta $erro.Resposta
        }

        $resultados = $null
        if (-not [string]::IsNullOrWhiteSpace($texto)) {
            try {
                $objeto = $texto | ConvertFrom-Json
                if ($null -ne $objeto.PSObject.Properties["results"]) { $resultados = @($objeto.results) }
            }
            catch [System.Exception] {
                $resultados = $null
            }
        }
        if ($null -ne $resultados) {
            $jsonResultados = ConvertTo-Json -InputObject $resultados -Depth 5
            [System.IO.File]::WriteAllText($BatchResultFile, $jsonResultados, (New-Object System.Text.UTF8Encoding $false))
        }

        if ($status -eq 200) {
            if ($null -eq $resultados -or $resultados.Count -eq 0) { return 4 }
            $temFalha = @($resultados | Where-Object { -not (Get-JsonPropValue $_ "success") }).Count -gt 0
            if ($temFalha) { return 4 }
            return 0
        }
        if ($status -eq 503) { return 22 }
        Write-Host "Daemon WhatsApp respondeu HTTP $status ao lote." -ForegroundColor Red
        return 24
    }
    catch [System.Exception] {
        Write-Host "Falha na chamada ao daemon WhatsApp: $($_.Exception.Message)" -ForegroundColor Red
        return 24
    }
}

function Invoke-WhatsAppDaemonSend {
    <#
    .SYNOPSIS
        Envia uma mensagem unica (texto, ou texto com anexo) ao daemon (POST /send). Usado pelo modo AUTO.
    .DESCRIPTION
        Devolve o exit code do fluxo atual: 200 -> 0; 503 -> 22; 409 (client_mismatch), 500, outro
        status ou falha de conexao -> 24. AttachmentPath vazio envia so o texto. O token nunca e' escrito em log.
    #>
    [CmdletBinding()]
    [OutputType([int])]
    param(
        [string]$Port,
        [string]$Token,
        [string]$ExecId,
        [string]$ClientId,
        [string]$ChatTarget,
        [string]$Caption,
        [string]$AttachmentPath = ""
    )

    try {
        $chatId = if ($ChatTarget.Contains("@")) { $ChatTarget } else { (($ChatTarget -replace '\D', '') + "@c.us") }
        $anexo = $null
        if (-not [string]::IsNullOrWhiteSpace($AttachmentPath)) { $anexo = $AttachmentPath }
        $corpo = [pscustomobject]@{
            exec_id         = $ExecId
            client_id       = $ClientId
            chat_id         = $chatId
            caption         = $Caption
            attachment_path = $anexo
        } | ConvertTo-Json -Depth 4
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($corpo)

        $status = 0
        $texto = ""
        try {
            $resposta = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/send" -Method Post -Headers @{ "X-Hub-Daemon-Token" = $Token } -Body $bytes -ContentType "application/json; charset=utf-8" -TimeoutSec 1800 -UseBasicParsing
            $status = [int]$resposta.StatusCode
        }
        catch [System.Exception] {
            $erro = Get-WhatsAppHttpErrorInfo -ErrorRecord $_
            if ($null -eq $erro.Resposta) {
                Write-Host "Daemon WhatsApp nao respondeu ao envio (sem resposta HTTP)." -ForegroundColor Red
                return 24
            }
            $status = $erro.Status
            $texto = Read-WhatsAppHttpErrorBody -ErrorRecord $_ -Resposta $erro.Resposta
        }

        if ($status -eq 200) { return 0 }
        if ($status -eq 503) { return 22 }
        if ($status -eq 409) {
            Write-Host "Daemon WhatsApp recusou o envio: client_id '$ClientId' nao confere com o perfil do daemon (HTTP 409). Falha de envio (exit 24)." -ForegroundColor Red
            return 24
        }

        $motivo = ""
        if (-not [string]::IsNullOrWhiteSpace($texto)) {
            try {
                $objeto = $texto | ConvertFrom-Json
                $motivoProp = $objeto.PSObject.Properties["error"]
                if ($null -ne $motivoProp) { $motivo = [string]$motivoProp.Value }
            }
            catch [System.Exception] {
                $motivo = ""
            }
        }
        $detalhe = ""
        if (-not [string]::IsNullOrWhiteSpace($motivo)) { $detalhe = " ($motivo)" }
        Write-Host "Daemon WhatsApp respondeu HTTP $status ao envio$detalhe." -ForegroundColor Red
        return 24
    }
    catch [System.Exception] {
        Write-Host "Falha na chamada ao daemon WhatsApp: $($_.Exception.Message)" -ForegroundColor Red
        return 24
    }
}

function Select-WhatsAppStaleProcessIds {
    <#
    .SYNOPSIS
        Escolhe os PIDs que a limpeza pre-envio pode encerrar (funcao pura, sem I/O).
    .DESCRIPTION
        Recebe a lista de processos (ProcessId, ParentProcessId, Name, CommandLine, ExecutablePath,
        CreationDate) e os PIDs do daemon WhatsApp. O proprio daemon e TODA a sua arvore de descendentes
        (ParentProcessId recursivo, incluindo os chrome.exe do Puppeteer) ficam protegidos. Fora isso,
        so' e' selecionado chrome.exe/node.exe de 'Automacoes' com mais de 10 s de vida.
    #>
    [CmdletBinding()]
    [OutputType([int[]])]
    param(
        [AllowEmptyCollection()]
        [object[]]$Processes = @(),

        [AllowEmptyCollection()]
        [int[]]$DaemonPids = @(),

        [datetime]$Now = [DateTime]::Now
    )

    $filhosPorPai = @{}
    foreach ($proc in @($Processes)) {
        if ($null -eq $proc) { continue }
        $pai = [int](Get-JsonPropValue $proc "ParentProcessId")
        if (-not $filhosPorPai.ContainsKey($pai)) {
            $filhosPorPai[$pai] = New-Object 'System.Collections.Generic.List[int]'
        }
        $filhosPorPai[$pai].Add([int](Get-JsonPropValue $proc "ProcessId"))
    }

    $protegidos = New-Object 'System.Collections.Generic.HashSet[int]'
    $fila = New-Object 'System.Collections.Generic.Queue[int]'
    foreach ($idDaemon in @($DaemonPids)) {
        if ($protegidos.Add([int]$idDaemon)) { $fila.Enqueue([int]$idDaemon) }
    }
    while ($fila.Count -gt 0) {
        $atual = $fila.Dequeue()
        if (-not $filhosPorPai.ContainsKey($atual)) { continue }
        foreach ($filho in $filhosPorPai[$atual]) {
            if ($protegidos.Add($filho)) { $fila.Enqueue($filho) }
        }
    }

    $selecionados = New-Object 'System.Collections.Generic.List[int]'
    foreach ($proc in @($Processes)) {
        if ($null -eq $proc) { continue }
        $id = [int](Get-JsonPropValue $proc "ProcessId")
        if ($protegidos.Contains($id)) { continue }
        $nome = [string](Get-JsonPropValue $proc "Name")
        if ($nome -ne "chrome.exe" -and $nome -ne "node.exe") { continue }
        $cmd = [string](Get-JsonPropValue $proc "CommandLine")
        $caminho = [string](Get-JsonPropValue $proc "ExecutablePath")
        if ($cmd -like "*whatsapp-daemon.js*") { continue }
        if (-not (($cmd -like "*Automacoes*") -or ($caminho -like "*Automacoes*"))) { continue }
        $criacao = Get-JsonPropValue $proc "CreationDate"
        if ($null -ne $criacao -and (($Now - [datetime]$criacao).TotalSeconds -lt 10)) { continue }
        $selecionados.Add($id)
    }

    return $selecionados.ToArray()
}

Export-ModuleMember -Function Read-CardsManifest, Write-WhatsAppBatchInput, Resolve-WhatsAppBatchDelivery, Update-WhatsAppResultRecordCounts, Get-WhatsAppDaemonRoute, Get-WhatsAppDaemonProcess, Get-WhatsAppDaemonHealth, Invoke-WhatsAppDaemonBatch, Invoke-WhatsAppDaemonSend, Select-WhatsAppStaleProcessIds, Read-WhatsAppHttpErrorBody, Get-WhatsAppDaemonEnvironment

