#
# Lib-WhatsAppBatch.psm1 — cliente PowerShell do daemon WhatsApp (rota, saude, envio em
# lote/unitario) e selecao de processos orfaos. Consumido por lib/Send-WhatsApp.ps1,
# lib/Keep-WhatsApp-Open.ps1 e lib/Authenticate-WhatsApp.bat.
#
# O manifesto paginado (`cards_manifest.json`), a serializacao do `batch_input.json` e a
# reconciliacao parcial via `batch_result.json` vivem em lib/python/hub_whatsapp.py desde
# que as automacoes migraram para o runner Python (1.3.117); as versoes PowerShell foram
# removidas em 1.3.118.
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

Export-ModuleMember -Function Get-WhatsAppDaemonRoute, Get-WhatsAppDaemonProcess, Get-WhatsAppDaemonHealth, Invoke-WhatsAppDaemonBatch, Invoke-WhatsAppDaemonSend, Select-WhatsAppStaleProcessIds, Read-WhatsAppHttpErrorBody, Get-WhatsAppDaemonEnvironment

