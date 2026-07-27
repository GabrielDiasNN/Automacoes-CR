#
# Testes da idempotencia de entrega por canal (achado A1).
#
# Estes testes sao a rede de seguranca da migracao dos run.ps1: como as
# automacoes reais dependem de Oracle/Outlook/WhatsApp e nao podem ser
# executadas aqui, o contrato de supressao/reenvio precisa estar coberto no
# nivel da biblioteca — incluindo os casos degradados (JSON corrompido, state
# ausente, hash vazio) que sao justamente onde as copias divergiam.
#

$MigradosParaLib = @(
    "Receitas Bloqueadas",
    "Receitas Emitidas",
    "Montagem de Terceirizados"
)

BeforeAll {
    $libRoot = Split-Path -Parent $PSScriptRoot
    Import-Module (Join-Path $libRoot "Lib-Idempotency.psm1") -Force
}

Describe "Get-LastContentHash" {
    It "Prefere o state provisorio (.tmp) ao definitivo" {
        $tmp = Join-Path $TestDrive "state.tmp"
        $final = Join-Path $TestDrive "state.json"
        '{"last_hash":"NOVO"}' | Set-Content -LiteralPath $tmp -Encoding UTF8
        '{"last_hash":"ANTIGO"}' | Set-Content -LiteralPath $final -Encoding UTF8

        Get-LastContentHash -StateTmpPath $tmp -StatePath $final | Should -Be "NOVO"
    }

    It "Usa o state definitivo quando nao ha .tmp" {
        $final = Join-Path $TestDrive "somente-final.json"
        '{"last_hash":"ANTIGO"}' | Set-Content -LiteralPath $final -Encoding UTF8

        Get-LastContentHash -StateTmpPath (Join-Path $TestDrive "inexistente.tmp") -StatePath $final |
            Should -Be "ANTIGO"
    }

    It "Retorna vazio quando nenhum state existe" {
        Get-LastContentHash -StateTmpPath (Join-Path $TestDrive "a.tmp") -StatePath (Join-Path $TestDrive "b.json") |
            Should -Be ""
    }

    It "Retorna vazio quando o JSON esta corrompido, sem lancar" {
        $corrupted = Join-Path $TestDrive "corrompido.json"
        '{"last_hash": ' | Set-Content -LiteralPath $corrupted -Encoding UTF8

        { Get-LastContentHash -StatePath $corrupted } | Should -Not -Throw
        Get-LastContentHash -StatePath $corrupted | Should -Be ""
    }

    It "Nao cai para o definitivo quando o .tmp esta corrompido" {
        # O hash antigo do definitivo casaria com o last_sent_hash ja gravado e
        # suprimiria a notificacao desta execucao. Vazio mantem o canal pendente.
        $tmp = Join-Path $TestDrive "quebrado.tmp"
        $final = Join-Path $TestDrive "bom.json"
        'nao é json' | Set-Content -LiteralPath $tmp -Encoding UTF8
        '{"last_hash":"ANTIGO"}' | Set-Content -LiteralPath $final -Encoding UTF8

        Get-LastContentHash -StateTmpPath $tmp -StatePath $final | Should -Be ""
    }

    It "Avisa o chamador quando o state existente esta ilegivel" {
        $tmp = Join-Path $TestDrive "avisa.tmp"
        'nao é json' | Set-Content -LiteralPath $tmp -Encoding UTF8
        $avisos = [System.Collections.ArrayList]::new()

        $hash = Get-LastContentHash -StateTmpPath $tmp -OnWarning {
            param($mensagem)
            [void]$avisos.Add($mensagem)
        }

        $hash | Should -Be ""
        $avisos.Count | Should -Be 1
    }

    It "Trata .tmp sem 'last_hash' como hash ausente" {
        $tmp = Join-Path $TestDrive "sem-campo.tmp"
        $final = Join-Path $TestDrive "com-campo.json"
        '{"outro":"valor"}' | Set-Content -LiteralPath $tmp -Encoding UTF8
        '{"last_hash":"ANTIGO"}' | Set-Content -LiteralPath $final -Encoding UTF8

        Get-LastContentHash -StateTmpPath $tmp -StatePath $final | Should -Be ""
    }

    It ".tmp corrompido com entrega ja registrada deixa o canal PENDENTE" {
        # Cenario completo do achado: sem a distincao entre ausente e ilegivel, a
        # notificacao desta execucao seria suprimida com a execucao reportando sucesso.
        $tmp = Join-Path $TestDrive "cenario.tmp"
        $final = Join-Path $TestDrive "cenario-state.json"
        $deliveryPath = Join-Path $TestDrive "cenario-delivery.json"

        'truncad' | Set-Content -LiteralPath $tmp -Encoding UTF8
        '{"last_hash":"HASH-A"}' | Set-Content -LiteralPath $final -Encoding UTF8

        $anterior = New-DeliveryState -Channels @("email")
        $anterior.last_sent_hash = "HASH-A"
        Set-DeliverySuccess -State $anterior -Channel "email"
        Save-DeliveryState -State $anterior -Path $deliveryPath

        $hash = Get-LastContentHash -StateTmpPath $tmp -StatePath $final
        $state = Read-DeliveryState -Path $deliveryPath -Channels @("email")
        [void](Update-DeliveryStateHash -State $state -CurrentHash $hash)

        Test-DeliveryPending -State $state -Channel "email" -CurrentHash $hash | Should -BeTrue
    }
}

