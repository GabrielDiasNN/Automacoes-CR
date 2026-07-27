#
# Lib-Idempotency.psm1 — idempotencia de entrega por canal.
#
# Extraido de run.ps1 na revisao arquitetural (achado A1): a mesma receita
# (ler hash -> carregar delivery_state tolerante a corrupcao -> resetar canais
# quando o conteudo muda -> consultar/marcar canal -> persistir) estava
# reimplementada em Receitas Bloqueadas, Receitas Emitidas e Montagem de
# Terceirizados, com divergencias sutis entre as copias.
#
# Escopo deliberado: apenas o modelo "por canal" (email/whatsapp). OBs Paradas
# Fase usa idempotencia por FASE (array `phases` de tamanho variavel por
# execucao) e OBs Fluxo Sem Tingimento resolve idempotencia dentro do Python,
# sem delivery_state — encaixar os dois aqui seria abstracao errada. Ambos
# reaproveitam apenas Get-LastContentHash.
#

Set-StrictMode -Version Latest

function Get-LastContentHash {
    <#
    .SYNOPSIS
        Le o hash do conteudo produzido pela etapa Python.

    .DESCRIPTION
        O script Python grava um state provisorio (.tmp) que so vira definitivo
        apos a entrega confirmada. O hash corrente e, portanto, o do .tmp quando
        ele existe, e o do arquivo definitivo caso contrario.

        Arquivo AUSENTE e arquivo ILEGIVEL nao sao a mesma coisa. Ausente: segue
        para o proximo candidato. Presente porem ilegivel (ou sem `last_hash`):
        devolve "" imediatamente, sem consultar o definitivo — cair para o hash
        antigo faria Test-DeliveryPending casar com o `last_sent_hash` ja gravado
        e SUPRIMIR a notificacao em silencio. Hash vazio mantem o canal pendente,
        que e o lado seguro: no pior caso reenvia.

    .PARAMETER StateTmpPath
        Caminho do state provisorio (.tmp) gravado pelo Python nesta execucao.

    .PARAMETER StatePath
        Caminho do state definitivo, da ultima execucao consolidada.

    .PARAMETER OnWarning
        ScriptBlock opcional chamado com a mensagem quando um state existente
        esta ilegivel (permite ao run.ps1 registrar no log da automacao).
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [string]$StateTmpPath,
        [string]$StatePath,
        [scriptblock]$OnWarning
    )

    foreach ($candidate in @($StateTmpPath, $StatePath)) {
        if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
        if (-not (Test-Path -LiteralPath $candidate)) { continue }

        try {
            $parsed = Get-Content -LiteralPath $candidate -Raw -Encoding UTF8 | ConvertFrom-Json
        } catch [System.Exception] {
            if ($OnWarning) {
                & $OnWarning ("State de conteudo '{0}' esta ilegivel. Hash tratado como ausente (a entrega prossegue). Motivo: {1}" -f $candidate, $_.Exception.Message)
            }
            return ""
        }

        if ($parsed -and $parsed.PSObject.Properties.Name -contains 'last_hash' -and $parsed.last_hash) {
            return [string]$parsed.last_hash
        }

        if ($OnWarning) {
            & $OnWarning ("State de conteudo '{0}' nao traz 'last_hash'. Hash tratado como ausente (a entrega prossegue)." -f $candidate)
        }
        return ""
    }

    return ""
}

function New-DeliveryState {
    <#
    .SYNOPSIS
        Cria a estrutura de estado de entrega zerada para os canais informados.

    .PARAMETER Channels
        Nomes dos canais governados por este estado (ex.: email, whatsapp).
    #>
    [CmdletBinding()]
    [OutputType([hashtable])]
    param(
        [Parameter(Mandatory)]
        [string[]]$Channels
    )

    $status = @{}
    foreach ($channel in $Channels) {
        $status[$channel] = @{ success = $false; sent_at = $null }
    }

    return @{
        last_sent_hash  = ""
        delivery_status = $status
    }
}

function Read-DeliveryState {
    <#
    .SYNOPSIS
        Carrega delivery_state.json normalizado, tolerante a arquivo ausente ou corrompido.

    .DESCRIPTION
        Um delivery_state ilegivel NAO aborta a automacao: o estado volta ao
        zerado, o que no pior caso reenvia uma notificacao — preferivel a
        suprimir um alerta operacional por causa de um JSON truncado.

        Canais ausentes no arquivo salvo ficam com o default zerado, de modo que
        adicionar um canal novo ao script nao exige migrar o arquivo em disco.

    .PARAMETER Path
        Caminho do delivery_state.json.

    .PARAMETER Channels
        Canais esperados pelo chamador.

    .PARAMETER OnWarning
        ScriptBlock opcional chamado com a mensagem quando o arquivo esta
        corrompido (permite ao run.ps1 registrar no log da automacao).
    #>
    [CmdletBinding()]
    [OutputType([hashtable])]
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [Parameter(Mandatory)]
        [string[]]$Channels,

        [scriptblock]$OnWarning
    )

    $state = New-DeliveryState -Channels $Channels

    if (-not (Test-Path -LiteralPath $Path)) {
        return $state
    }

    try {
        $saved = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch [System.Exception] {
        if ($OnWarning) {
            & $OnWarning ("Falha ao ler '{0}'. Estado de entrega reiniciado. Motivo: {1}" -f $Path, $_.Exception.Message)
        }
        return $state
    }

    if (-not $saved) { return $state }

    $savedNames = $saved.PSObject.Properties.Name
    if (($savedNames -contains 'last_sent_hash') -and $saved.last_sent_hash) {
        $state.last_sent_hash = [string]$saved.last_sent_hash
    }

    if (-not ($savedNames -contains 'delivery_status') -or -not $saved.delivery_status) {
        return $state
    }

    $statusNames = $saved.delivery_status.PSObject.Properties.Name
    foreach ($channel in $Channels) {
        if ($statusNames -notcontains $channel) { continue }
        $savedChannel = $saved.delivery_status.$channel
        if (-not $savedChannel) { continue }

        $channelNames = $savedChannel.PSObject.Properties.Name
        if ($channelNames -contains 'success') {
            $state.delivery_status[$channel].success = [bool]$savedChannel.success
        }
        if ($channelNames -contains 'sent_at') {
            $state.delivery_status[$channel].sent_at = $savedChannel.sent_at
        }
    }

    return $state
}

