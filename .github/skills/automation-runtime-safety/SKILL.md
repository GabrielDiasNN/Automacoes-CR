---
name: automation-runtime-safety
description: "Use when hardening bootstrap diagnostics, cleanup, config validation, timeout strategy, encoding behavior, or process safety across enterprise automation layers."
user-invocable: false
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise Automation Runtime Safety

## Purpose

Use this skill for cross-layer runtime hardening. It captures the repository standards that make unattended automation diagnosable, restart-safe, and resistant to silent corruption or runaway retries.

## When to Use

- Designing bootstrap and failure behavior before the main logger is ready.
- Defining cleanup, timeout, lock, or retry policies.
- Reviewing scripts that open Excel, dispatch processes, or persist files.
- Standardizing `-DryRun`, `-RunOnce`, visibility modes, and environment parity.

## Do Not Use When

- The work is only about business rules, report layout, or message wording.
- The main question is naming or architecture of VBA classes.
- The task is only about log-line format; use `log-standardization` for that.

## Related Skills

- `automation-execution-contract`: correlation, idempotency, ownership, and exit-code semantics.
- `log-standardization`: logging format and severity rules.
- `powershell-automation`: PowerShell-specific runtime guards and PS 5.1 constraints.
- `vba-governance-sync`: workbook lock, compile gate, and VBA import safety.

## Non-Negotiable Rules

1. Write bootstrap diagnostics before expensive setup whenever startup can fail early.
2. Validate configuration and prerequisites before the first destructive side effect.
3. Cleanup must run on every exit path, including partial failures.
4. Timeouts, retries, and polling loops must be bounded and justified.
5. Locks and read-only states must fail fast with explicit diagnostics, never silently.
6. Encoding behavior must be explicit when files or logs are written.

## Runtime Safety Baseline

| Concern | Standard |
| --- | --- |
| Bootstrap logging | Write a minimal line before full logger initialization |
| Config validation | Refuse invalid config before entering the main loop or side effects |
| Cleanup | Centralize release of COM objects, file handles, and child processes |
| Retry | Use bounded attempts and clear stop conditions |
| Timeout | Use explicit timeout strategy; do not rely on indefinite waits |
| Dry-run | Skip side effects but preserve validation and logging |

## Layer Guidance

| Layer | Safety rule |
| --- | --- |
| PowerShell | Use startup diagnostics for pre-logger failures and explicit UTF-8 writes |
| BAT | Log before branching and preserve error codes immediately |
| Node.js | Install global fatal handlers and flush diagnostics before exit |
| Excel/VBA | Release Excel and Outlook objects on every path; keep UI suppression deterministic |
| Workbook sync | Abort immediately when workbook is read-only or compile gate fails |

## Timeout and Retry Rules

- Prefer bounded retries with delay and a terminal failure outcome.
- For VBS timeout loops based on `Timer`, use day-rollover-safe delta logic.
- Do not let a monitor or bridge keep retrying when authentication is known to be expired.
- Treat lock/compile failures as fast exits rather than waiting for long macro timeouts.

## Environment Parity

| Mode | Rule |
| --- | --- |
| Interactive | Reserve visible mode for pairing, debugging, or approval-sensitive flows |
| Unattended | Default to silent execution with explicit logs and deterministic cleanup |
| DryRun | Validate config and schedule matching but skip external launches or file mutation |
| RunOnce | Execute a single cycle and exit with the correct final code |

## Repo-Specific Constraints

- `MonitorAutomacoes.ps1` should support `-RunOnce` and `-DryRun` together for safe preflight.
- `-MutexNameOverride` with `-RunOnce -SkipTaskExecution` is the preferred monitor smoke-test path when the main mutex is already in use.
- In Montagem, preflight compile checks that rely on `Excel.VBE.CommandBars.FindControl` must degrade to WARN when the control is unavailable, not produce a false compile failure.
- Workbook sync/import must stop immediately on `Workbook.ReadOnly = True` and must compile before save.

## Validation

1. Test one startup-failure path and confirm the bootstrap diagnostic exists.
2. Simulate one lock or configuration error and verify it fails fast.
3. Confirm that `-DryRun` does not launch external processes or mutate persistent state.
4. Verify that every successful run releases owned resources before exit.

## Troubleshooting

| Symptom | Root Cause | Action |
| --- | --- | --- |
| Process dies before normal log file appears | Failure before logger initialization | Add or inspect bootstrap diagnostics |
| Automation hangs until global timeout | Lock or prerequisite failure handled too late | Move validation and lock checks before the main execution path |
| DryRun still changes state | Guard applied after side effect | Move `DryRun` branching ahead of launch or write operations |
| Retry loop never stabilizes | Missing stop condition or auth-expired case | Add bounded retry policy and terminal exit mapping |

## Pre-Delivery Checklist

- [ ] Bootstrap diagnostics exist where startup can fail early.
- [ ] Configuration and prerequisites are validated before side effects.
- [ ] Cleanup is centralized and guaranteed.
- [ ] Timeouts and retries are bounded.
- [ ] Lock and read-only scenarios fail fast.
- [ ] Dry-run and run-once semantics are explicit.
