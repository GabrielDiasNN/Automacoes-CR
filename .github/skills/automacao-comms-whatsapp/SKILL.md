---
name: automacao-comms-whatsapp
description: "Use when implementing, reviewing, or troubleshooting WhatsApp delivery bridges built with VBS, BAT, Node.js, and whatsapp-web.js in unattended automation flows."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise WhatsApp Delivery Bridge

## Purpose

Use this skill for the repository WhatsApp delivery path that starts in the trigger layer, passes through a BAT bridge, and ends in a Node.js sender backed by `whatsapp-web.js`. The focus is stable authentication, idempotent delivery, explicit exit codes, and operational recovery.

## When to Use

- Building or reviewing `RunWhatsApp.bat`, `sendWhatsApp.js`, or related config/state files.
- Troubleshooting authentication expiry, duplicate sends, or attachment handoff.
- Defining how WhatsApp delivery participates in the broader automation flow.

## Do Not Use When

- The work is only about generic Node.js runtime patterns; use `nodejs-automation`.
- The question is only about BAT quoting or path handling; use `bat-automation`.
- The flow does not use the repository WhatsApp bridge stack.

## Related Skills

- `automacao-standard`: VBS to VBA to bridge orchestration.
- `automation-execution-contract`: `ExecId`, idempotency boundaries, and exit-code semantics.
- `bat-automation`: bridge launch, quoting, and downstream exit-code preservation.
- `nodejs-automation`: bootstrap logging, typed errors, and deterministic shutdown.

## Non-Negotiable Rules

1. Bootstrap diagnostics must exist before the Node.js runtime fully initializes.
2. Delivery must be idempotent; repeated executions of the same business condition must not duplicate sends.
3. `.wwebjs_auth/` is persistent operational state and must not be deleted casually.
4. Authentication-expired paths must stop retries and return exit code `21`.
5. `whatsapp-config.json` owns runtime behavior; recipient or mode changes belong in config, not code.
6. The bridge must stay short-lived and leave no stray browser processes behind.

## Architecture Overview

| Layer | File | Responsibility |
| --- | --- | --- |
| Trigger | `Trigger_Automation.vbs` | Preserve `ExecId` and call the bridge |
| BAT bridge | `RunWhatsApp.bat` | Validate runtime, route args, preserve exit code |
| Node.js sender | `sendWhatsApp.js` | Load config, restore session, validate state, send message |
| Config | `whatsapp-config.json` | Recipients, paths, retry policy, mode flags |
| Session state | `.wwebjs_auth/` | LocalAuth persisted session |
| Delivery state | `whatsapp-state.json` | Duplicate-prevention and execution records |

## Exit Codes

| Code | Meaning |
| --- | --- |
| `0` | Success or feature disabled |
| `11` | Attachment missing |
| `20` | Final failure after all attempts |
| `21` | Re-authentication required |
| `22` | Invalid configuration |
| `99` | Unexpected fatal failure |

## Repo-Specific Constraints

- Concurrency detection must be based on the absolute path of `sendWhatsApp.js`, not a generic `node.exe` process match.
- `.wwebjs_auth/` is preserved by retention policy because it is critical session state.
- The bridge must keep the same `ExecId` received from the caller.
- Idempotency should rely on stable business inputs plus channel identity, not only on a timestamped `ExecId`.

## Validation

1. Test bootstrap logging and confirm diagnostics exist even when initialization fails early.
2. Validate attachment existence before attempting send.
3. Force an auth-expired scenario and confirm the bridge returns `21` without endless retries.
4. Rerun the same business condition and confirm the state file prevents duplicates.
5. Confirm the process exits cleanly without leaving background browser state active.

## Troubleshooting

| Symptom | Root Cause | Action |
| --- | --- | --- |
| Bridge fails before normal log starts | Failure occurs before runtime initialization | Inspect bootstrap diagnostics first |
| Exit code `21` repeats | Session expired or corrupted | Re-run pairing intentionally and rebuild session state cleanly |
| Duplicate sends | Missing or unstable idempotency key | Rework the state key around stable business data |
| Wrong Node process is considered concurrent | Detection keyed to generic process name | Match by the absolute path of `sendWhatsApp.js` |

## Pre-Delivery Checklist

- [ ] Bootstrap diagnostics exist before full runtime initialization.
- [ ] Exit codes are explicit and aligned with the shared contract.
- [ ] `.wwebjs_auth/` is treated as persistent state.
- [ ] `whatsapp-state.json` prevents duplicates.
- [ ] `ExecId` is preserved from caller to sender.
- [ ] The bridge exits cleanly after completion.
