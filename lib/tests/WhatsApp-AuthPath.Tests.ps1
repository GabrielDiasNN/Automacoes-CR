#
# Testes do caminho da sessao autenticada do WhatsApp (achado ALTO da auditoria
# de seguranca de 27/07/2026).
#
# O diretorio LocalAuth contem as credenciais de sessao do WhatsApp Web da conta
# que envia RB-01, OBP-04 e OFST-06: quem copia o diretorio assume a conta sem
# QR code. Ele vivia em lib/.wwebjs_auth/ — protegido pelo .gitignore, mas nao
# contra zip, backup de pasta ou sync do projeto. A trava abaixo existe porque
# o caminho estava reconstruido manualmente em cinco pontos: basta um deles
# voltar para dentro da arvore para reabrir a exposicao sem ninguem perceber.
#

$FontesQueResolvemOCaminho = @(
    "lib\Send-WhatsApp.ps1",
    "lib\WhatsApp-Core.js",
    "lib\open-whatsapp-session.js",
    "OBs Paradas Fase\run.ps1",
    "OBs Fluxo Sem Tingimento\run.ps1"
)

BeforeAll {
    $script:LibRoot = Split-Path -Parent $PSScriptRoot
    $script:RepoRoot = Split-Path -Parent $script:LibRoot
    Import-Module (Join-Path $script:LibRoot "Lib-Process.psm1") -Force
}

Describe "Get-WhatsAppAuthPath" {

    It "resolve para fora da arvore do repositorio" {
        $caminho = Get-WhatsAppAuthPath
        $caminho | Should -Not -BeNullOrEmpty
        $caminho.ToLower().StartsWith($script:RepoRoot.ToLower()) | Should -BeFalse `
            -Because "a sessao dentro do repositorio vaza em qualquer zip/backup/sync do projeto"
    }

    It "usa %LOCALAPPDATA% quando WHATSAPP_AUTH_PATH nao esta definido" {
        $anterior = $env:WHATSAPP_AUTH_PATH
        try {
            $env:WHATSAPP_AUTH_PATH = $null
            Get-WhatsAppAuthPath | Should -Be (Join-Path $env:LOCALAPPDATA "Automacoes\wwebjs_auth")
        } finally {
            $env:WHATSAPP_AUTH_PATH = $anterior
        }
    }

    It "respeita o override WHATSAPP_AUTH_PATH" {
        $anterior = $env:WHATSAPP_AUTH_PATH
        $alternativo = Join-Path $env:TEMP "sessao-whatsapp-teste"
        try {
            $env:WHATSAPP_AUTH_PATH = $alternativo
            Get-WhatsAppAuthPath | Should -Be $alternativo
        } finally {
            $env:WHATSAPP_AUTH_PATH = $anterior
        }
    }

    It "normaliza override relativo para caminho absoluto" {
        $anterior = $env:WHATSAPP_AUTH_PATH
        try {
            $env:WHATSAPP_AUTH_PATH = ".\sessao-relativa"
            $caminho = Get-WhatsAppAuthPath
            [System.IO.Path]::IsPathRooted($caminho) | Should -BeTrue
            $caminho | Should -BeLike "*sessao-relativa"
        } finally {
            $env:WHATSAPP_AUTH_PATH = $anterior
        }
    }

    It "ignora espacos nas bordas do override" {
        $anterior = $env:WHATSAPP_AUTH_PATH
        $alternativo = Join-Path $env:TEMP "sessao-com-espaco"
        try {
            $env:WHATSAPP_AUTH_PATH = "  $alternativo  "
            Get-WhatsAppAuthPath | Should -Be $alternativo
        } finally {
            $env:WHATSAPP_AUTH_PATH = $anterior
        }
    }
}

Describe "Paridade entre os resolvedores PowerShell e Node" {
    # A paridade so importa nos casos DEGRADADOS: no default os dois sempre
    # concordaram. Override relativo e override com espaco eram justamente onde
    # divergiam — e divergir significa pedir QR code em producao.
    BeforeAll {
        $script:NodeDisponivel = [bool](Get-Command node -ErrorAction SilentlyContinue)
        $script:ResolverJs = (Join-Path (Split-Path -Parent $PSScriptRoot) "whatsapp-auth-path.js") -replace '\\', '/'
        # Base absoluta derivada do ambiente, nunca literal — o gate de
        # portabilidade reprova qualquer "C:\..." engessado no repositorio.
        $script:BaseAbsoluta = Join-Path $env:TEMP "sessao-paridade"
    }

    It "resolve o mesmo caminho nos dois runtimes: <Nome>" -ForEach @(
        @{ Nome = "sem override";                Forma = "nenhum" }
        @{ Nome = "override absoluto";           Forma = "absoluto" }
        @{ Nome = "override relativo";           Forma = "relativo" }
        @{ Nome = "override com espacos";        Forma = "com-espacos" }
        @{ Nome = "override com nome curto 8.3"; Forma = "curto-8.3" }
        @{ Nome = "override com ..";             Forma = "com-ponto-ponto" }
    ) {
        if (-not $script:NodeDisponivel) { Set-ItResult -Skipped -Because "node nao esta disponivel neste host" ; return }

        $override = switch ($Forma) {
            "nenhum"          { $null }
            "absoluto"        { $script:BaseAbsoluta }
            "relativo"        { ".\sessao-paridade" }
            "com-espacos"     { "  $($script:BaseAbsoluta)  " }
            "curto-8.3"       { $env:TEMP }
            "com-ponto-ponto" { Join-Path (Join-Path $env:TEMP "a\..") "sessao-paridade" }
        }

        $anterior = $env:WHATSAPP_AUTH_PATH
        try {
            $env:WHATSAPP_AUTH_PATH = $override
            $doNode = & node -e "process.stdout.write(require('$($script:ResolverJs)').resolveAuthPath())"
            $doNode | Should -Be (Get-WhatsAppAuthPath) `
                -Because "PowerShell e Node precisam abrir exatamente o mesmo perfil de sessao"
        } finally {
            $env:WHATSAPP_AUTH_PATH = $anterior
        }
    }
}

Describe "Trava anti-regressao do caminho da sessao" {

    It "<_> nao reconstroi o caminho da sessao manualmente" -ForEach $FontesQueResolvemOCaminho {
        $repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
        $conteudo = Get-Content -LiteralPath (Join-Path $repoRoot $_) -Raw
        $conteudo | Should -Not -Match '\.wwebjs_auth' `
            -Because "o caminho deve vir de Get-WhatsAppAuthPath (PowerShell) ou resolveAuthPath() (Node)"
    }

    It "o diretorio de sessao nao existe dentro do repositorio" {
        $repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
        Test-Path (Join-Path $repoRoot "lib\.wwebjs_auth") | Should -BeFalse
    }
}
