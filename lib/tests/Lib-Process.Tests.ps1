#
# Testes Pester de lib/Lib-Process.psm1 — foco em Resolve-HubPythonExe.
#
# Motivacao: a funcao resolve o python.exe do venv da raiz para automacoes
# rodadas de um worktree (o .venv nao e versionado). O ramo de falha da
# descoberta do repositorio principal (git ausente, Resolve-Path quebrado)
# caia num `catch` vazio: o pre-flight so' dizia "Path inacessivel:
# python.exe", sem pista de que a cadeia git rev-parse foi tentada e falhou.
# Estes testes travam (1) o valor de retorno em cada ramo e (2) que a falha
# de descoberta deixa rastro em warning.
#

BeforeAll {
    $script:RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    Import-Module (Join-Path $script:RepoRoot 'lib\Lib-Process.psm1') -Force
}

Describe 'Resolve-HubPythonExe' {

    It 'devolve o venv local quando ele existe' {
        $proj = Join-Path $TestDrive 'com-venv'
        New-Item -ItemType Directory -Force -Path (Join-Path $proj '.venv\Scripts') | Out-Null
        Set-Content -LiteralPath (Join-Path $proj '.venv\Scripts\python.exe') -Value 'x'

        Resolve-HubPythonExe -ProjectRoot $proj |
            Should -Be (Join-Path $proj '.venv\Scripts\python.exe')
    }

    It 'devolve o caminho do venv local (inexistente) como fallback, nunca string vazia' {
        $proj = Join-Path $TestDrive 'sem-nada'
        New-Item -ItemType Directory -Force -Path $proj | Out-Null

        $resultado = Resolve-HubPythonExe -ProjectRoot $proj -WarningAction SilentlyContinue
        $resultado | Should -Be (Join-Path $proj '.venv\Scripts\python.exe')
        [string]::IsNullOrEmpty($resultado) | Should -BeFalse
    }

    It 'emite warning quando a descoberta do repositorio principal falha (git ausente)' {
        $proj = Join-Path $TestDrive 'sem-git'
        New-Item -ItemType Directory -Force -Path $proj | Out-Null

        $pathAnterior = $env:PATH
        try {
            # Sem PATH, o executavel `git` nao resolve: CommandNotFoundException
            # cai no catch. Antes o catch era vazio e a falha sumia.
            $env:PATH = ''
            $warnings = @()
            $resultado = Resolve-HubPythonExe -ProjectRoot $proj -WarningVariable +warnings -WarningAction SilentlyContinue
        }
        finally {
            $env:PATH = $pathAnterior
        }

        $resultado | Should -Be (Join-Path $proj '.venv\Scripts\python.exe')
        ($warnings -join "`n") | Should -Match 'venv do repositorio principal'
    }
}

Describe 'Invoke-HubPythonRunner' {

    It 'repassa argumentos com espacos e devolve exatamente o exit code do runner' {
        $pythonExe = Resolve-HubPythonExe -ProjectRoot $script:RepoRoot
        if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
            Set-ItResult -Skipped -Because 'venv do projeto ausente neste ambiente'
            return
        }

        $pastaComEspaco = Join-Path $TestDrive 'Pasta Com Espaco'
        New-Item -ItemType Directory -Force -Path $pastaComEspaco | Out-Null
        $scriptTeste = Join-Path $pastaComEspaco 'echo_exit.py'
        Set-Content -LiteralPath $scriptTeste -Encoding UTF8 -Value @'
import sys
print("ARG1=" + sys.argv[1])
print("ARG2=" + sys.argv[2])
sys.exit(int(sys.argv[3]))
'@

        $codigo = Invoke-HubPythonRunner `
            -PythonExe $pythonExe `
            -Arguments @($scriptTeste, 'valor com espaco', 'acao-utf8', '26') `
            -WorkingDirectory $pastaComEspaco

        $codigo | Should -Be 26
    }
}
