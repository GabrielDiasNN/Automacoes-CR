---
name: powershell-automation
description: "Use when creating, reviewing, or refactoring PowerShell automation scripts that require enterprise-grade scheduling, logging, encoding control, and process safety."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise PowerShell Automation Standard

## Purpose
Use this skill for PowerShell automation scripts, especially monitors, schedulers, service-like loops, orchestrators, and tooling scripts. The standard emphasizes explicit failure behavior, UTF-8-safe file handling, singleton control, structured logging, and configuration validation.

## Non-Negotiable Rules
1. Set `$ErrorActionPreference = "Stop"` at the top of every script. Downgrade selectively and with a comment.
2. Never rely on default encoding for file output. Wrap writes in explicit UTF-8 StreamWriter helpers.
3. Use a named mutex or equivalent guard when the script must run as a singleton.
4. Validate configuration before entering the main execution loop.
5. Log operational state transitions, not only exceptions.
6. Use `[CmdletBinding()]` and a `param()` block for all non-trivial scripts.
7. Use only PowerShell Approved Verbs for function names.

---

## Script Header Standard

Every script must start with a structured header followed by a `param()` block:

```powershell
# ==============================================================================
# ARQUIVO: NomeDoScript.ps1
# VERSÃO: 1.0
# DESCRIÇÃO: Resumo do que o script faz.
# ==============================================================================

[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ExecId        = "",
    [string]$BasePath      = "C:\Automacoes",
    [switch]$DryRun,
    [switch]$RunOnce
)

$ErrorActionPreference = "Stop"
```

---

## DryRun Mode Convention

Scripts that perform destructive or side-effecting operations must support a `-DryRun` flag.

| Rule | Details |
|---|---|
| Flag | `[switch]$DryRun` in param block |
| Behavior | Log the action with `[DRY-RUN]` prefix but skip the actual operation |
| Coverage | All file operations, email sends, scheduled launches, and config mutations |
| Exit code | Same as real run: 0 for success, standard codes for failures |

```powershell
if ($DryRun) {
    Write-Log "[DRY-RUN] Removeria arquivo: $file" -Type "INFO"
    return
}
Remove-Item -LiteralPath $file -Force
```

---

## RunOnce Mode Convention

Long-running loop scripts (monitors, schedulers) must support `-RunOnce`:

```powershell
if ($RunOnce) {
    Invoke-SingleCycle
    exit $script:ExitCode
}

while ($true) {
    Invoke-SingleCycle
    Start-Sleep -Seconds $LoopIntervalSeconds
}
```

---

## UTF-8 Encoding Standard

Never rely on host defaults. Use explicit StreamWriter helpers:

```powershell
$script:Utf8Encoding = New-Object System.Text.UTF8Encoding($false)

function Add-Utf8Line {
    param([string]$FilePath, [string]$Line)
    $sw = New-Object System.IO.StreamWriter($FilePath, $true, $script:Utf8Encoding)
    try   { $sw.WriteLine($Line); $sw.Flush() }
    finally { $sw.Close(); $sw.Dispose() }
}

function Set-Utf8Content {
    param([string]$FilePath, [string]$Content)
    [System.IO.File]::WriteAllText($FilePath, $Content, $script:Utf8Encoding)
}
```

Apply this at startup too:

```powershell
[Console]::InputEncoding  = $script:Utf8Encoding
[Console]::OutputEncoding = $script:Utf8Encoding
$OutputEncoding           = $script:Utf8Encoding
```

---

## Write-Log Function Standard

Every script must have a single `Write-Log` function:

```powershell
function Write-Log {
    param(
        [string]$msg,
        [string]$type  = "INFO",
        [string]$LogDir = $script:LogDir
    )

    Initialize-Directory $LogDir
    $fileName  = "$(Get-Date -Format 'yyyy-MM')_NomeScript.log"
    $logPath   = Join-Path $LogDir $fileName
    $timestamp = Get-Date -Format 'dd/MM/yyyy HH:mm:ss'
    $line      = "[$timestamp] [PS] [$type] $msg"

    try { Add-Utf8Line -FilePath $logPath -Line $line } catch {}

    $color = switch ($type) {
        "ERRO"  { "Red" }
        "WARN"  { "Yellow" }
        default { "Cyan" }
    }
    Write-Host $line -ForegroundColor $color
}
```

Log types follow the project convention: `INFO`, `WARN`, `ERRO`.

---

## Singleton Guard (Mutex)

When duplicate instances are unsafe, protect with a named mutex:

```powershell
$MutexName = "Global\NomeDoScriptMutex"
$script:Mutex = New-Object System.Threading.Mutex($false, $MutexName)

try {
    $acquired = $script:Mutex.WaitOne([TimeSpan]::FromSeconds(5), $false)
} catch [System.Threading.AbandonedMutexException] {
    $acquired = $true
}

if (-not $acquired) {
    Write-Log "Outra instancia ja esta em execucao. Encerrando." -Type "WARN"
    exit 0
}
```

Always release the mutex in a `finally` block or `Register-EngineEvent` cleanup handler.

---

## Configuration Validation

Use a dedicated `Test-Configuration` function and refuse invalid input before execution starts:

```powershell
function Test-Configuration {
    param($Config)

    if (-not $Config) { return "Config nula." }
    if (-not $Config.tasks) { return "Campo 'tasks' ausente." }

    foreach ($task in $Config.tasks) {
        $err = Test-TaskStructure $task
        if ($err) { return $err }
    }

    return $null
}
```