function Update-DeliveryStateHash {
    <#
    .SYNOPSIS
        Reseta o status dos canais quando o conteudo mudou desde a ultima entrega.

    .DESCRIPTION
        Retorna $true se houve reset (conteudo novo), $false se o hash e o mesmo
        ou se nao ha hash corrente — nesses casos o estado fica intacto.

        Hash vazio nao reseta de proposito: sem hash nao ha como afirmar que o
        conteudo mudou, e zerar o estado provocaria reenvio a cada execucao.

        O reset zera apenas `success`; `sent_at` e preservado por ser carimbo de
        diagnostico ("quando o alerta saiu pela ultima vez"), nao flag de
        controle. E o comportamento das tres implementacoes originais.

    .PARAMETER State
        Estado devolvido por Read-DeliveryState (modificado no lugar).

    .PARAMETER CurrentHash
        Hash do conteudo desta execucao.
    #>
    [CmdletBinding()]
    [OutputType([bool])]
    param(
        [Parameter(Mandatory)]
        [hashtable]$State,

        [string]$CurrentHash
    )

    if ([string]::IsNullOrWhiteSpace($CurrentHash)) { return $false }
    if ($CurrentHash -eq $State.last_sent_hash) { return $false }

    $State.last_sent_hash = $CurrentHash
    foreach ($channel in @($State.delivery_status.Keys)) {
        $State.delivery_status[$channel].success = $false
    }

    return $true
}

function Test-DeliveryPending {
    <#
    .SYNOPSIS
        Indica se o canal ainda precisa entregar este conteudo.

    .DESCRIPTION
        $false significa "ja entregue, pode suprimir". Canal desconhecido conta
        como pendente: e mais seguro enviar de novo do que suprimir por engano.

        Informar -CurrentHash reproduz a condicao composta original dos run.ps1
        (`success -and $currentHash -eq $last_sent_hash`), que importa num caso de
        borda real: quando o hash corrente esta indisponivel (state ilegivel ou
        ausente) mas o delivery_state registra entrega de um hash anterior, o
        canal volta a ser PENDENTE. Suprimir ali arriscaria engolir um alerta
        operacional so porque o state de conteudo se perdeu.

    .PARAMETER State
        Estado de entrega corrente.

    .PARAMETER Channel
        Nome do canal.

    .PARAMETER CurrentHash
        Hash do conteudo desta execucao. Quando omitido, so o flag de sucesso e
        considerado.
    #>
    [CmdletBinding()]
    [OutputType([bool])]
    param(
        [Parameter(Mandatory)]
        [hashtable]$State,

        [Parameter(Mandatory)]
        [string]$Channel,

        [string]$CurrentHash
    )

    if (-not $State.delivery_status.ContainsKey($Channel)) { return $true }
    if (-not [bool]$State.delivery_status[$Channel].success) { return $true }

    if ($PSBoundParameters.ContainsKey('CurrentHash') -and $CurrentHash -ne $State.last_sent_hash) {
        return $true
    }

    return $false
}

function Set-DeliverySuccess {
    <#
    .SYNOPSIS
        Marca o canal como entregue, carimbando a data no padrao BR do hub.

    .PARAMETER State
        Estado de entrega corrente (modificado no lugar).

    .PARAMETER Channel
        Nome do canal entregue.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [hashtable]$State,

        [Parameter(Mandatory)]
        [string]$Channel
    )

    if (-not $State.delivery_status.ContainsKey($Channel)) {
        $State.delivery_status[$Channel] = @{ success = $false; sent_at = $null }
    }

    $State.delivery_status[$Channel].success = $true
    $State.delivery_status[$Channel].sent_at = (Get-Date -Format 'dd/MM/yyyy HH:mm:ss')
}

function Save-DeliveryState {
    <#
    .SYNOPSIS
        Persiste o estado de entrega em disco.

    .PARAMETER State
        Estado de entrega a gravar.

    .PARAMETER Path
        Caminho do delivery_state.json.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [hashtable]$State,

        [Parameter(Mandatory)]
        [string]$Path
    )

    $State | ConvertTo-Json -Depth 5 | Out-File -LiteralPath $Path -Encoding UTF8
}

Export-ModuleMember -Function Get-LastContentHash, New-DeliveryState, Read-DeliveryState, Update-DeliveryStateHash, Test-DeliveryPending, Set-DeliverySuccess, Save-DeliveryState
