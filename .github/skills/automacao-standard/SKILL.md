---
name: automacao-standard
description: "Use when designing, reviewing, or refactoring automations that follow the repository flow from Trigger_Automation.vbs into Excel/VBA and optional outbound delivery channels."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise Automation Standard

## Purpose

Use this skill as the repository-level orchestration guide for automations that begin in VBS, execute core work in Excel/VBA, and optionally continue into email, WhatsApp, reports, or monitor registration. This skill explains how the layers fit together; it does not replace the runtime or channel-specific skills.

## When to Use

- Creating a new automation from the repository template.
- Refactoring end-to-end flows that cross VBS, Excel/VBA, BAT, Node.js, or scheduler integration.
- Reviewing whether a flow is restart-safe, manually testable, and ready for unattended execution.

## Do Not Use When

- The task is only about PowerShell implementation details.
- The question is only about VBA architecture or workbook sync tooling.
- The work is limited to one output channel without changing the orchestration path.

## Related Skills

- `automation-execution-contract`: ExecId, idempotency, ownership, and exit-code semantics.
- `automation-runtime-safety`: bootstrap diagnostics, cleanup, timeouts, and fail-fast behavior.
- `vba-enterprise-vbe-safe`: VBA architecture and ASCII-safe coding inside the VBE.
- `automacao-comms-email`: Outlook delivery from VBA.
- `automacao-comms-whatsapp`: bridge path through BAT and Node.js.
- `automacao-monitor`: task registration and unattended scheduling.

## Non-Negotiable Rules

1. Every automation must start from a dedicated `Trigger_Automation.vbs` derived from the repository template.
2. Every automation must keep a local `Logs` directory and write diagnostics from the first meaningful step.
3. The flow must be safe to rerun without duplicating sends, corrupting files, or leaving orphan Excel processes.
4. Excel automation must suppress UI interference unless the workflow is explicitly interactive.
5. Cleanup must release Excel, Outlook, and bridge resources on every exit path.
6. `ExecId` must be generated at the outer entrypoint and propagated before side effects.

## Architecture Overview

| Layer | Responsibility | Required outcome |
| --- | --- | --- |
| `Trigger_Automation.vbs` | Entrypoint, Excel lifecycle, fatal handling, timeout watcher | Deterministic launch and teardown |
| Excel/VBA core | Business rules, refreshes, exports, validations | Business result produced once |
| Optional bridge | BAT or Node.js handoff for non-VBA delivery | Preserved exit code and correlation |
| Scheduler integration | `config.json` registration under the monitor | Safe unattended execution |

## Output Scope Selection

| Output mode | Implementation rule |
| --- | --- |
| Report only | Finish inside Excel/VBA and persist artifacts only |
| Email | Deliver from VBA through Outlook and attachment validation |
| WhatsApp | Use `POST_EXECUTION_BAT` and route through the BAT plus Node.js bridge |
| Hybrid | Define explicit ordering and separate idempotency boundaries per channel |

## Execution Model

1. Copy the `_Template` structure or an equivalent existing automation.
2. Configure `Trigger_Automation.vbs` with absolute paths, macro name, log file, and feature flags.
3. Implement the main VBA macro and its orchestration classes.
4. Stabilize the core business run manually before enabling any outbound delivery.
5. Add channel integration only after the core flow is restart-safe.
6. Register in `config.json` only after manual execution succeeds.

## Feature-Flag Pattern

Declare runtime behavior explicitly in the entrypoint; do not infer from file presence.

```vbscript
' ========== MODULE CONFIGURATION ==========
excelPath = "C:\Automacoes\ModuleName\Workbook.xlsm"
macroName = "MainMacro"
logPath   = "C:\Automacoes\ModuleName\Logs\Execution.log"

' Long-running VBA timeout monitor
USE_TIMEOUT_MONITOR = False
vbaLogPath          = "C:\Automacoes\ModuleName\Logs\VBA_Internal.log"
maxTimeoutSeconds   = 300

' Post-execution bridge
POST_EXECUTION_BAT  = ""
```

## Repo-Specific Constraints

- `Trigger_Automation.vbs` must monitor the same log that the VBA layer writes. In Montagem, that means the unified `Logs/Montagem.log`, not an empty daily file.
- The trigger parser must treat the success sentinel case-insensitively so `FIM Do PROCESSO. Resultado=Sucesso` and `FIM DO PROCESSO.` variants do not diverge.
- Timeout loops based on `Timer` must use a day-rollover-safe delta calculation.
- `POST_EXECUTION_BAT` must preserve the original `ExecId`; never regenerate it after the main execution.
- External-notification dedupe must use stable business hashes when reruns are possible.

## Validation

1. Run the trigger manually and confirm that the first meaningful log line appears in the expected local log file.
2. Validate that the main macro can succeed without any outbound integration enabled.
3. Test one failure path and confirm Excel cleanup still happens.
4. If a bridge exists, confirm the same `ExecId` appears in VBS, VBA, and downstream logs.
5. Register in the monitor only after the manual path is stable.

## Troubleshooting

| Symptom | Root Cause | Action |
| --- | --- | --- |
| Excel remains open after failure | Cleanup path is fragmented | Centralize teardown and call it on all exits |
| Duplicate outbound messages | Dedupe tied only to trigger time or `ExecId` | Introduce a stable `operationKey` for the outbound side effect |
| Trigger runs but the job appears idle | Header values or macro name mismatch | Validate absolute paths, macro name, and local log destination |
| Long run times out incorrectly | Timer delta or log watcher contract is wrong | Rework timeout logic and verify the trigger watches the correct log |

## Pre-Delivery Checklist

- [ ] `Trigger_Automation.vbs` is derived from the template and uses absolute paths.
- [ ] Local `Logs` directory exists and receives traceable output.
- [ ] Core Excel/VBA execution succeeds manually before scheduler registration.
- [ ] `ExecId` is preserved across every layer.
- [ ] Output channels are explicit and individually idempotent.
- [ ] Trigger timeout and success-sentinel rules match the owning automation.
