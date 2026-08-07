$here = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($here)) {
    $here = Split-Path -Parent $PSCommandPath
}

$sut = (Split-Path -Parent $here) + "\Lib-Logging.psm1"

Import-Module $sut -Force

Describe "Lib-Logging Tests" {
    Context "Write-AutomacaoLog" {
        It "Should execute without errors" {
            $tempLog = Join-Path $TestDrive "test.log"
            { Write-AutomacaoLog -Message "Test message" -Level "INFO" -LogPath $tempLog } | Should -Not -Throw
            if (Test-Path $tempLog) { Remove-Item $tempLog -Force }
        }
    }

    Context "Get-ForwardedLogLevel" {
        # Centralizada a partir de tres copias em run.ps1 (achado A1 da revisao
        # arquitetural). Os run.ps1 chamam com -Msg, por isso o alias e testado.
        It "Normaliza ERROR para ERRO" {
            Get-ForwardedLogLevel -Message "[ERROR] falha na extracao" | Should -Be "ERRO"
        }

        It "Aceita ERRO ja no padrao do hub" {
            Get-ForwardedLogLevel -Message "[ERRO] falha" | Should -Be "ERRO"
        }

        It "Detecta o marcador sem diferenciar maiuscula de minuscula" {
            Get-ForwardedLogLevel -Message "[warn] atencao" | Should -Be "WARN"
        }

        It "Preserva DEBUG" {
            Get-ForwardedLogLevel -Message "[DEBUG] detalhe" | Should -Be "DEBUG"
        }

        It "Usa o fallback quando a linha nao tem marcador" {
            Get-ForwardedLogLevel -Message "linha sem marcador" -Fallback "WARN" | Should -Be "WARN"
        }

        It "Usa INFO como fallback padrao em linha vazia" {
            Get-ForwardedLogLevel -Message "" | Should -Be "INFO"
        }

        It "Aceita o alias -Msg usado pelos run.ps1" {
            Get-ForwardedLogLevel -Msg "[ERROR] via alias" | Should -Be "ERRO"
        }
    }

    Context "Get-AutomationExitStatus" {
        # Extraida de Exit-AutomationWithCode, que centraliza a classificacao
        # que tinha divergido entre 4 run.ps1 (achado de qualidade da revisao
        # arquitetural): -eq 0, -eq 0 -or -eq 2, -in $NonFailureCodes.
        It "Codigo 0 sem NonFailureCodes explicito (padrao) e sucesso" {
            Get-AutomationExitStatus -Code 0 | Should -BeTrue
        }

        It "Codigo diferente de 0 sem NonFailureCodes explicito e falha" {
            Get-AutomationExitStatus -Code 1 | Should -BeFalse
        }

        It "Padrao de Receitas Bloqueadas/OBs Paradas Fase: 0 e 2 sao sucesso" {
            Get-AutomationExitStatus -Code 2 -NonFailureCodes @(0, 2) | Should -BeTrue
            Get-AutomationExitStatus -Code 9 -NonFailureCodes @(0, 2) | Should -BeFalse
        }

        It "Padrao de OBs Fluxo Sem Tingimento: 22 (canal pendente) e sucesso" {
            Get-AutomationExitStatus -Code 22 -NonFailureCodes @(0, 2, 22) | Should -BeTrue
        }

        It "Codigo fora da lista de NonFailureCodes e sempre falha" {
            Get-AutomationExitStatus -Code 22 -NonFailureCodes @(0, 2) | Should -BeFalse
        }
    }
}
