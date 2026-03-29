---
name: automacao-comms-whatsapp
description: "Use when implementing, reviewing, or troubleshooting WhatsApp delivery bridges built with Node.js and whatsapp-web.js."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise WhatsApp Delivery Bridge

## Purpose
Use this skill for automation flows that hand off outbound delivery to a WhatsApp bridge. The standard emphasizes authentication resilience, idempotent sends, structured exit codes, bootstrap logging, and controlled recovery from session failures.

## Architecture Overview
| Layer | Responsibility |
|---|---|
| Trigger layer | Pass execution identity and start the bridge |
| BAT orchestration | Validate prerequisites, choose execution mode, preserve exit codes |
| Node.js bridge | Load config, initialize client, manage retries, send messages |
| Session store | Persist authenticated client state |
| State store | Persist idempotency and sent execution records |

## Non-Negotiable Rules
1. The bridge must log before heavy imports or client initialization so bootstrap failures are diagnosable.
2. Delivery must be idempotent. The same execution must not send more than once.
3. Session assets must not be deleted casually. Re-authentication is an operational event, not a default recovery step.
4. Exit codes must be explicit and documented so upstream VBS or BAT layers can react deterministically.
5. Retry logic must stop on authentication-expired scenarios and hand control back to the orchestrator.

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
| Code | Meaning |
|---|---|
| 0 | Success or feature disabled by configuration |
| 11 | Attachment missing |
| 20 | Final failure after all attempts |
| 21 | Re-authentication required |
| 22 | Invalid configuration |
| 99 | Unexpected fatal failure |

## Enterprise Patterns
| Pattern | Standard |
|---|---|
| Bootstrap log | Write a minimal synchronous log before require or client initialization |
| Idempotency | Compute an execKey from stable execution inputs and persist it in a state file |
| Retry | Use bounded attempts with delay and stop immediately on auth-expired paths |
| Visibility mode | Support silent and visible modes; visible mode is reserved for pairing or diagnostics |
| Session recovery | Escalate to re-auth instead of masking session corruption silently |

## Maintenance Rules
| Topic | Guidance |
|---|---|
| Recipient updates | Change configuration, not code |
| Dependency corruption | Reinstall packages only after confirming the lock or install state is broken |
| On-demand execution | Keep the bridge process short-lived; do not leave background clients running without need |
| Rate limits | Avoid tight repeated sends that resemble abuse patterns |

## Troubleshooting
| Symptom | Root Cause | Action |
|---|---|---|
| Bridge fails before main log starts | Failure occurs before runtime initialization | Inspect bootstrap log first |
| Exit code 21 repeats | Session expired or corrupted | Re-enter pairing flow and regenerate session cleanly |
| Duplicate sends | Missing or unstable idempotency key | Rework execKey inputs and persist send state correctly |
| Attachment send fails | File path invalid or file not ready | Validate path, save completion, and access timing |

## Pre-Delivery Checklist
- [ ] Bootstrap logging happens before imports or client startup.
- [ ] Exit codes are explicit and stable.
- [ ] Re-authentication paths are handled separately from generic retries.
- [ ] Idempotency state prevents duplicate messages.
- [ ] Session storage is treated as persistent operational state.
