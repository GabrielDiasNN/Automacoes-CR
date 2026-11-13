BeforeAll {
    $here = $PSScriptRoot
    if ([string]::IsNullOrWhiteSpace($here)) {
        $here = Split-Path -Parent $PSCommandPath
    }
    $repoRoot = Split-Path -Parent (Split-Path -Parent $here)
    Import-Module (Join-Path $repoRoot "lib\Lib-WhatsAppBatch.psm1") -Force

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
