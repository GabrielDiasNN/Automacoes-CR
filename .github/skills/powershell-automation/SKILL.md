---
name: powershell-automation
description: "Use when creating, reviewing, or refactoring PowerShell automation scripts that need explicit logging, UTF-8-safe I/O, config validation, process safety, and compatibility with the repository runtime."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise PowerShell Automation Standard

## Purpose

Use this skill for PowerShell scripts in the repository, especially monitors, runners, tooling commands, and maintenance scripts. The goal is predictable behavior in Windows PowerShell 5.1-compatible environments, explicit diagnostics, and safe unattended execution.

## When to Use

- Writing or refactoring `.ps1` scripts used by automations or tooling.
- Reviewing logging, encoding, mutex, config validation, or loop behavior.
- Hardening startup diagnostics, exit codes, and process safety in PowerShell.

## Do Not Use When

- The work is only about monitor task registration; use `automacao-monitor`.
- The task is only about workbook import or VBA compile safety.
- The question is only about plain-text log format; use `log-standardization`.

## Related Skills

- `automation-runtime-safety`: bootstrap diagnostics, cleanup, dry-run, and fail-fast rules.
- `automation-execution-contract`: `ExecId`, ownership, and exit-code semantics.
- `automacao-monitor`: scheduler-specific contract and operational dispatch rules.
- `log-standardization`: canonical log-line structure and privacy rules.

## Non-Negotiable Rules

1. Set `$ErrorActionPreference = "Stop"` near the top of every non-trivial script.
2. Use `[CmdletBinding()]` and a `param()` block for maintainable scripts.
3. Never rely on default encoding for file output.
4. Validate configuration and prerequisites before the first destructive side effect.
5. Use Approved Verbs for function names.
6. Do not use `$args` as a custom variable name.

## Script Header Standard

```powershell
# ==============================================================================
# ARQUIVO: NomeDoScript.ps1
# DESCRICAO: Resumo do que o script faz.
# ==============================================================================

[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ExecId = "",
    [switch]$DryRun,
    [switch]$RunOnce
)

$ErrorActionPreference = "Stop"
```

## Core Runtime Contract

| Concern | Standard |
| --- | --- |
| Logging | Keep one `Write-Log` surface and explicit log type |
| Encoding | Use explicit UTF-8 helpers for append and full-file writes |
| Config validation | Implement `Test-Configuration` or equivalent before main execution |
| Loop control | Support `-RunOnce` in long-running scripts |
| Dry run | Honor `-DryRun` before side effects |
| Mutex | Use only when duplicate instances are unsafe |

## UTF-8 and Startup Diagnostics

- Use explicit `System.Text.UTF8Encoding($false)` helpers instead of host defaults.
- For startup failures before the main logger exists, define an emergency log path early and write with `StreamWriter` or `WriteAllText`.
- Keep console and file output encoding explicit when logs must preserve deterministic text.

## Approved Implementation Patterns

### `Write-Log`

Keep one canonical function per script and honor repository types such as `INFO`, `WARN`, and `ERRO`.

### `Test-Configuration`

Validate JSON or script parameters before side effects. Reject invalid structure early.

### `Get-ConfigHash`

Use hash-based reload detection only in scripts that truly need hot reload.

### `-DryRun`

Skip mutation and launch steps, but keep validation and logging active.

### `-RunOnce`

Execute one cycle and return the real final exit code.

## Compatibility Rules

| Topic | Rule |
| --- | --- |
| Runtime baseline | Stay compatible with Windows PowerShell 5.1 unless the repository explicitly changes the baseline |
| Relative paths | Avoid APIs unavailable in the baseline, such as `GetRelativePath`; prefer compatible helpers |
| String interpolation | Avoid patterns like `$var:`; prefer `${var}` or format operator `-f` |
| Diagnostic noise | Treat editor-only parse warnings with caution and confirm with runtime when needed |

## Repo-Specific Constraints

- Avoid using `$args` as a custom argument list variable because it can shadow the automatic variable and trigger incorrect invocation behavior.
- `Tools/Test-PowerShellApprovedVerbs.ps1` is part of repository governance; do not introduce non-approved verb function names.
- If diagnostics appear inconsistent after rename or bulk edit, confirm with runtime or dedicated validation before rewriting working code to satisfy a stale editor warning.
- Startup diagnostics should capture failures that occur before the main logger is initialized.

## Validation

1. Run the script in a representative environment and confirm it parses and exits deterministically.
2. Test `-DryRun` if the script mutates state or launches processes.
3. Test `-RunOnce` when the script is loop-based.
4. Validate one failure path and confirm the error is logged with context.
5. Run verb governance checks if new functions were added.

## Troubleshooting

| Symptom | Root Cause | Action |
| --- | --- | --- |
| Script behaves differently in another host | Hidden dependency on newer PowerShell API | Replace with PS 5.1-compatible helper |
| Variable interpolation breaks unexpectedly | Ambiguous `$var:` pattern | Use `${var}` or `-f` formatting |
| Tool launches wrong process or enters interactive shell | Custom variable named `$args` | Rename the variable and pass arguments explicitly |
| Parser warning does not match runtime | Editor cache or false positive | Confirm with execution or dedicated validation script |

## Pre-Delivery Checklist

- [ ] Script uses `[CmdletBinding()]`, `param()`, and explicit error handling.
- [ ] UTF-8 behavior is explicit for file output.
- [ ] `Write-Log`, config validation, and runtime guards are centralized.
- [ ] `-DryRun` and `-RunOnce` behave correctly when applicable.
- [ ] Function names use Approved Verbs.
- [ ] The script stays compatible with the repository runtime baseline.
