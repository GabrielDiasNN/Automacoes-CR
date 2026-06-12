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
        param([string[]]$Paths)

        return & $script:ScriptPath -BasePath "." -Paths $Paths
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

        It "Detecta JavaScript e frontend para .js, .html e .css" {
            $summary = Invoke-Summary -Paths @("Dashboard/js/app.js")
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
