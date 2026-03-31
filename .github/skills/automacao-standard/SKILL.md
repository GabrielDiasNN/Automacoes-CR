---
name: automacao-standard
description: "Use when creating, reviewing, or refactoring automation flows that follow the VBS -> Excel/VBA -> notification architecture."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise Automation Standard

## Purpose

Use this skill to design or modify automations that follow the repository execution model: a VBS entrypoint orchestrates Excel/VBA work, then optionally triggers outbound communication such as email or WhatsApp. The goal is operational reliability, deterministic cleanup, traceability, and safe restarts.

## Architecture Overview

| Layer                 | Responsibility                                                    | Required Outcome                   |
| --------------------- | ----------------------------------------------------------------- | ---------------------------------- |
| VBS entrypoint        | Open Excel, run macro, handle fatal failures, emit execution logs | Deterministic process lifecycle    |
| Excel/VBA core        | Execute business rules, validations, refreshes, exports           | Business result produced once      |
| Notification layer    | Send email, WhatsApp, or report-only output                       | No duplicate external side effects |
| Scheduler integration | Register task in config and run under monitor                     | Safe unattended execution          |

## Non-Negotiable Rules

1. Every automation must start from a dedicated Trigger_Automation.vbs derived from the project template.
2. Every automation must maintain a local Logs directory and write execution traces from the first meaningful step.
3. The flow must be restart-safe. Re-running the same execution must not duplicate sends, corrupt files, or leave orphan Excel processes.
4. Excel automation must always disable UI interference: DisplayAlerts = False, Visible = False, AskToUpdateLinks = False, and VBA must disable ScreenUpdating and EnableEvents when appropriate.
5. Cleanup is mandatory on every failure path. Excel objects and external processes must be released even when macro execution fails.
6. ExecId must be generated at VBS level and propagated to every downstream layer before any side effect occurs.
7. Every log line across all layers must follow the universal format: `[dd/MM/yyyy HH:mm:ss] [LAYER] [LEVEL] [ExecId:id] message`.

## Output Scope Selection

| Output mode | Implementation rule                                                      |
| ----------- | ------------------------------------------------------------------------ |
| WhatsApp    | Enable POST_EXECUTION_BAT in VBS and route to a BAT orchestrator         |
| Email       | Implement Outlook automation in VBA and validate attachments before send |
| Hybrid      | Combine both channels with explicit ordering and idempotency rules       |
| Report only | Generate files or calculations without external delivery                 |

## Required Components

| Component              | Why it exists                                 |
| ---------------------- | --------------------------------------------- |
| Trigger_Automation.vbs | Stable entrypoint and infrastructure boundary |
| Local Logs folder      | Operational diagnostics and audit trail       |
| Main VBA macro         | Encapsulates business execution               |
| Idempotency guard      | Prevents duplicate downstream side effects    |

## Feature Flags Pattern

Configure the VBS header explicitly. Do not infer runtime behavior from file presence alone.

```vbscript
' ========== MODULE CONFIGURATION ==========
excelPath = "C:\Automacoes\ModuleName\Workbook.xlsm"
macroName = "MainMacro"
logPath   = "C:\Automacoes\ModuleName\Logs\Execution.log"

' [Flag] Long-running VBA timeout monitor
USE_TIMEOUT_MONITOR = False
vbaLogPath          = "C:\Automacoes\ModuleName\Logs\VBA_Internal.log"
maxTimeoutSeconds   = 300

' [Flag] Post-execution bridge
POST_EXECUTION_BAT  = ""
```

| Scenario                     | USE_TIMEOUT_MONITOR | POST_EXECUTION_BAT |
| ---------------------------- | ------------------- | ------------------ |
| Short synchronous job        | False               | Empty              |
| Long-running Excel/VBA job   | True                | Empty              |
| Job with external bridge     | False               | BAT absolute path  |
| Long-running job with bridge | True                | BAT absolute path  |

## Implementation Workflow

1. Copy the \_Template module structure and rename it to the new automation name.
2. Configure Trigger_Automation.vbs with absolute paths, feature flags, and log destinations.
3. Implement the main VBA macro with explicit entrypoint signature and deterministic cleanup.
4. Add outbound integrations only after the core business path is stable when executed manually.
5. Register the automation in the root config.json only after the manual execution path succeeds.

## Engineering Patterns

| Pattern            | Standard                                                                                                 |
| ------------------ | -------------------------------------------------------------------------------------------------------- |
| ExecId             | Generate at the VBS entrypoint via `GerarExecId()` and propagate to every layer                          |
| ExecId propagation | VBS → VBA (via `modLogging.DefinirRunId`), VBS → BAT → Node.js (via `--exec-id` argument)                |
| Log format         | Every layer must produce lines as: `[dd/MM/yyyy HH:mm:ss] [LAYER] [LEVEL] [ExecId:id] message`           |
| Logging            | Log start, key transitions, exit path, and fatal failures                                                |
| Error handling     | Use selective error suppression only around expected failure points; restore normal handling immediately |
| Cleanup            | Centralize object disposal in a single routine and call it on all exits                                  |
| Idempotency        | Prevent duplicate sends, duplicate exports, and duplicate state transitions                              |

## Troubleshooting

| Symptom                           | Root Cause                                   | Action                                                               |
| --------------------------------- | -------------------------------------------- | -------------------------------------------------------------------- |
| Excel remains open after failure  | Cleanup path not centralized                 | Move teardown into a single cleanup routine and call it on all exits |
| Duplicate outbound messages       | No idempotency key or repeated trigger       | Add execution identity and persist send state                        |
| Monitor runs but job does nothing | Trigger misconfigured or macro name mismatch | Validate VBS header values and manual execution first                |
| Long job terminates early         | Timeout monitoring too aggressive            | Recalibrate maxTimeoutSeconds and validate VBA log heartbeat         |

## Pre-Delivery Checklist

- [ ] Trigger_Automation.vbs was created from the template and configured with absolute paths.
- [ ] Local Logs directory exists and the automation writes traceable logs.
- [ ] ExecId is generated at VBS level and propagated to VBA and Node.js layers.
- [ ] All log lines follow the universal format with `[LAYER]`, `[LEVEL]`, and `[ExecId:id]`.
- [ ] Excel and VBA cleanup are guaranteed on both success and failure.
- [ ] Output channel behavior is explicit and idempotent.
- [ ] Manual execution succeeds before scheduler registration.
