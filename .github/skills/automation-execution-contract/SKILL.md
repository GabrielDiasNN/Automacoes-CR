---
name: automation-execution-contract
description: "Use when defining or reviewing execution identity, idempotency, exit codes, ownership boundaries, or feature-flag precedence across VBS, VBA, PowerShell, BAT, and Node.js automation flows."
user-invocable: false
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise Automation Execution Contract

## Purpose

Use this skill as the shared execution contract for the repository. It defines how a single automation run is identified, how side effects are deduplicated, how failures propagate between layers, and how exit codes remain meaningful from the entrypoint to the outer scheduler.

## When to Use

- Designing or refactoring flows that cross VBS, Excel/VBA, PowerShell, BAT, and Node.js.
- Defining `ExecId`, `RunId`, `execKey`, or other execution-correlation rules.
- Standardizing exit-code behavior across monitor, bridges, and delivery scripts.
- Clarifying which layer owns the final error log or user-visible failure.

## Do Not Use When

- The task is only about syntax, formatting, or style inside a single language.
- The question is exclusively about HTML/CSS rendering.
- The workflow does not cross process or layer boundaries.

## Related Skills

- `automacao-standard`: overall repository execution path and VBS to Excel/VBA orchestration.
- `automation-runtime-safety`: bootstrap diagnostics, cleanup, environment safety, and bounded retries.
- `log-standardization`: universal log line, severity alignment, and privacy rules.
- `automacao-monitor`: monitor-specific dispatch behavior and scheduler semantics.

## Non-Negotiable Rules

1. Every execution must have one correlation identity generated before the first side effect.
2. `ExecId` exists for traceability; idempotency must use a stable business key when reruns are possible.
3. Exit codes must be explicit, documented, and preserved through every bridge layer.
4. A failure must be logged once at the ownership boundary, not duplicated blindly upstream.
5. Feature-flag precedence must be explicit. Never infer behavior from file presence alone.
6. A downstream layer must not silently generate a new execution identity unless the workflow intentionally restarts.

## Execution Identity Contract

| Concept | Purpose | Rule |
| --- | --- | --- |
| `ExecId` | Cross-layer correlation | Generate once at the outer entrypoint and propagate unchanged |
| `RunId` | Internal alias for VBA/logging compatibility | Mirror `ExecId`; do not create a second unrelated value |
| `operationKey` or `execKey` | Idempotency key | Derive from stable business inputs, not only from timestamp |
| `taskName` | Operational labeling | Human-readable name for logs and metrics; not a unique execution id |

## Propagation Chain

| Layer | Contract |
| --- | --- |
| VBS entrypoint | Generates `ExecId` and passes it forward before opening external channels |
| PowerShell monitor | Generates or receives the `ExecId` for the triggered task and passes it as the first positional argument to child `.ps1` scripts |
| Excel/VBA | Receives the value and applies it through `modLogging.DefinirRunId` or equivalent |
| BAT bridge | Receives the value from the caller and forwards it unchanged to Node.js |
| Node.js bridge | Accepts `--exec-id` and includes the value in logs and state records |

## Idempotency Contract

Use `ExecId` for correlation and a stable key for duplicate prevention.

| Scenario | Recommended key |
| --- | --- |
| One-shot technical run | `ExecId` may be sufficient |
| Notification resend risk | Hash only the business divergence payload, not volatile row order or totals |
| File export with overwrite risk | Stable key from target artifact + business date/window |
| WhatsApp or email delivery | Stable recipient + business payload hash + channel identifier |

For Montagem-style alerting, the state hash must represent only real divergences. Do not include volatile ordering or row counts that turn `0 -> 0` into a fake change.

## Exit-Code Registry

| Code or Range | Meaning |
| --- | --- |
| `0` | Success or intentionally disabled behavior |
| `1-9` | Validation or prerequisite failures |
| `10-19` | Layer-specific validation codes |
| `11` | Attachment or required file missing in bridge-style flows |
| `20-29` | Business or operational failures |
| `21` | Re-authentication required |
| `22` | Invalid runtime configuration |
| `23` and `40` | Operational monitor outcomes treated as WARN, not ERROR |
| `30-49` | Environment, launch, or infrastructure failures |
| `99` | Unexpected fatal failure |

When a layer introduces a custom code, document it relative to this registry and preserve it through every caller.

## Ownership Boundary

| Event | Owning layer |
| --- | --- |
| Workbook automation or VBA business rule failure | Excel/VBA caller |
| Scheduler dispatch issue | PowerShell monitor |
| Bridge launch failure | BAT or PowerShell launcher |
| WhatsApp runtime/authentication failure | Node.js bridge |
| Outlook `.Send` blocked by corporate prompt/policy | VBA/Outlook adapter |

Upstream layers may summarize the outcome, but must not re-log the same failure as if they discovered it.

## Feature-Flag and Configuration Precedence

Use an explicit order and document exceptions per automation.

Recommended precedence for this repository:

1. Explicit runtime override designed by the automation.
2. Scheduler-level task configuration.
3. Entry-point defaults such as VBS header flags.
4. Hardcoded fallback.

If an automation intentionally uses a different order, document it in the owning skill.

## Repo-Specific Constraints

- `Trigger_Automation.vbs` owns the initial `ExecId` when the flow starts from VBS.
- `MonitorAutomacoes.ps1` passes `ExecId` positionally to child PowerShell scripts.
- `POST_EXECUTION_BAT` must preserve the same `ExecId`; never regenerate after the main VBA run.
- Deduplication logic for Montagem notifications must be based on divergences only.

## Validation

1. Confirm that the first meaningful log line already carries `ExecId` or explicitly states bootstrap mode.
2. Verify that rerunning the same business condition does not duplicate external side effects.
3. Confirm that bridge layers return the original downstream exit code unless they are intentionally remapping it.
4. Test at least one owned failure path and ensure the error is logged at the correct boundary only once.

## Troubleshooting

| Symptom | Root Cause | Action |
| --- | --- | --- |
| Same run produces duplicate notifications | Correlation id reused as idempotency key in a rerun scenario | Introduce a stable business `operationKey` |
| Monitor log says error but child log has nothing useful | Ownership boundary unclear | Move the detailed failure log into the layer that caught the exception |
| Exit code loses meaning after BAT or PowerShell bridge | Caller overwrote `%ERRORLEVEL%` or `$LASTEXITCODE` | Capture and return the downstream code immediately |
| Post-execution step cannot be correlated | `ExecId` regenerated in bridge step | Preserve the original identifier from the entrypoint |

## Pre-Delivery Checklist

- [ ] `ExecId` and idempotency key are not conflated when reruns are possible.
- [ ] Every bridge preserves downstream exit codes.
- [ ] Failure ownership is explicit.
- [ ] Feature-flag precedence is documented.
- [ ] Related skills are referenced instead of duplicating shared execution rules.
