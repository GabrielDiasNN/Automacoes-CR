# Teste do achado #12 (revisao stateless de 25/08/2026): o fallback de destino em
# whatsapp-config.json (ex.: "550000000000-0000000000@g.us") e' um grupo/numero que nao
# existe. Antes desta correcao, se a variavel de ambiente de contactIdEnv estivesse
# ausente/vazia, Send-WhatsApp.ps1 enviava silenciosamente para esse placeholder em vez de
# falhar. Resolve-WhatsAppTarget (lib/Lib-Config.psm1) centraliza essa decisao e falha cedo.

BeforeAll {
    $script:LibRoot = Split-Path -Parent $PSScriptRoot
    Import-Module (Join-Path $script:LibRoot "Lib-Config.psm1") -Force
}

Describe "Resolve-WhatsAppTarget" {

    It "usa o valor da env var quando contactIdEnv esta definido e nao vazio" {
        $anterior = $env:ORB_TESTE_TARGET
        try {
            $env:ORB_TESTE_TARGET = "5511999999999-999999@g.us"
            $target = [pscustomobject]@{
                contactId    = "550000000000-0000000000@g.us"
                contactIdEnv = "ORB_TESTE_TARGET"
            }
            Resolve-WhatsAppTarget -Target $target | Should -Be "5511999999999-999999@g.us"
        } finally {
            $env:ORB_TESTE_TARGET = $anterior
        }
    }

    It "falha cedo (throw) quando contactIdEnv esta declarado mas a variavel nao existe" {
        $anterior = $env:ORB_TESTE_TARGET_AUSENTE
        try {
            Remove-Item Env:\ORB_TESTE_TARGET_AUSENTE -ErrorAction SilentlyContinue
            $target = [pscustomobject]@{
                contactId    = "550000000000-0000000000@g.us"
                contactIdEnv = "ORB_TESTE_TARGET_AUSENTE"
            }
            { Resolve-WhatsAppTarget -Target $target } | Should -Throw
        } finally {
            $env:ORB_TESTE_TARGET_AUSENTE = $anterior
        }
    }

    It "falha cedo (throw) quando contactIdEnv esta declarado mas a variavel esta em branco" {
        $anterior = $env:ORB_TESTE_TARGET_VAZIO
        try {
            $env:ORB_TESTE_TARGET_VAZIO = "   "
            $target = [pscustomobject]@{
                contactId    = "550000000000-0000000000@g.us"
                contactIdEnv = "ORB_TESTE_TARGET_VAZIO"
            }
            { Resolve-WhatsAppTarget -Target $target } | Should -Throw
        } finally {
            $env:ORB_TESTE_TARGET_VAZIO = $anterior
        }
    }

    It "mensagem de erro cita a env var ausente mas nao vaza o placeholder do JSON" {
        Remove-Item Env:\ORB_TESTE_TARGET_AUSENTE2 -ErrorAction SilentlyContinue
        $target = [pscustomobject]@{
            contactId    = "550000000000-0000000000@g.us"
            contactIdEnv = "ORB_TESTE_TARGET_AUSENTE2"
        }
        # -PassThru em vez de try/catch: a governanca PowerShell reprova bloco
        # 'catch' generico, e o matcher nativo do Pester ja devolve o ErrorRecord.
        $erro = { Resolve-WhatsAppTarget -Target $target } | Should -Throw -PassThru
        $mensagem = $erro.Exception.Message
        $mensagem | Should -Not -BeNullOrEmpty
        $mensagem | Should -BeLike "*ORB_TESTE_TARGET_AUSENTE2*"
        $mensagem | Should -Not -BeLike "*550000000000*"
    }

    It "usa contactId direto quando contactIdEnv nao esta declarado (config sem override por .env)" {
        $target = [pscustomobject]@{
            contactId = "5511999999999@c.us"
        }
        Resolve-WhatsAppTarget -Target $target | Should -Be "5511999999999@c.us"
    }

    It "usa contactPhone quando contactId esta ausente e contactIdEnv nao esta declarado" {
        $target = [pscustomobject]@{
            contactPhone = "5511999999999"
        }
        Resolve-WhatsAppTarget -Target $target | Should -Be "5511999999999"
    }

    It "falha cedo (throw) quando o target nao declara contactId, contactPhone nem contactIdEnv" {
        $target = [pscustomobject]@{}
        { Resolve-WhatsAppTarget -Target $target } | Should -Throw
    }
}
