---
name: nodejs-automation
description: "Use when writing or refactoring Node.js automation scripts that need deterministic startup, typed operational failures, bounded retries, and explicit state handling in unattended flows."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise Node.js Automation Standard

## Purpose

Use this skill for Node.js automation scripts in the repository, especially short-lived bridges, messaging delivery jobs, and auxiliary runtime workers. The emphasis is deterministic startup, explicit exit mapping, bounded retries, and safe state persistence.

## When to Use

- Implementing or refactoring `sendWhatsApp.js` style scripts.
- Reviewing startup behavior, retries, or `ManagedError` design.
- Defining config loading, state persistence, and fatal-process handling in Node.js.

## Do Not Use When

- The process should be a long-running scheduler; use `automacao-monitor` for that concern.
- The question is only about BAT bridging or entrypoint orchestration.
- The work is only about HTML/CSS output.

## Related Skills

- `automation-execution-contract`: `ExecId`, idempotency boundaries, and exit-code registry.
- `automation-runtime-safety`: bootstrap diagnostics, retries, and failure hardening.
- `automacao-comms-whatsapp`: repository-specific WhatsApp delivery rules.
- `nodejs-html-css`: HTML/CSS generation outside VBA.

## Non-Negotiable Rules

1. Write bootstrap diagnostics before any heavy initialization and before `require()` if startup can fail very early.
2. Centralize exit codes in one immutable map.
3. Use typed operational errors with explicit `exitCode`.
4. Handle `unhandledRejection` and `uncaughtException` deterministically.
5. Retries and waits must be bounded.
6. Accept and log `--exec-id` when the flow participates in repository correlation.

## Runtime Contract

| Concern | Standard |
| --- | --- |
| Process arguments | Parse documented args and defaults explicitly |
| Exit behavior | Flush diagnostics and exit with a mapped code |
| Error taxonomy | Separate validation, business, infrastructure, and fatal paths |
| Config loading | Validate config before side effects |
| State persistence | Use JSON state files for idempotency or resumability |
| Visibility mode | Keep interactive or pairing mode explicit and separate |

## Recommended Error Shape

```js
class ManagedError extends Error {
  constructor(message, exitCode, details) {
    super(message);
    this.name = "ManagedError";
    this.exitCode = exitCode;
    this.details = details;
  }
}
```

## Idempotency and State

- Use `ExecId` for traceability and a stable business key for duplicate prevention when reruns are possible.
- Persist state in a file such as `whatsapp-state.json` only when the script owns resumability or duplicate prevention.
- Keep state-file writes deterministic and scoped to the owning operation.

## Repo-Specific Constraints

- `sendWhatsApp.js` style flows must stay short-lived; do not leave background browser instances running after completion.
- Session assets like `.wwebjs_auth` are operational state and must not be treated as disposable scratch data.
- Align bridge-specific exit codes such as `11`, `21`, and `22` with the shared execution contract.

## Validation

1. Test bootstrap failure and confirm a diagnostic line exists before the main logger finishes initialization.
2. Validate config shape before the first external side effect.
3. Test one retry path and confirm it stops at the configured bound.
4. Verify that the final exit code matches the owning failure category.
5. Confirm that state files prevent duplicates when the scenario requires it.

## Troubleshooting

| Symptom | Root Cause | Action |
| --- | --- | --- |
| Script fails before normal logs appear | Bootstrap failure too early | Add or inspect the minimal startup logger |
| Duplicate side effects | State key is missing or too volatile | Introduce a stable operation key and persist it |
| Infinite retries | Missing stop condition | Add bounded attempts and terminal failure mapping |
| Silent termination | Missing global fatal handlers | Install handlers for `unhandledRejection` and `uncaughtException` |

## Pre-Delivery Checklist

- [ ] Bootstrap diagnostics exist where startup can fail early.
- [ ] Exit codes are centralized and documented.
- [ ] Config validation happens before side effects.
- [ ] Retries are bounded and explicit.
- [ ] State persistence is deterministic and justified.
- [ ] The script exits cleanly on both success and failure.
