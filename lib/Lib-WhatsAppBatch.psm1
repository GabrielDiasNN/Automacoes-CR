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

Export-ModuleMember -Function Read-CardsManifest, Write-WhatsAppBatchInput, Resolve-WhatsAppBatchDelivery, Update-WhatsAppResultRecordCounts

