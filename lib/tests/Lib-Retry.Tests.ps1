BeforeAll {
    $here = $PSScriptRoot
    if ([string]::IsNullOrWhiteSpace($here)) {
        $here = Split-Path -Parent $PSCommandPath
    }
    $libRoot = Split-Path -Parent $here
    Import-Module (Join-Path $libRoot "Lib-Retry.psm1") -Force

    # Garante simbolo global disponivel para Mock mesmo sem carregar Outlook COM.
    if (-not (Get-Command Send-OutlookEmail -ErrorAction SilentlyContinue)) {
        function global:Send-OutlookEmail {
            param($To, $Subject, $HtmlBody, $ExecId, $LogPath)
            return $true
        }
    }
}

Describe "Send-AlertaFalhaDefinitiva" {
    BeforeEach {
        $script:prevAlertEmail = [Environment]::GetEnvironmentVariable("AUTOMACAO_ALERT_EMAIL", "Process")
    }

    AfterEach {
        [Environment]::SetEnvironmentVariable("AUTOMACAO_ALERT_EMAIL", $script:prevAlertEmail, "Process")
    }

    It "suprime envio com warning quando AUTOMACAO_ALERT_EMAIL nao esta definido" {
        [Environment]::SetEnvironmentVariable("AUTOMACAO_ALERT_EMAIL", $null, "Process")
        Mock Send-OutlookEmail -ModuleName Lib-Retry { return $true }

        $warnings = @()
        Send-AlertaFalhaDefinitiva -TaskName "RE-03" -ExecId "E1" -WarningVariable warnings 3>$null

        Should -Invoke Send-OutlookEmail -ModuleName Lib-Retry -Times 0 -Exactly
        ($warnings -join " ") | Should -Match "AUTOMACAO_ALERT_EMAIL"
    }

    It "envia e-mail de alerta via Send-OutlookEmail quando AUTOMACAO_ALERT_EMAIL esta definido" {
        [Environment]::SetEnvironmentVariable("AUTOMACAO_ALERT_EMAIL", "alertas@empresa.local", "Process")
        Mock Send-OutlookEmail -ModuleName Lib-Retry { return $true }
        $fakeLog = Join-Path $TestDrive "alerta.jsonl"

        Send-AlertaFalhaDefinitiva `
            -TaskName "RB-01" `
            -ExecId "EXEC_99" `
            -UltimoErro "ORA-01017 simulado" `
            -Tentativas 3 `
            -LogPath $fakeLog

        Should -Invoke Send-OutlookEmail -ModuleName Lib-Retry -Times 1 -Exactly -ParameterFilter {
            ($To -eq "alertas@empresa.local") -and
            ($Subject -match "RB-01") -and
            ($HtmlBody -match "EXEC_99") -and
            ($HtmlBody -match "ORA-01017 simulado") -and
            ($HtmlBody -match "3 tentativas") -and
            ($ExecId -eq "EXEC_99") -and
            ($LogPath -eq $fakeLog)
        }
    }
}