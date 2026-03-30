---
name: powershell-automation
description: "Use when creating, reviewing, or refactoring PowerShell automation scripts that require enterprise-grade scheduling, logging, encoding control, and process safety."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise PowerShell Automation Standard

## Purpose
Use this skill for PowerShell automation scripts, especially monitors, schedulers, service-like loops, and orchestrators. The standard emphasizes explicit failure behavior, UTF-8-safe file handling, singleton control, structured logging, and configuration validation.

## Non-Negotiable Rules
1. Set $ErrorActionPreference = "Stop" unless there is a documented reason to downgrade a specific command.
2. Never rely on default encoding for file output; wrap writes in explicit UTF-8 helper functions.
3. Use a mutex or equivalent guard when the script must run as a singleton.
4. Validate configuration before entering the main execution loop.
5. Log operational state transitions, not only exceptions.

## Runtime Contract
| Concern | Standard |
|---|---|
| Error behavior | Fail fast by default |
| Encoding | Explicit UTF-8 for read and write paths |
| Process singleton | Named mutex when duplicate instances are unsafe |
| State | Keep runtime state in $script: scope when shared across functions |
| Logs | Timestamped INFO, WARN, and ERROR records |

## Enterprise Patterns
| Pattern | Guidance |
|---|---|
| Structured logging | Implement a single Write-Log function with levels and rotation strategy |
| Hot reload | Detect config file changes and reload safely between execution cycles |
| Validation first | Use a Test-Configuration function and refuse invalid input |
| Emergency diagnostics | Write early fatal failures to a separate startup error file |
| Heartbeat | Emit periodic health messages for long-running monitors |

## Encoding Standard
| Rule | Guidance |
|---|---|
| File writes | Prefer explicit UTF-8 helper functions over Out-File defaults |
| Config files | Preserve predictable encoding across save operations |
| Console output | Treat console encoding separately from file encoding |

## Troubleshooting
| Symptom | Root Cause | Action |
|---|---|---|
| Script behaves differently by host | Host-specific defaults or encoding behavior | Make encoding and preference variables explicit |
| Duplicate monitor instances | Missing singleton guard | Add named mutex protection |
| Config change not picked up | Reload logic too weak or hash not updated | Rework change detection and validation boundary |
| Errors disappear into non-terminating warnings | ErrorActionPreference too permissive | Fail fast and selectively catch expected cases |

## Pre-Delivery Checklist
- [ ] ErrorActionPreference is explicit.
- [ ] File encoding is explicit for all writes.
- [ ] Singleton protection exists when required.
- [ ] Configuration is validated before execution.
- [ ] Logs capture startup, heartbeat, transitions, and fatal failures.