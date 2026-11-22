[CmdletBinding()]
param(
    [string]$ExecId = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }

$projectRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$libProcess  = Join-Path $projectRoot "lib\Lib-Process.psm1"
$configPath  = Join-Path $ScriptDir "promocao.json"

Import-Module $libProcess -Force

$pythonExe = Resolve-HubPythonExe -ProjectRoot $projectRoot
if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
    Write-Host "[ERRO] Python do projeto nao encontrado em '$pythonExe'."
    exit 9
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = Join-Path $projectRoot "lib\python"

$runnerArgs = @("-m", "promovidas.run_promocao", "--config", $configPath)
if (-not [string]::IsNullOrWhiteSpace($ExecId)) { $runnerArgs += $ExecId }
if ($DryRun) { $runnerArgs += "--dry-run" }

$exitCode = Invoke-HubPythonRunner -PythonExe $pythonExe -Arguments $runnerArgs -WorkingDirectory $ScriptDir
exit $exitCode
