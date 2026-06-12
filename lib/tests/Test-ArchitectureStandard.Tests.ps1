$here = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($here)) {
    $here = Split-Path -Parent $PSCommandPath
}

BeforeAll {
    function New-ArchitectureFixture {
        param([string]$BasePath)

        New-Item -ItemType Directory -Force -Path (Join-Path $BasePath "docs") | Out-Null
        New-Item -ItemType Directory -Force -Path (Join-Path $BasePath "Tools") | Out-Null
        New-Item -ItemType Directory -Force -Path (Join-Path $BasePath "Orchestrator\app\routers") | Out-Null
        New-Item -ItemType Directory -Force -Path (Join-Path $BasePath "Orchestrator\app\services") | Out-Null

        @"
# Padrao Arquitetural

## Camadas

Contrato minimo.

## Severidade

Contrato minimo.

## Validacao

Contrato minimo.
"@ | Set-Content -LiteralPath (Join-Path $BasePath "docs\architecture-standard.md") -Encoding UTF8

        "Referencia docs/architecture-standard.md" | Set-Content -LiteralPath (Join-Path $BasePath "README.md") -Encoding UTF8
        "Referencia docs/architecture-standard.md" | Set-Content -LiteralPath (Join-Path $BasePath "CONTEXT.md") -Encoding UTF8
        "Referencia docs/architecture-standard.md" | Set-Content -LiteralPath (Join-Path $BasePath "docs\repository-governance.md") -Encoding UTF8

        @"
{
  "version": "1.0.0",
  "python_subprocess_allowlist": [
    "^Orchestrator\\\\worker\\.py$"
  ],
  "python_sqlite_allowlist": [
    "^Orchestrator\\\\app\\\\database\\.py$"
  ],
  "automation_exclusions": [
    "^_Template\\\\run\\.ps1$",
    "^Orchestrator\\\\tests\\\\"
  ],
  "documentation_required_sections": [
    { "label": "Camadas", "pattern": "Camadas" },
    { "label": "Severidade", "pattern": "Severidade" },
    { "label": "Validacao", "pattern": "Valida(cao|ção)" }
  ]
}
"@ | Set-Content -LiteralPath (Join-Path $BasePath "Tools\architecture-standard.rules.json") -Encoding UTF8
    }

    function Invoke-ArchitectureStandard {
        param(
            [string]$BasePath,
            [string[]]$ExtraArgs = @()
        )

        $repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
        $sut = Join-Path $repoRoot "Tools\Test-ArchitectureStandard.ps1"
        $outputPath = Join-Path $BasePath "architecture-output.txt"
        $arguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $sut, "-RootPath", $BasePath) + $ExtraArgs
        $process = Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -Wait -PassThru -NoNewWindow -RedirectStandardOutput $outputPath
        $output = Get-Content -LiteralPath $outputPath -Raw

        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            Output   = $output
        }
    }
}