Describe "Read-DeliveryState" {
    It "Devolve estado zerado quando o arquivo nao existe" {
        $state = Read-DeliveryState -Path (Join-Path $TestDrive "nao-existe.json") -Channels @("email")

        $state.last_sent_hash | Should -Be ""
        $state.delivery_status.email.success | Should -BeFalse
    }

    It "Carrega hash e status salvos" {
        $path = Join-Path $TestDrive "delivery-ok.json"
        '{"last_sent_hash":"H1","delivery_status":{"email":{"success":true,"sent_at":"21/07/2026 08:00:00"}}}' |
            Set-Content -LiteralPath $path -Encoding UTF8

        $state = Read-DeliveryState -Path $path -Channels @("email")

        $state.last_sent_hash | Should -Be "H1"
        $state.delivery_status.email.success | Should -BeTrue
        $state.delivery_status.email.sent_at | Should -Be "21/07/2026 08:00:00"
    }

    It "Reinicia o estado quando o JSON esta corrompido e avisa o chamador" {
        $path = Join-Path $TestDrive "delivery-corrompido.json"
        '{"last_sent_hash":' | Set-Content -LiteralPath $path -Encoding UTF8
        $avisos = [System.Collections.ArrayList]::new()

        $state = Read-DeliveryState -Path $path -Channels @("email") -OnWarning {
            param($mensagem)
            [void]$avisos.Add($mensagem)
        }

        $state.last_sent_hash | Should -Be ""
        $state.delivery_status.email.success | Should -BeFalse
        $avisos.Count | Should -Be 1
    }

    It "Zera canal novo ausente no arquivo salvo, preservando os existentes" {
        # Cenario real: script passa a notificar tambem por WhatsApp e encontra
        # um delivery_state.json gravado quando so existia e-mail.
        $path = Join-Path $TestDrive "delivery-legado.json"
        '{"last_sent_hash":"H1","delivery_status":{"email":{"success":true,"sent_at":"x"}}}' |
            Set-Content -LiteralPath $path -Encoding UTF8

        $state = Read-DeliveryState -Path $path -Channels @("email", "whatsapp")

        $state.delivery_status.email.success | Should -BeTrue
        $state.delivery_status.whatsapp.success | Should -BeFalse
    }
}

