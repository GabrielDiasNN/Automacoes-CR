---
name: bat-automation
description: "Use when creating, reviewing, or refactoring Windows BAT automation scripts that orchestrate external processes and require enterprise-grade logging and exit-code discipline."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise BAT Automation Standard

## Purpose
Use this skill for Windows batch files that orchestrate external tools, launch Node.js or PowerShell scripts, validate prerequisites, and preserve operational exit codes. The standard focuses on deterministic control flow, safe variable expansion, and bootstrap-level traceability.

## Non-Negotiable Rules
1. Start with setlocal and enable delayed expansion when values will be read inside IF or FOR blocks.
2. Write bootstrap logging as early as possible, before branching or expensive setup.
3. Document exit codes in the file header and preserve them across subroutine calls.
4. Separate prerequisite validation from business execution.
5. Use call :label modularization for non-trivial scripts.

## Runtime Contract
| Concern | Standard |
|---|---|
| Variable expansion | Use !VAR! inside blocks when delayed expansion is enabled |
| Error propagation | Capture and re-emit exit codes explicitly |
| Logging | Append timestamped records and avoid failing on log-write contention |
| Modularity | Split validation, execution, and recovery into labeled subroutines |
| External tools | Validate executable, paths, and working directory before launch |

## Enterprise Patterns
| Pattern | Guidance |
|---|---|
| Bootstrap log | Emit a first diagnostic line before any meaningful logic |
| Delayed expansion | Use setlocal EnableDelayedExpansion and distinguish %ERRORLEVEL% from !ERRORLEVEL! |
| Prerequisite gate | Implement a dedicated :validar_pre_requisitos routine |
| Recovery flow | Use explicit branching for retry, reauth, or fallback modes |
| Log resilience | Redirect log-write failures with 2>nul when the log must never break the script |

## Exit Code Taxonomy
| Range | Meaning |
|---|---|
| 0 | Success |
| 1-9 | Validation or prerequisite failure |
| 20-29 | Business or runtime flow escalation |
| 30-49 | Launch or environment failure |
| 99 | Unexpected fatal failure |

## Troubleshooting
| Symptom | Root Cause | Action |
|---|---|---|
| Variable value appears stale inside IF block | Percent expansion evaluated too early | Enable delayed expansion and switch to !VAR! |
| Exit code is lost after subroutine | Code not preserved after call | Capture errorlevel immediately and return it explicitly |
| Script fails silently | No bootstrap or branch logging | Add early append-only logging |
| External tool launches in wrong folder | Missing cd /d or path validation | Set working directory explicitly before launch |

## Pre-Delivery Checklist
- [ ] Delayed expansion is enabled when block evaluation requires it.
- [ ] Prerequisite validation is isolated in its own routine.
- [ ] Exit codes are documented and preserved.
- [ ] Bootstrap logging happens before main branching.
- [ ] External process launch paths and working directory are validated.