Describe "Test-ArchitectureStandard" {
    It "aprova fixture minima sem violacao critica" {
        $fixture = Join-Path $TestDrive "healthy"
        New-ArchitectureFixture -BasePath $fixture

        $result = Invoke-ArchitectureStandard -BasePath $fixture -ExtraArgs @("-AsJson")
        $report = $result.Output | ConvertFrom-Json

        $result.ExitCode | Should -Be 0
        $report.status | Should -Be "healthy"
        $report.summary.critical | Should -Be 0
    }

    It "falha quando router FastAPI importa Oracle diretamente" {
        $fixture = Join-Path $TestDrive "oracle-router"
        New-ArchitectureFixture -BasePath $fixture
        "import oracledb`n" | Set-Content -LiteralPath (Join-Path $fixture "Orchestrator\app\routers\bad.py") -Encoding UTF8

        $result = Invoke-ArchitectureStandard -BasePath $fixture -ExtraArgs @("-AsJson")
        $report = $result.Output | ConvertFrom-Json

        $result.ExitCode | Should -Be 1
        $report.status | Should -Be "incident"
        @($report.findings | Where-Object { $_.rule -eq "ORACLE_IN_API_ROUTER" }).Count | Should -Be 1
    }

    It "emite aviso para subprocess fora da allowlist sem falhar o gate" {
        $fixture = Join-Path $TestDrive "subprocess-warning"
        New-ArchitectureFixture -BasePath $fixture
        New-Item -ItemType Directory -Force -Path (Join-Path $fixture "Orchestrator\app\helpers") | Out-Null
        "import subprocess`n" | Set-Content -LiteralPath (Join-Path $fixture "Orchestrator\app\helpers\shell.py") -Encoding UTF8

        $result = Invoke-ArchitectureStandard -BasePath $fixture -ExtraArgs @("-AsJson")
        $report = $result.Output | ConvertFrom-Json

        $result.ExitCode | Should -Be 0
        $report.status | Should -Be "attention"
        @($report.findings | Where-Object { $_.rule -eq "SUBPROCESS_OUTSIDE_RUNTIME_ALLOWLIST" }).Count | Should -Be 1
    }

    It "retorna JSON com contrato minimo da ferramenta" {
        $fixture = Join-Path $TestDrive "json-contract"
        New-ArchitectureFixture -BasePath $fixture

        $result = Invoke-ArchitectureStandard -BasePath $fixture -ExtraArgs @("-AsJson")
        $report = $result.Output | ConvertFrom-Json

        $report.tool | Should -Be "Test-ArchitectureStandard"
        $report.version | Should -Be "1.0.0"
        ($report.PSObject.Properties.Name -contains "findings") | Should -Be $true
    }

    It "respeita Paths e nao valida automacao fora do alvo" {
        $fixture = Join-Path $TestDrive "targeted-unrelated"
        New-ArchitectureFixture -BasePath $fixture
        New-Item -ItemType Directory -Force -Path (Join-Path $fixture "BadAuto") | Out-Null
        "Write-Host ok" | Set-Content -LiteralPath (Join-Path $fixture "BadAuto\run.ps1") -Encoding UTF8

        $result = Invoke-ArchitectureStandard -BasePath $fixture -ExtraArgs @("-Paths", "README.md", "-AsJson")
        $report = $result.Output | ConvertFrom-Json

        $result.ExitCode | Should -Be 0
        $report.status | Should -Be "healthy"
    }

    It "bloqueia Paths fora da raiz sem ler o arquivo externo" {
        $fixture = Join-Path $TestDrive "outside-root"
        New-ArchitectureFixture -BasePath $fixture
        $outsidePath = Join-Path $TestDrive "outside.py"
        "import sqlite3" | Set-Content -LiteralPath $outsidePath -Encoding UTF8

        $result = Invoke-ArchitectureStandard -BasePath $fixture -ExtraArgs @("-Paths", "..\outside.py", "-AsJson")
        $report = $result.Output | ConvertFrom-Json

        $result.ExitCode | Should -Be 1
        @($report.findings | Where-Object { $_.rule -eq "PATH_OUTSIDE_ROOT" }).Count | Should -Be 1
        @($report.findings | Where-Object { $_.rule -eq "SQLITE_DIRECT_ACCESS_OUTSIDE_DB_LAYER" }).Count | Should -Be 0
    }

    It "ignora mencao textual a Oracle em comentario de endpoint GET" {
        $fixture = Join-Path $TestDrive "oracle-comment"
        New-ArchitectureFixture -BasePath $fixture
        @"
from fastapi import APIRouter
router = APIRouter()

@router.get("/ok")
def ok():
    # Oracle citado apenas em comentario operacional.
    return {"ok": True}
"@ | Set-Content -LiteralPath (Join-Path $fixture "Orchestrator\app\routers\ok.py") -Encoding UTF8

        $result = Invoke-ArchitectureStandard -BasePath $fixture -ExtraArgs @("-Paths", "Orchestrator\app\routers\ok.py", "-AsJson")
        $report = $result.Output | ConvertFrom-Json

        $result.ExitCode | Should -Be 0
        @($report.findings | Where-Object { $_.rule -eq "ORACLE_IN_GET_ENDPOINT" }).Count | Should -Be 0
    }

    It "falha quando o ruleset arquitetural esta ausente" {
        $fixture = Join-Path $TestDrive "missing-rules"
        New-ArchitectureFixture -BasePath $fixture
        Remove-Item -LiteralPath (Join-Path $fixture "Tools\architecture-standard.rules.json") -Force

        $result = Invoke-ArchitectureStandard -BasePath $fixture -ExtraArgs @("-AsJson")
        $report = $result.Output | ConvertFrom-Json

        $result.ExitCode | Should -Be 1
        @($report.findings | Where-Object { $_.rule -eq "RULESET_MISSING" }).Count | Should -Be 1
    }
}
