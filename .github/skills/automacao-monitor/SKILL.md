---
name: automacao-monitor
description: "Use when changing the central PowerShell scheduler, its config.json contract, or the operational rules for unattended automation execution."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise Automation Monitor Standard

## Purpose

Use this skill for the central scheduler and monitor layer that loads tasks from config.json, enforces singleton execution, and launches automations safely in unattended mode. The standard prioritizes configuration validation, operational observability, and predictable process control.

## Architecture Overview

| Asset                     | Responsibility                                          |
| ------------------------- | ------------------------------------------------------- |
| MonitorAutomacoes.ps1     | Scheduler core, reload logic, task lifecycle management |
| config.json               | Declarative task registry and schedule contract         |
| Logs/YYYY-MM_Monitor.log  | Central operational log                                 |
| Logs/Monitor_Metrics.json | Structured operational metrics snapshot                 |
| Startup_Error.txt         | Early fatal startup diagnostics                         |

## Non-Negotiable Rules

1. The monitor must run as a singleton protected by a global mutex.
2. config.json must be treated as a contract and validated before task execution begins.
3. New tasks must be proven manually before they are scheduled.
4. Paths in the scheduler must be absolute and operationally valid.
5. Encoding must be explicit. Do not rely on default shell encoding behavior.
6. DryRun mode must not launch external processes or modify state.
7. Metrics must be persisted periodically to `Logs/Monitor_Metrics.json`.

## Task Registration Standard

```json
{
  "name": "Friendly Task Name",
  "scriptPath": "C:\\Automacoes\\Module\\Trigger_Automation.vbs",
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

| Field               | Meaning                                                  |
| ------------------- | -------------------------------------------------------- |
| enabled             | Disable safely without deleting the task                 |
| preventOverlap      | Do not start a second instance while one is still active |
| waitForExit         | Decide whether the monitor blocks on process completion  |
| schedule.daysOfWeek | Day filter using the scheduler convention                |
| schedule.hours      | Hour filter; empty array means no hour-based trigger     |
| schedule.minutes    | Minute filter for execution windows                      |

## Supported CLI Flags

| Flag                 | Behavior                                                               |
| -------------------- | ---------------------------------------------------------------------- |
| `-RunOnce`           | Execute a single scheduling cycle and exit; used for on-demand testing |
| `-DryRun`            | Log eligible task launches without actually starting any process       |
| `-SkipTaskExecution` | Run the monitor loop but suppress all task launches                    |
| `-MutexNameOverride` | Override the mutex name for isolated testing                           |

`-DryRun` and `-RunOnce` can be combined for safe pre-flight validation.

## Enterprise Patterns

| Pattern             | Standard                                                                        |
| ------------------- | ------------------------------------------------------------------------------- |
| Mutex               | Use a single named global mutex to prevent duplicate monitor instances          |
| Hot reload          | Detect config changes via MD5 hash and reload without requiring process restart |
| Structured logging  | Emit timestamped `[PS]` prefixed INFO, WARN, and ERRO records to a rotating log |
| Startup diagnostics | Write a dedicated `Startup_Error.txt` for failures before full logging starts   |
| Validation first    | Refuse to run invalid task definitions; log the specific field error            |
| Heartbeat           | Emit periodic health log entries to prove the scheduler is still alive          |
| Metrics snapshot    | Persist `Monitor_Metrics.json` with cumulative and rolling-window counters      |

## Metrics Contract

`Logs/Monitor_Metrics.json` must be persisted periodically with the following shape:

```json
{
  "generatedAt": "2026-03-30T08:00:00-03:00",
  "monitorVersion": "3.6",
  "runningTasks": 0,
  "cumulative": {
    "TasksTriggered": 42,
    "TasksCompleted": 40,
    "TasksFinishedNonZero": 2,
    "TasksSkippedOverlap": 1,
    "ConfigReloadSuccess": 3,
    "ConfigReloadFailure": 0
  },
  "window": {
    "startedAt": "2026-03-30T07:00:00-03:00",
    "endedAt": "2026-03-30T08:00:00-03:00",
    "counters": {}
  }
}
```

## Operational Rules

| Topic                   | Guidance                                                                                         |
| ----------------------- | ------------------------------------------------------------------------------------------------ |
| Manual validation first | Only register a task after Trigger_Automation.vbs succeeds manually                              |
| Local time              | Scheduler uses Windows local time unless explicitly designed otherwise                           |
| UTF-8                   | Save config in UTF-8 and avoid ambiguous encoding writers                                        |
| Heartbeat               | Emit periodic health log entries at regular intervals (e.g., every 30 min)                       |
| Exit code mapping       | Define an `exitCodeMap` in config.json to produce readable log descriptions for known exit codes |
| DryRun testing          | Use `-RunOnce -DryRun` to validate schedule matching without launching any process               |

## Troubleshooting

| Symptom                                 | Root Cause                                                      | Action                                                                |
| --------------------------------------- | --------------------------------------------------------------- | --------------------------------------------------------------------- |
| Monitor does not start                  | Invalid JSON or startup failure before normal logging           | Inspect `Startup_Error.txt` first                                     |
| Task never fires                        | Schedule mismatch or disabled task                              | Validate `enabled` flag and schedule arrays against system local time |
| Overlap prevention suppresses execution | Prior process still active                                      | Confirm whether `preventOverlap` is intended and inspect task runtime |
| Hot reload does not react               | File encoding or save semantics interfere with change detection | Re-save config in explicit UTF-8 and verify MD5 hash comparison       |
| Metrics not updated                     | Save-MetricsSnapshot not called on schedule                     | Verify periodic flush call in the main loop                           |
| DryRun launches real processes          | DryRun flag not checked inside task launch logic                | Validate DryRun guard before `Start-Process` or similar calls         |

## Pre-Delivery Checklist

- [ ] config.json changes are schema-valid and use absolute paths.
- [ ] The target automation succeeds manually before scheduling.
- [ ] Singleton behavior remains enforced by a mutex.
- [ ] Logs carry `[PS]` prefix and follow the universal log format.
- [ ] Encoding behavior is explicit and safe.
- [ ] `-DryRun` flag is honored and prevents actual process launches.
- [ ] `-RunOnce` flag causes the monitor to exit after a single cycle.
- [ ] Metrics are persisted to `Logs/Monitor_Metrics.json` periodically.
- [ ] `Startup_Error.txt` captures fatal failures before logging is ready.
