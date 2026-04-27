---
name: automacao-monitor
description: "Use when changing the central PowerShell scheduler, its config.json contract, or the operational rules for unattended task dispatch in this repository."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise Automation Monitor Standard

## Purpose

Use this skill for the central monitor and scheduler layer implemented by `MonitorAutomacoes.ps1`. It defines how tasks are registered, validated, dispatched, correlated, and observed during unattended execution.

## When to Use

- Changing monitor behavior, task dispatch rules, or `config.json` contract.
- Reviewing overlap prevention, mutex, hot reload, heartbeat, or metrics behavior.
- Adding or troubleshooting a scheduled automation.

## Do Not Use When

- The task is only about a standalone PowerShell script outside the monitor contract.
- The work is limited to VBA architecture or workbook synchronization.
- The question is only about log-line format; use `log-standardization`.

## Related Skills

- `powershell-automation`: PowerShell implementation patterns and PS 5.1 compatibility.
- `automation-execution-contract`: `ExecId`, exit-code ownership, and downstream propagation.
- `automation-runtime-safety`: startup diagnostics, cleanup, and dry-run discipline.
- `automacao-standard`: manual-first rule before monitor registration.

## Non-Negotiable Rules

1. The monitor must run as a singleton protected by a global mutex.
2. `config.json` is a contract and must be validated before task dispatch begins.
3. New tasks must prove themselves manually before scheduler registration.
4. Task paths should be relative (e.g., `.\\Module\\run.ps1`) for repository portability, as the monitor resolves them dynamically relative to its own location.
5. Dry-run mode must not launch external processes or mutate persistent state.
6. Metrics must be persisted periodically to `Logs/Monitor_Metrics.json`.

## Architecture Overview

| Asset | Responsibility |
| --- | --- |
| `MonitorAutomacoes.ps1` | Scheduler core, dynamic path resolution, task lifecycle management |
| `config.json` | Declarative task registry and schedule contract |
| `Logs/yyyy-MM_Monitor.log` | Central operational log |
| `Logs/Monitor_Metrics.json` | Structured operational metrics snapshot |
| `Startup_Error.txt` | Early fatal startup diagnostics |

## Task Registration Standard

```json
{
  "name": "Friendly Task Name",
  "scriptPath": ".\\Module\\run.ps1",
  "enabled": true,
  "preventOverlap": true,
  "waitForExit": false,
  "schedule": {
    "daysOfWeek": [1, 2, 3, 4, 5],
    "hours": [8, 14],
    "minutes": [0]
  }
}
```

## Configuration Contract

| Field | Meaning |
| --- | --- |
| `enabled` | Disable safely without deleting the task |
| `preventOverlap` | Do not start a second instance while one is still active |
| `waitForExit` | Decide whether the monitor blocks on process completion |
| `schedule.daysOfWeek` | Day filter using monitor convention `0..6` only |
| `schedule.hours` | Hour filter; empty array means no hour-based trigger |
| `schedule.minutes` | Minute filter for execution windows |
| `exitCodeMap` | Optional readable mapping for known task exit codes |

## Supported CLI Flags

| Flag | Behavior |
| --- | --- |
| `-RunOnce` | Execute a single scheduling cycle and exit |
| `-DryRun` | Log eligible launches without actually starting them |
| `-SkipTaskExecution` | Run validation and loop logic but suppress launches |
| `-MutexNameOverride` | Override mutex name for isolated testing |

`-RunOnce -DryRun` is the preferred preflight path. When the main mutex is already in use, combine `-MutexNameOverride -RunOnce -SkipTaskExecution` for smoke testing.

## Enterprise Patterns

| Pattern | Standard |
| --- | --- |
| Mutex | Use a single named global mutex to prevent duplicate monitor instances |
| Hot reload | Detect config changes via hash and reload without restart |
| Structured logging | Emit `[PS]` prefixed records with monitor-specific context |
| Startup diagnostics | Write `Startup_Error.txt` for failures before normal logging |
| Validation first | Reject invalid task definitions before launch |
| Metrics snapshot | Persist cumulative and rolling-window counters |
| Correlation | Pass `ExecId` to child PowerShell scripts as the first positional argument |

## Repo-Specific Constraints

- `schedule.daysOfWeek` accepts only `0..6`. Using `7` invalidates the config and can trap the monitor in a reload-failure loop.
- Exit codes `23` and `40` are operational WARN outcomes in this repository; they must not be counted as hard errors.
- When validating the monitor while another instance is active, use `-MutexNameOverride` rather than disabling the real mutex.
- The monitor is responsible for passing `ExecId` into child `.ps1` tasks positionally so downstream logs stay correlated.

## Metrics Contract

`Logs/Monitor_Metrics.json` is the only structured JSON metrics artifact in the logging stack. Keep it as an operational snapshot, not a log stream.

## Validation

1. Validate `config.json` before launching any task.
2. Run `-RunOnce -DryRun` after schedule changes.
3. Confirm that overlap prevention, mutex, and exit-code mapping still behave as expected.
4. Verify that `ExecId` reaches child PowerShell scripts and appears in the owning logs.
5. Confirm metrics and heartbeat still update in unattended mode.

## Troubleshooting

| Symptom | Root Cause | Action |
| --- | --- | --- |
| Monitor does not start | Invalid JSON or startup failure before logger initialization | Inspect `Startup_Error.txt` first |
| Task never fires | Schedule mismatch, disabled task, or invalid `daysOfWeek` value | Validate task flags and the `0..6` day range |
| Overlap prevention suppresses execution | Prior process still active | Confirm `preventOverlap` intent and inspect the task runtime |
| DryRun launches real processes | Launch guard placed too late | Move the dry-run check ahead of `Start-Process` or equivalent |
| Non-zero task counts as hard error but should not | Exit code policy not aligned | Treat `23` and `40` as WARN at the monitor boundary |

## Pre-Delivery Checklist

- [ ] `config.json` changes are valid and use relative paths for portability.
- [ ] New tasks were proven manually before registration.
- [ ] Singleton behavior remains enforced.
- [ ] `-RunOnce`, `-DryRun`, and `-SkipTaskExecution` still honor their contracts.
- [ ] `ExecId` is propagated to child PowerShell tasks.
- [ ] Metrics and startup diagnostics are preserved.