Describe "Update-DeliveryStateHash" {
    It "Reseta todos os canais quando o conteudo muda" {
        $state = New-DeliveryState -Channels @("email", "whatsapp")
        $state.last_sent_hash = "ANTIGO"
        $state.delivery_status.email.success = $true
        $state.delivery_status.whatsapp.success = $true

        $resetou = Update-DeliveryStateHash -State $state -CurrentHash "NOVO"

        $resetou | Should -BeTrue
        $state.last_sent_hash | Should -Be "NOVO"
        $state.delivery_status.email.success | Should -BeFalse
        $state.delivery_status.whatsapp.success | Should -BeFalse
    }

    It "Preserva sent_at no reset — o carimbo e diagnostico, nao flag de controle" {
        $state = New-DeliveryState -Channels @("email")
        $state.last_sent_hash = "ANTIGO"
        Set-DeliverySuccess -State $state -Channel "email"
        $carimbo = $state.delivery_status.email.sent_at

        [void](Update-DeliveryStateHash -State $state -CurrentHash "NOVO")

        $state.delivery_status.email.success | Should -BeFalse
        $state.delivery_status.email.sent_at | Should -Be $carimbo
    }

    It "Nao mexe no estado quando o hash e o mesmo" {
        $state = New-DeliveryState -Channels @("email")
        $state.last_sent_hash = "H1"
        $state.delivery_status.email.success = $true

        $resetou = Update-DeliveryStateHash -State $state -CurrentHash "H1"

        $resetou | Should -BeFalse
        $state.delivery_status.email.success | Should -BeTrue
    }

    It "Hash vazio nao reseta — sem hash nao ha como afirmar que mudou" {
        $state = New-DeliveryState -Channels @("email")
        $state.last_sent_hash = "H1"
        $state.delivery_status.email.success = $true

        $resetou = Update-DeliveryStateHash -State $state -CurrentHash ""

        $resetou | Should -BeFalse
        $state.delivery_status.email.success | Should -BeTrue
    }
}

Describe "Test-DeliveryPending e Set-DeliverySuccess" {
    It "Canal zerado esta pendente" {
        $state = New-DeliveryState -Channels @("email")
        Test-DeliveryPending -State $state -Channel "email" | Should -BeTrue
    }

    It "Canal marcado deixa de estar pendente e recebe carimbo de data" {
        $state = New-DeliveryState -Channels @("email")

        Set-DeliverySuccess -State $state -Channel "email"

        Test-DeliveryPending -State $state -Channel "email" | Should -BeFalse
        $state.delivery_status.email.sent_at | Should -Match '^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}$'
    }

    It "Canal desconhecido conta como pendente (falha para o lado seguro)" {
        $state = New-DeliveryState -Channels @("email")
        Test-DeliveryPending -State $state -Channel "telegram" | Should -BeTrue
    }

    It "Com -CurrentHash divergente, canal entregue volta a ser pendente" {
        # Caso de borda preservado dos run.ps1: o state de conteudo sumiu ou
        # ficou ilegivel (hash vazio) mas o delivery_state registra entrega de um
        # hash anterior. Reenviar e preferivel a engolir o alerta.
        $state = New-DeliveryState -Channels @("email")
        $state.last_sent_hash = "H1"
        Set-DeliverySuccess -State $state -Channel "email"

        Test-DeliveryPending -State $state -Channel "email" -CurrentHash "" | Should -BeTrue
        Test-DeliveryPending -State $state -Channel "email" -CurrentHash "H1" | Should -BeFalse
    }
}

Describe "Contrato com os run.ps1 migrados" {
    # Trava anti-regressao: impede que a receita volte a ser copiada para dentro
    # dos scripts — foi exatamente assim que as tres copias divergiram.
    # A lista fica no escopo do arquivo, NAO em BeforeAll: o -ForEach do Pester e
    # resolvido na fase de discovery, antes de qualquer BeforeAll rodar — de
    # dentro do bloco, os casos seriam silenciosamente ignorados.
    BeforeAll {
        $script:RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    }

    It "<_> importa Lib-Idempotency.psm1" -ForEach $MigradosParaLib {
        $conteudo = Get-Content -LiteralPath (Join-Path $script:RepoRoot "$_\run.ps1") -Raw
        $conteudo | Should -Match 'Import-Module \$libIdempotency'
    }

    It "<_> nao reimplementa a leitura manual de delivery_status" -ForEach $MigradosParaLib {
        $conteudo = Get-Content -LiteralPath (Join-Path $script:RepoRoot "$_\run.ps1") -Raw
        $conteudo | Should -Not -Match '\$savedState\.delivery_status'
    }

    It "<_> nao persiste delivery_state manualmente" -ForEach $MigradosParaLib {
        $conteudo = Get-Content -LiteralPath (Join-Path $script:RepoRoot "$_\run.ps1") -Raw
        $conteudo | Should -Not -Match '\$deliveryState \| ConvertTo-Json'
    }
}

