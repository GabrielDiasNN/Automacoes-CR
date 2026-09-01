$here = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($here)) {
    $here = Split-Path -Parent $PSCommandPath
}

BeforeAll {
    $script:ScriptPath = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "Tools\Get-GovernanceTargetSummary.ps1"
    if (-not (Test-Path -LiteralPath $script:ScriptPath)) {
        throw "Script alvo nao encontrado: $script:ScriptPath"
    }

    function Invoke-Summary {
        param(
            [string[]]$Paths,
            [switch]$NoCriticalPromotion
        )

        return & $script:ScriptPath -BasePath "." -Paths $Paths -NoCriticalPromotion:$NoCriticalPromotion
    }
}

Describe "Get-GovernanceTargetSummary - flags por area" {
    Context "Diff direcionado (targeted_paths)" {
        It "Detecta apenas Python quando o diff contem somente .py" {
            $summary = Invoke-Summary -Paths @("Orchestrator/app/main.py")

            $summary.SelectionMode | Should -Be "targeted_paths"
            $summary.HasPython | Should -BeTrue
            $summary.HasPowerShell | Should -BeFalse
            $summary.HasJs | Should -BeFalse
            $summary.HasMarkdown | Should -BeFalse
        }

        It "Detecta Python quando requirements muda na raiz" {
            $summary = Invoke-Summary -Paths @("requirements-dev.in")

            $summary.HasPython | Should -BeTrue
            $summary.HasPowerShell | Should -BeFalse
        }

        It "Detecta apenas PowerShell quando o diff contem somente .ps1 fora de area critica" {
            $summary = Invoke-Summary -Paths @("Receitas Emitidas/run.ps1")

            $summary.SelectionMode | Should -Be "targeted_paths"
            $summary.HasPowerShell | Should -BeTrue
            $summary.HasPython | Should -BeFalse
            $summary.HasJs | Should -BeFalse
        }

        It "Detecta JavaScript e frontend para .ts/.tsx, .html e .css" {
            $summary = Invoke-Summary -Paths @("Dashboard/src/main.tsx")
            $summary.HasJs | Should -BeTrue

            $summary = Invoke-Summary -Paths @("Dashboard/src/api/client.ts")
            $summary.HasJs | Should -BeTrue

            $summary = Invoke-Summary -Paths @("Dashboard/index.html")
            $summary.HasJs | Should -BeTrue
        }

        It "Detecta apenas Markdown para documentacao nao critica" {
            $summary = Invoke-Summary -Paths @("docs/runbooks/exemplo.md")

            $summary.HasMarkdown | Should -BeTrue
            $summary.HasPython | Should -BeFalse
            $summary.HasPowerShell | Should -BeFalse
            $summary.HasJs | Should -BeFalse
        }
    }

    Context "Full scan e diff vazio" {
        It "Forca todas as areas quando um caminho critico e alterado" {
            $summary = Invoke-Summary -Paths @("Tools/ValidarAutomacoes.ps1")

            $summary.SelectionMode | Should -Be "full_scan"
            $summary.HasPython | Should -BeTrue
            $summary.HasPowerShell | Should -BeTrue
            $summary.HasJs | Should -BeTrue
            $summary.HasMarkdown | Should -BeTrue
        }

        It "Suprime a promocao a full_scan com -NoCriticalPromotion" {
            # Regressao do hook Stop: entre 27/08/2026 e 01/09/2026 um unico
            # alvo critico no diff zerava GovernancePaths e o gate varria o
            # repositorio inteiro (340 s) apesar de ter recebido -Paths,
            # estourando o timeout de 240 s em 13 de 13 execucoes.
            $alvos = @("lib/CLAUDE.md", "CLAUDE.md")
            $summary = Invoke-Summary -Paths $alvos -NoCriticalPromotion

            $summary.SelectionMode | Should -Be "targeted_paths"
            $summary.HasCriticalPaths | Should -BeFalse
            $summary.GovernancePaths.Count | Should -Be 2

            # A deteccao continua registrada: so a promocao foi suprimida.
            $summary.CriticalPathCount | Should -Be 1
            $summary.CriticalPaths | Should -Contain "lib\CLAUDE.md"
        }

        It "Mantem a promocao a full_scan sem a flag (pre-commit e CI)" {
            $summary = Invoke-Summary -Paths @("lib/CLAUDE.md", "CLAUDE.md")

            $summary.SelectionMode | Should -Be "full_scan"
            $summary.HasCriticalPaths | Should -BeTrue
            $summary.GovernancePaths.Count | Should -Be 0
        }

        It "Forca todas as areas quando o diff esta vazio (no_paths)" {
            $summary = Invoke-Summary -Paths @()

            $summary.SelectionMode | Should -Be "no_paths"
            $summary.HasPython | Should -BeTrue
            $summary.HasPowerShell | Should -BeTrue
            $summary.HasJs | Should -BeTrue
            $summary.HasMarkdown | Should -BeTrue
        }
    }

    Context "Contrato existente preservado" {
        It "Mantem HasLogTargets para script operacional e exclui Tools" {
            $summary = Invoke-Summary -Paths @("Receitas Emitidas/run.ps1")
            $summary.HasLogTargets | Should -BeTrue

            $summary = Invoke-Summary -Paths @("Tools/Watch-CI.ps1")
            $summary.HasLogTargets | Should -BeFalse
        }
    }
}
