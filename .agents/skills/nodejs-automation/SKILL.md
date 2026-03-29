---
name: nodejs-automation
description: "Use when creating, reviewing, or refactoring Node.js automation scripts that require enterprise-grade logging, error handling, retries, and deterministic execution."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise Node.js Automation Standard

## Purpose
Use this skill for Node.js automation scripts that interact with files, external services, browsers, messaging bridges, or orchestration layers. The standard favors deterministic exits, structured diagnostics, bounded retries, and explicit runtime contracts.

## Non-Negotiable Rules
1. Write a bootstrap log before loading heavy dependencies when startup failures must remain diagnosable.
2. Centralize exit codes in an immutable constant map and use them consistently.
3. Model operational failures with a typed error structure such as ManagedError carrying an explicit exitCode.
4. Handle both unhandledRejection and uncaughtException and terminate deterministically.
5. Long-running or retrying flows must have a bounded timeout.

## Runtime Contract
| Concern | Standard |
|---|---|
| Process arguments | Document expected argv positions and defaults |
| Exit behavior | End with process.exit(code) only after cleanup and final log flush |
| Error taxonomy | Distinguish validation, business, infrastructure, and fatal failures |
| Config loading | Validate config shape before main execution |
| State persistence | Use JSON or equivalent durable storage for idempotency and resumability |

## Enterprise Patterns
| Pattern | Guidance |
|---|---|
| Bootstrap logging | Use a minimal sync-safe logger before imports when startup can fail early |
| Retry with backoff | Use maxAttempts and attemptDelayMs; never retry indefinitely |
| Idempotency | Persist an execution identity such as execKey to prevent duplicate side effects |
| Event heartbeat | Log important runtime events for diagnosability |
| Visibility modes | Separate silent, interactive, and diagnostic modes explicitly |

## Exit Code Taxonomy
| Range | Meaning |
|---|---|
| 0 | Success or intentionally disabled execution |
| 1-10 | Validation or prerequisite failures |
| 20-29 | Business or recoverable operational failures |
| 30-49 | Environment or infrastructure failures |
| 99 | Unexpected fatal failure |

## Recommended Error Shape
```js
class ManagedError extends Error {
  constructor(message, exitCode, details) {
    super(message);
    this.name = 'ManagedError';
    this.exitCode = exitCode;
    this.details = details;
  }
}
```

## Troubleshooting
| Symptom | Root Cause | Action |
|---|---|---|
| Script fails before main log initializes | Startup failure before runtime setup | Add or inspect bootstrap logging |
| Duplicate side effects | Missing idempotency persistence | Introduce execKey-based state tracking |
| Infinite retries | Retry policy unbounded | Add maxAttempts and stop conditions |
| Silent termination | Unhandled promise rejection or exception | Add global handlers and explicit exit mapping |

## Pre-Delivery Checklist
- [ ] Bootstrap diagnostics exist where early startup can fail.
- [ ] Exit codes are centralized and documented.
- [ ] Config validation happens before side effects.
- [ ] Retries are bounded and timeboxed.
- [ ] The script exits deterministically on both success and failure.