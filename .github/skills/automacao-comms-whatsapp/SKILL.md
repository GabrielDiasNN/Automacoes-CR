---
name: automacao-comms-whatsapp
description: "Use when implementing, reviewing, or troubleshooting WhatsApp delivery bridges built with Node.js and whatsapp-web.js."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise WhatsApp Delivery Bridge

## Purpose

Use this skill for automation flows that hand off outbound delivery to a WhatsApp bridge. The standard emphasizes authentication resilience, idempotent sends, structured exit codes, bootstrap logging, and controlled recovery from session failures.

## Architecture Overview

| Layer               | File                     | Responsibility                                                   |
| ------------------- | ------------------------ | ---------------------------------------------------------------- |
| Trigger layer (VBS) | `Trigger_Automation.vbs` | Pass ExecId and launch the BAT bridge                            |
| BAT orchestration   | `RunWhatsApp.bat`        | Validate Node.js, choose execution mode, pass `--exec-id`        |
| Node.js bridge      | `sendWhatsApp.js`        | Load config, initialize client, manage retries, send messages    |
| Configuration       | `whatsapp-config.json`   | Recipients, paths, retry policy, feature flags                   |
| Session store       | `.wwebjs_auth/`          | Persisted authenticated client state (whatsapp-web.js LocalAuth) |
| State store         | `whatsapp-state.json`    | ExecId-based idempotency and sent execution records              |

## Non-Negotiable Rules

1. The bridge must log before `require()` calls so bootstrap failures are diagnosable.
2. Delivery must be idempotent. The same ExecId must not result in more than one message sent.
3. Session assets (`.wwebjs_auth/`) must not be deleted casually. Re-authentication is an operational event, not a default recovery step.
4. Exit codes must be explicit and documented so upstream VBS or BAT layers can react deterministically.
5. Retry logic must stop immediately on authentication-expired scenarios and return exit code 21.
6. `whatsapp-config.json` controls all runtime behavior. Recipient updates must change config, not code.

## Execution Flow

```text
Trigger layer
      -> BAT orchestrator (ExecId + mode)
            -> Node.js bridge
                  -> Load config
                  -> Restore session
                  -> Validate idempotency state
                  -> Send message and optional attachment
```

## Exit Codes

| Code | Meaning                                      |
| ---- | -------------------------------------------- |
| 0    | Success or feature disabled by configuration |
| 11   | Attachment missing                           |
| 20   | Final failure after all attempts             |
| 21   | Re-authentication required                   |
| 22   | Invalid configuration                        |
| 99   | Unexpected fatal failure                     |

## Enterprise Patterns

| Pattern          | Standard                                                                              |
| ---------------- | ------------------------------------------------------------------------------------- |
| Bootstrap log    | Write a minimal synchronous log before require or client initialization               |
| Idempotency      | Compute an execKey from stable execution inputs and persist it in a state file        |
| Retry            | Use bounded attempts with delay and stop immediately on auth-expired paths            |
| Visibility mode  | Support silent and visible modes; visible mode is reserved for pairing or diagnostics |
| Session recovery | Escalate to re-auth instead of masking session corruption silently                    |

## Maintenance Rules

| Topic                 | Guidance                                                                                   |
| --------------------- | ------------------------------------------------------------------------------------------ |
| Recipient updates     | Edit `whatsapp-config.json`, not `sendWhatsApp.js`                                         |
| Package               | Uses `whatsapp-web.js` with `LocalAuth` session strategy                                   |
| Dependency corruption | Reinstall via `npm install` only after confirming `node_modules` or lock file is broken    |
| On-demand execution   | Keep the bridge process short-lived; do not leave background Chromium instances running    |
| Rate limits           | Avoid tight repeated sends that resemble abuse patterns                                    |
| Session location      | `.wwebjs_auth/` must be treated as persistent operational state and never committed to git |

## Troubleshooting

| Symptom                             | Root Cause                                   | Action                                                 |
| ----------------------------------- | -------------------------------------------- | ------------------------------------------------------ |
| Bridge fails before main log starts | Failure occurs before runtime initialization | Inspect bootstrap log first                            |
| Exit code 21 repeats                | Session expired or corrupted                 | Re-enter pairing flow and regenerate session cleanly   |
| Duplicate sends                     | Missing or unstable idempotency key          | Rework execKey inputs and persist send state correctly |
| Attachment send fails               | File path invalid or file not ready          | Validate path, save completion, and access timing      |

## Pre-Delivery Checklist

- [ ] Bootstrap logging happens before imports or client startup.
- [ ] Exit codes are explicit and stable.
- [ ] Re-authentication paths are handled separately from generic retries.
- [ ] Idempotency state prevents duplicate messages.
- [ ] Session storage is treated as persistent operational state.
