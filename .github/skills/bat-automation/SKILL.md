---
name: bat-automation
description: "Use when scripting Windows BAT files that orchestrate external processes, preserve downstream exit codes, and bridge VBS with PowerShell or Node.js in unattended automation flows."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise BAT Automation Standard

## Purpose

Use this skill for Windows batch files that act as orchestration bridges. In this repository, BAT is primarily the handoff layer between VBS and Node.js or between callers and external tools. Keep BAT small, explicit, and operationally traceable.

## When to Use

- Creating or reviewing `RunWhatsApp.bat` style bridge scripts.
- Preserving exit codes across process launches.
- Hardening prerequisite checks, quoting, and bootstrap diagnostics in BAT.

## Do Not Use When

- The workflow logic belongs in PowerShell, Node.js, or VBA and BAT is only a thin launcher.
- The task is only about cross-layer correlation semantics; use `automation-execution-contract`.
- The question is only about log format or message privacy.

## Related Skills

- `automation-execution-contract`: `ExecId`, exit-code registry, and ownership rules.
- `automation-runtime-safety`: bootstrap diagnostics and fail-fast behavior.
- `automacao-comms-whatsapp`: repository-specific bridge behavior for WhatsApp delivery.
- `nodejs-automation`: downstream Node.js runtime contract.

## Non-Negotiable Rules

1. Start with `@echo off` and `setlocal`.
2. Enable delayed expansion when values are read inside `IF` or `FOR` blocks.
3. Validate prerequisites before launching downstream processes.
4. Capture and return downstream exit codes immediately.
5. Quote every path that may contain spaces.
6. Keep BAT focused on orchestration, not business logic.

## Runtime Contract

| Concern | Standard |
| --- | --- |
| Variable expansion | Use `!VAR!` inside blocks when delayed expansion is enabled |
| Exit codes | Capture `%ERRORLEVEL%` immediately after the downstream command |
| Logging | Write bootstrap diagnostics before main branching |
| Paths | Use fully quoted paths and set working directory explicitly when needed |
| Encoding | Use `chcp 65001` only when logs or output need UTF-8-safe text |

## Bridge Pattern

BAT files that bridge VBS to Node.js must:

1. Receive `ExecId` from the caller.
2. Validate Node.js and the target script path.
3. Pass `--exec-id` unchanged to Node.js.
4. Return the downstream exit code unchanged unless there is a deliberate remap.

```bat
@echo off
setlocal EnableDelayedExpansion

set "EXEC_ID=%~1"
set "NODE_SCRIPT=%~dp0sendWhatsApp.js"

if not exist "%NODE_SCRIPT%" exit /b 30

node "%NODE_SCRIPT%" --exec-id "%EXEC_ID%"
set "EXIT_CODE=%ERRORLEVEL%"
exit /b %EXIT_CODE%
```

## Repo-Specific Constraints

- For WhatsApp orchestration, concurrency detection must use the absolute path of `sendWhatsApp.js`, not a generic process name.
- Preserve the same `ExecId` received from `Trigger_Automation.vbs`; do not invent a new identifier inside BAT.
- If UTF-8 logging is needed, set `chcp 65001 >nul` near the top and keep the downstream process expectations aligned.

## Validation

1. Run the BAT file with a representative `ExecId` and confirm the argument reaches the downstream process.
2. Test a missing-script or missing-runtime path and confirm the exit code remains meaningful.
3. Confirm the working directory and quoted paths behave correctly when folders contain spaces.
4. Verify that any bootstrap log or console output appears before the main launch.

## Troubleshooting

| Symptom | Root Cause | Action |
| --- | --- | --- |
| Variable value appears stale inside a block | Percent expansion evaluated too early | Enable delayed expansion and switch to `!VAR!` |
| Exit code is lost after a subroutine or extra command | `%ERRORLEVEL%` overwritten | Capture it immediately and return it explicitly |
| Wrong bridge instance is considered running | Concurrency check too generic | Match by absolute script path |
| External tool launches in the wrong folder | Missing explicit working directory handling | Use `cd /d` or launch with a validated absolute path |

## Pre-Delivery Checklist

- [ ] BAT remains a thin orchestration layer.
- [ ] Delayed expansion is enabled only where needed.
- [ ] Paths are quoted and validated.
- [ ] Downstream exit codes are preserved.
- [ ] `ExecId` is forwarded unchanged.
- [ ] Concurrency detection uses the correct script identity when applicable.