Call this before starting the main loop. Log validation failures as `ERRO` and exit.

---

## Hot Reload Pattern

For long-running monitors, detect and reload config between cycles:

```powershell
function Get-ConfigHash {
    param([string]$FilePath)
    if (-not (Test-Path $FilePath)) { return $null }
    return (Get-FileHash -Path $FilePath -Algorithm MD5).Hash
}

# In the main loop:
$currentHash = Get-ConfigHash $ConfigFilePath
if ($currentHash -ne $script:ConfigHash) {
    $newConfig = Get-Content $ConfigFilePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $err = Test-Configuration $newConfig
    if ($err) {
        Write-Log "Config invalida apos reload: $err" -Type "ERRO"
    } else {
        $script:Config = $newConfig
        $script:ConfigHash = $currentHash
        Write-Log "Config recarregada com sucesso." -Type "INFO"
    }
}
```

---

## Metrics Collection

Track key operational counters using a `$script:Metrics` hashtable:

```powershell
$script:Metrics = @{
    TasksTriggered        = 0
    TasksCompleted        = 0
    TasksFinishedNonZero  = 0
    ConfigReloadSuccess   = 0
    ConfigReloadFailure   = 0
}

function Add-MetricCounter {
    param([string]$MetricName, [int]$Delta = 1)
    if ($script:Metrics.ContainsKey($MetricName)) {
        $script:Metrics[$MetricName] += $Delta
    }
}
```

Persist metrics as a JSON snapshot to `Logs/Monitor_Metrics.json` periodically.

---

## Approved Verb Compliance

PowerShell function names must use only Approved Verbs. Common mappings:

| Avoid | Use instead |
|---|---|
| `Log-Something` | `Write-Log` |
| `Validate-Config` | `Test-Configuration` |
| `CheckTask` | `Test-TaskStructure` |
| `LoadConfig` | `Import-Configuration` |
| `SaveMetrics` | `Save-MetricsSnapshot` |
| `MakeDir` | `Initialize-Directory` |
| `GetHash` | `Get-ConfigHash` |

Run `Tools/Test-PowerShellApprovedVerbs.ps1` to validate compliance.

---

## Startup Diagnostics

Write a dedicated emergency file for failures that happen before logging is ready:

```powershell
$EmergencyLog = Join-Path $ScriptPath "Startup_Error.txt"

function Write-StartupDiagnostic {
    param([string]$Message, [string]$Type = "ERRO")
    try {
        $line = "[$(Get-Date -Format 'dd/MM/yyyy HH:mm:ss')] [$Type] $Message"
        $sw = New-Object System.IO.StreamWriter($EmergencyLog, $true, $Utf8Encoding)
        try { $sw.WriteLine($line); $sw.Flush() }
        finally { $sw.Close(); $sw.Dispose() }
    } catch {}
}
```

Call this before `Write-Log` is available (mutex setup, encoding setup, config load).

---

## Runtime Contract

| Concern | Standard |
|---|---|
| Error behavior | `$ErrorActionPreference = "Stop"` by default; downgrade selectively |
| Encoding | Explicit UTF-8 for read and write paths; set console encoding at startup |
| Process singleton | Named mutex when duplicate instances are unsafe |
| State | `$script:` scope for variables shared across functions |
| Logs | Timestamped `[PS]` prefixed records with `INFO`, `WARN`, or `ERRO` |
| DryRun | `[DRY-RUN]` prefix on log lines; no actual side effects |
| RunOnce | Single cycle execution for testing or on-demand triggering |

---

## Heartbeat

Emit periodic health messages from long-running monitors:

```powershell
$HeartbeatIntervalMinutes = 30
$script:LastHeartbeat = Get-Date

# Inside the main loop:
if ((Get-Date) - $script:LastHeartbeat -gt [TimeSpan]::FromMinutes($HeartbeatIntervalMinutes)) {
    Write-Log "Heartbeat | tarefas_ativas=$($script:RunningTasks.Count)" -Type "INFO"
    $script:LastHeartbeat = Get-Date
}
```

---

## Troubleshooting

| Symptom | Root Cause | Action |
|---|---|---|
| Script behaves differently by host | Host-specific defaults | Make encoding and preference variables explicit |
| Duplicate monitor instances | Missing mutex guard | Add named mutex protection |
| Config change not picked up | Reload logic too weak or hash not updated | Rework change detection and validation boundary |
| Non-approved verb warning | Function name uses a custom verb | Rename using Get-Verb approved list |
| File write appears empty or corrupted | Default encoding interference | Use explicit UTF-8 StreamWriter |
| Startup failure with no log | Logging not yet initialized | Add Write-StartupDiagnostic before main logging starts |

---

## Pre-Delivery Checklist

- [ ] `$ErrorActionPreference = "Stop"` is set at the top.
- [ ] File encoding is explicit for all writes (StreamWriter with UTF-8).
- [ ] Console encoding is set at startup.
- [ ] Singleton mutex is implemented when required.
- [ ] Configuration is validated before execution (`Test-*` pattern).
- [ ] Logs carry `[PS]` layer prefix and follow the universal format.
- [ ] DryRun mode is supported for side-effecting operations.
- [ ] RunOnce mode is supported for long-running scripts.
- [ ] Function names use only PowerShell Approved Verbs.
- [ ] Startup diagnostics write to `Startup_Error.txt` before main logging.