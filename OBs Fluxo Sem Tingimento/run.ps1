<#
.SYNOPSIS
    Shim de entrada da automacao OBs Fluxo Sem Tingimento (OFST-06): delega ao runner Python.
.DESCRIPTION
    A orquestracao (pre-flight, lock OFST-06, extract, transform, dispatch por WhatsApp e
    commit do estado) esta em run_ofst.py, que usa lib/python/hub_runner.py e
    lib/python/hub_whatsapp.py.
    Este script so faz tres coisas: resolve o interpretador do projeto
    (Resolve-HubPythonExe, valido em worktree), chama o runner repassando o ExecId e
    sai com o MESMO exit code, porque o worker do Orchestrator le o exit code de
    powershell.exe -File run.ps1 <ExecId>.
    Sem Python do projeto, sai com 9 (codigo de pre-flight), com mensagem clara.
.PARAMETER ExecId
    Identificador da execucao, repassado pelo Orchestrator. Vazio: o runner registra a
    telemetria e obtem o ExecId.
.PARAMETER DryRun
    Validacao manual: pre-flight, extract e transform rodam de verdade, mas nenhum
    WhatsApp e enviado e o state nao e confirmado. Nao use em producao.
.EXAMPLE
    powershell.exe -NoProfile -File "OBs Fluxo Sem Tingimento\run.ps1" -DryRun
.NOTES
    Version: 3.0.0
    Runtime: Windows PowerShell 5.1 (powershell.exe).
    Contract: enterprise-orchestration-contract, structured-logging, retry-on-failure, granular-idempotency
#>

[CmdletBinding()]
param(
    [string]$ExecId = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# Configuracao Global de Encoding
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }

$projectRoot = Split-Path -Parent $ScriptDir
$libProcess  = Join-Path $projectRoot "lib\Lib-Process.psm1"
$runnerPy    = Join-Path $ScriptDir "run_ofst.py"

Import-Module $libProcess -Force

# O .venv nao e versionado e vive na raiz do repositorio principal: Resolve-HubPythonExe
# devolve o venv do repositorio principal quando a arvore corrente nao tem um.
$pythonExe = Resolve-HubPythonExe -ProjectRoot $projectRoot

if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
    Write-Host "[ERRO] Python do projeto nao encontrado em '$pythonExe'. Crie o .venv na raiz do repositorio principal."
    exit 9
}
if (-not (Test-Path -LiteralPath $runnerPy -PathType Leaf)) {
    Write-Host "[ERRO] Runner ausente: $runnerPy"
    exit 9
}

# O runner grava eventos em UTF-8; os filhos Python herdam estas variaveis.
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$runnerArgs = @($runnerPy)
if (-not [string]::IsNullOrWhiteSpace($ExecId)) { $runnerArgs += $ExecId }
if ($DryRun) { $runnerArgs += "--dry-run" }

& $pythonExe @runnerArgs
exit $LASTEXITCODE