Describe "Ciclo completo de idempotencia" {
    It "Suprime reenvio do mesmo conteudo e volta a enviar quando o conteudo muda" {
        $deliveryPath = Join-Path $TestDrive "ciclo-delivery.json"
        $statePath = Join-Path $TestDrive "ciclo-state.json"

        # --- Execucao 1: conteudo novo, entrega acontece ---
        '{"last_hash":"HASH-A"}' | Set-Content -LiteralPath $statePath -Encoding UTF8
        $hash1 = Get-LastContentHash -StatePath $statePath
        $state1 = Read-DeliveryState -Path $deliveryPath -Channels @("email")
        [void](Update-DeliveryStateHash -State $state1 -CurrentHash $hash1)
        Test-DeliveryPending -State $state1 -Channel "email" | Should -BeTrue
        Set-DeliverySuccess -State $state1 -Channel "email"
        Save-DeliveryState -State $state1 -Path $deliveryPath

        # --- Execucao 2: mesmo conteudo, deve suprimir ---
        $hash2 = Get-LastContentHash -StatePath $statePath
        $state2 = Read-DeliveryState -Path $deliveryPath -Channels @("email")
        [void](Update-DeliveryStateHash -State $state2 -CurrentHash $hash2)
        Test-DeliveryPending -State $state2 -Channel "email" | Should -BeFalse

        # --- Execucao 3: conteudo mudou, deve reenviar ---
        '{"last_hash":"HASH-B"}' | Set-Content -LiteralPath $statePath -Encoding UTF8
        $hash3 = Get-LastContentHash -StatePath $statePath
        $state3 = Read-DeliveryState -Path $deliveryPath -Channels @("email")
        [void](Update-DeliveryStateHash -State $state3 -CurrentHash $hash3)
        Test-DeliveryPending -State $state3 -Channel "email" | Should -BeTrue
    }

    It "Falha de um canal nao suprime o outro no ciclo seguinte" {
        $deliveryPath = Join-Path $TestDrive "ciclo-parcial.json"
        $state = Read-DeliveryState -Path $deliveryPath -Channels @("email", "whatsapp")
        [void](Update-DeliveryStateHash -State $state -CurrentHash "H1")

        # E-mail entrega, WhatsApp falha (nao marcado).
        Set-DeliverySuccess -State $state -Channel "email"
        Save-DeliveryState -State $state -Path $deliveryPath

        $proximo = Read-DeliveryState -Path $deliveryPath -Channels @("email", "whatsapp")
        [void](Update-DeliveryStateHash -State $proximo -CurrentHash "H1")

        Test-DeliveryPending -State $proximo -Channel "email" | Should -BeFalse
        Test-DeliveryPending -State $proximo -Channel "whatsapp" | Should -BeTrue
    }

    It "Aceita campo extra por canal sem perde-lo na persistencia" {
        # Receitas Bloqueadas grava exit_code no canal whatsapp — diagnostico
        # proprio daquela automacao, fora do contrato generico da lib. O estado
        # devolvido por Read-DeliveryState precisa aceitar a chave extra e
        # carrega-la ate o JSON salvo.
        $path = Join-Path $TestDrive "extra-field.json"
        $state = Read-DeliveryState -Path $path -Channels @("email", "whatsapp")

        $state.delivery_status.whatsapp.ContainsKey("exit_code") | Should -BeFalse
        $state.delivery_status.whatsapp.exit_code = $null
        $state.delivery_status.whatsapp.exit_code = 24
        Set-DeliverySuccess -State $state -Channel "whatsapp"
        Save-DeliveryState -State $state -Path $path

        $salvo = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
        $salvo.delivery_status.whatsapp.exit_code | Should -Be 24
        $salvo.delivery_status.whatsapp.success | Should -BeTrue
    }

    It "Estado salvo e relido sem perda (round-trip do JSON)" {
        $path = Join-Path $TestDrive "roundtrip.json"
        $original = New-DeliveryState -Channels @("email", "whatsapp")
        $original.last_sent_hash = "HASH-RT"
        Set-DeliverySuccess -State $original -Channel "whatsapp"

        Save-DeliveryState -State $original -Path $path
        $relido = Read-DeliveryState -Path $path -Channels @("email", "whatsapp")

        $relido.last_sent_hash | Should -Be "HASH-RT"
        $relido.delivery_status.whatsapp.success | Should -BeTrue
        $relido.delivery_status.whatsapp.sent_at | Should -Be $original.delivery_status.whatsapp.sent_at
        $relido.delivery_status.email.success | Should -BeFalse
    }
}
