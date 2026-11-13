BeforeAll {
    $here = $PSScriptRoot
    if ([string]::IsNullOrWhiteSpace($here)) {
        $here = Split-Path -Parent $PSCommandPath
    }
    $repoRoot = Split-Path -Parent (Split-Path -Parent $here)
    $sendScript = Join-Path $repoRoot "lib\Send-WhatsApp.ps1"
    $psExe = (Get-Process -Id $PID).Path
}

Describe "Send-WhatsApp.ps1" {
    It "encerra com ExitCode 22 quando app.enabled ou target.enabled esta desabilitado (bool ou string) e nao grava BatchResultFile" {
        $dir = Join-Path $TestDrive ("send_wa_disabled_" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        try {
            $cfgPath = Join-Path $dir "whatsapp-config.json"
            $batchInput = Join-Path $dir "batch_input.json"
            $batchResult = Join-Path $dir "batch_result.json"
            [System.IO.File]::WriteAllText($batchInput, '[{"phase_key":"page_01","image_path":"card.png","caption":"ok"}]', (New-Object System.Text.UTF8Encoding $false))

            $cfgObj = @{
                app    = @{ enabled = "false" }
                target = @{ contactPhone = "5511999999999"; enabled = $true }
                auth   = @{ clientId = "test-disabled" }
            } | ConvertTo-Json -Depth 5
            [System.IO.File]::WriteAllText($cfgPath, $cfgObj, (New-Object System.Text.UTF8Encoding $false))

            $out = & $psExe -NoProfile -ExecutionPolicy Bypass -File $sendScript `
                -ConfigPath $cfgPath -Mode BATCH -BatchInputFile $batchInput -BatchResultFile $batchResult 2>&1
            $LASTEXITCODE | Should -Be 22
            ($out -join "`n") | Should -Match "desabilitado"
            Test-Path -LiteralPath $batchResult | Should -BeFalse
        }
        finally {
            Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It "adia com ExitCode 22 sem remover Default\\Lock quando o mutex nomeado do clientId ja esta ocupado" {
        $dir = Join-Path $TestDrive ("send_wa_lock_" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        $clientId = "pester-lock-" + [guid]::NewGuid().ToString("N").Substring(0, 8)
        $mutexName = "Global\AutomationHub_WA_$clientId"

        $prevAuth = $env:WHATSAPP_AUTH_PATH
        $sessionDefaultDir = Join-Path $dir "session-$clientId\Default"
        New-Item -ItemType Directory -Path $sessionDefaultDir -Force | Out-Null
        $lockFile = Join-Path $sessionDefaultDir "Lock"
        [System.IO.File]::WriteAllText($lockFile, "lock-ativo", (New-Object System.Text.UTF8Encoding $false))
        $env:WHATSAPP_AUTH_PATH = $dir

        $psThread = [PowerShell]::Create()
        $readyEvent = New-Object System.Threading.ManualResetEventSlim($false)
        $releaseEvent = New-Object System.Threading.ManualResetEventSlim($false)
        try {
            $null = $psThread.AddScript({
                param($mName, $ready, $release)
                $m = New-Object System.Threading.Mutex($false, $mName)
                $owned = $false
                try {
                    $owned = $m.WaitOne(5000)
                    $ready.Set()
                    $null = $release.Wait(15000)
                }
                finally {
                    if ($owned) {
                        try { $m.ReleaseMutex() } catch [System.ApplicationException] {}
                    }
                    $m.Dispose()
                }
            }).AddArgument($mutexName).AddArgument($readyEvent).AddArgument($releaseEvent)

            $asyncHandle = $psThread.BeginInvoke()
            $readyEvent.Wait(5000) | Should -BeTrue

            $out = & $psExe -NoProfile -ExecutionPolicy Bypass -File $sendScript `
                -Message "teste" -Phone "5511999999999" -ClientId $clientId -SessionLockTimeoutMs 100 2>&1
            $LASTEXITCODE | Should -Be 22
            ($out -join "`n") | Should -Match "Adiando envio com exit 22"
            Test-Path -LiteralPath $lockFile | Should -BeTrue
        }
        finally {
            $releaseEvent.Set()
            if ($asyncHandle) {
                try { $psThread.EndInvoke($asyncHandle) } catch [System.Exception] {}
            }
            $psThread.Dispose()
            $readyEvent.Dispose()
            $releaseEvent.Dispose()
            if ($null -eq $prevAuth) {
                Remove-Item Env:\WHATSAPP_AUTH_PATH -ErrorAction SilentlyContinue
            }
            else {
                $env:WHATSAPP_AUTH_PATH = $prevAuth
            }
            Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}
