---
name: log-standardization
description: "Use when defining, reviewing, or troubleshooting plain-text, cross-layer logging across the VBS, VBA, PowerShell, BAT, and Node.js automation stack."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Log Standardization

## Purpose

Use this skill as the single source of truth for operational logging in the repository. It defines log-line structure, severity alignment, privacy rules, and the ownership model that keeps unattended triage readable across layers.

## When to Use

- Creating or refactoring logging in VBS, VBA, PowerShell, BAT, or Node.js.
- Reviewing whether logs are correlated, privacy-safe, and consistent.
- Standardizing milestone events, error ownership, and metrics exceptions.

## Do Not Use When

- The task is only about execution identity or idempotency semantics; use `automation-execution-contract`.
- The task is only about runtime cleanup or timeout behavior; use `automation-runtime-safety`.
- The question is only about UI formatting or report layout.

## Related Skills

- `automation-execution-contract`: `ExecId`, ownership boundaries, and exit-code semantics.
- `automation-runtime-safety`: bootstrap diagnostics and failure hardening.
- `powershell-automation`: PowerShell-specific logging helpers and encoding rules.
- `vba-enterprise-vbe-safe`: centralized VBA logging surfaces and ASCII-safe internals.

## Non-Negotiable Rules

1. Log facts, not guesses.
2. Log before side effects, not only after them.
3. Include `ExecId` whenever the value is already available.
4. Use the same milestone vocabulary across layers whenever the event is logically the same.
5. Log a failure once at the layer that owns the handling.
6. Never write secrets, raw credentials, or full recipient identifiers to plain-text logs.

## Universal Log Line Format

All normal operational log lines must follow this structure:

```text
[dd/MM/yyyy HH:mm:ss] [LAYER] [LEVEL] [ExecId:id] message
```

| Segment | Description |
| --- | --- |
| `[dd/MM/yyyy HH:mm:ss]` | Local timestamp in Brazilian format |
| `[LAYER]` | `VBS`, `VBA`, `PS`, `BAT`, or `NODE` |
| `[LEVEL]` | `DEBUG`, `INFO`, `WARN`, `ERROR`, or `FATAL` |
| `[ExecId:id]` | Correlation identifier when available |
| `message` | Concise factual statement |

Bootstrap lines may omit `ExecId` only before the execution identity exists.

## Severity Model

| Level | When to use |
| --- | --- |
| `DEBUG` | Local diagnostics that are intentionally verbose |
| `INFO` | Expected milestones and successful transitions |
| `WARN` | Degraded state or expected validation issue that did not stop the flow |
| `ERROR` | Failed operation that requires investigation |
| `FATAL` | Unrecoverable state that forces the process to stop |

Repository-specific exception: the PowerShell monitor uses `ERRO` instead of `ERROR` by established convention.

## Layer Prefixes and Files

| Layer | Prefix | Typical file |
| --- | --- | --- |
| VBS entrypoint | `VBS` | `Module/Logs/Execution.log` |
| VBA runtime | `VBA` | module-specific log such as `Logs/Montagem.log` |
| PowerShell monitor | `PS` | `Logs/yyyy-MM_Monitor.log` |
| BAT bridge | `BAT` | local bridge or bootstrap log when applicable |
| Node.js bridge | `NODE` | file configured by the bridge configuration |

## Ownership Rules

| Event | Logging rule |
| --- | --- |
| Bootstrap start | Log immediately, even before full logger initialization |
| Business validation issue | Log as `WARN` at the layer that evaluated the condition |
| Retry attempt | Log intermediate attempts as `WARN`; final failure at ownership boundary |
| Hard failure | Log detailed context once at the layer that caught or decided the failure |
| Final completion | Log once with outcome and relevant exit code |

## Structured Metrics Exception

`Logs/Monitor_Metrics.json` is the only approved structured JSON metrics file. It is a snapshot, not a replacement for plain-text logs.

Do not convert normal operational logs to JSON.

## Privacy Rules

Never log:

- Passwords, tokens, credentials, or cookies
- Full phone numbers or email addresses
- Full document numbers
- Private cryptographic material

Use masking or redaction when business context requires a trace.

## Repo-Specific Constraints

- Montagem `modLogging.bas` must emit lines as `[dd/MM/yyyy HH:mm:ss] [VBA] [LEVEL] [ExecId:id] message` and sanitize internal text to remain ASCII-safe before writing to the unified `Logs/Montagem.log`.
- In Monitor and Montagem validation flows, search logs by `ExecId` and a short time window. Broad historical filters create noisy diagnostics.
- Heartbeat or polling loops must not flood `INFO` lines unless state changed.

## Validation

1. Confirm the first meaningful log line already carries the correct layer prefix.
2. Confirm the same `ExecId` can be followed across the layers that took part in the run.
3. Verify that sensitive fields are masked.
4. Test one failure and ensure it appears once at the correct ownership boundary.

## Troubleshooting

| Symptom | Root Cause | Action |
| --- | --- | --- |
| Logs from the same run cannot be correlated | `ExecId` missing or regenerated | Rework propagation from the outer entrypoint |
| Alert triage returns stale history | Search not narrowed by `ExecId` and time window | Filter by correlation id and recent execution window |
| Same failure appears in multiple layers | Ownership boundary unclear | Keep the detailed error at the handling layer and only summarize upstream |
| Log text breaks in VBA output | Internal strings not sanitized for the target file path | Normalize VBE-facing text and preserve accents only in safe external destinations |

## Pre-Delivery Checklist

- [ ] Log lines follow the canonical structure.
- [ ] Severity choices are aligned with the repository model.
- [ ] Sensitive values are masked or omitted.
- [ ] Metrics remain in `Monitor_Metrics.json`, not mixed with plain-text logs.
- [ ] Failure ownership is clear and not duplicated across layers.
