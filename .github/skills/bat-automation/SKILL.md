---
name: bat-automation
description: "Use when creating, reviewing, or refactoring Windows BAT automation scripts that orchestrate external processes and require enterprise-grade logging and exit-code discipline."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise BAT Automation Standard

## Purpose

Use this skill for Windows batch files that orchestrate external tools, launch Node.js or PowerShell scripts, validate prerequisites, and preserve operational exit codes. The standard focuses on deterministic control flow, safe variable expansion, and bootstrap-level traceability.

## Non-Negotiable Rules

1. Start with `setlocal` and enable delayed expansion when values will be read inside IF or FOR blocks.
2. Write bootstrap logging as early as possible, before branching or expensive setup.
3. Document exit codes in the file header and preserve them across subroutine calls.
4. Separate prerequisite validation from business execution.
5. Use `call :label` modularization for non-trivial scripts.
6. Set `chcp 65001` at the top when script output or log content must handle non-ASCII characters.

## Runtime Contract

| Concern            | Standard                                                                      |
| ------------------ | ----------------------------------------------------------------------------- |
| Variable expansion | Use `!VAR!` inside blocks when delayed expansion is enabled                   |
| Error propagation  | Capture and re-emit exit codes explicitly                                     |
| Logging            | Append timestamped records; redirect log-write errors with `2>nul`            |
| Modularity         | Split validation, execution, and recovery into labeled subroutines            |
| External tools     | Validate executable, paths, and working directory before launch               |
| Encoding           | Use `chcp 65001` when non-ASCII content is expected in output or log files    |
| ExecId             | Receive ExecId from the VBS caller and pass it via argument to Node.js bridge |

## Chain Integration Pattern

BAT files that bridge VBS → Node.js must:

1. Receive `ExecId` as `%1` or a named parameter from the VBS entrypoint.
2. Validate Node.js installation and bridge file existence before launch.
3. Pass `--exec-id %EXEC_ID%` to the node process.
4. Capture and return the Node.js exit code to the VBS caller.

```bat
@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

set EXEC_ID=%1
set NODE_SCRIPT=%~dp0sendWhatsApp.js

if not exist "%NODE_SCRIPT%" (
    echo [ERRO] Script Node.js nao encontrado: %NODE_SCRIPT%
    exit /b 30
)

node "%NODE_SCRIPT%" --exec-id !EXEC_ID!
set EXIT_CODE=!ERRORLEVEL!
exit /b !EXIT_CODE!
```

## Enterprise Patterns

| Pattern           | Guidance                                                                           |
| ----------------- | ---------------------------------------------------------------------------------- |
| Bootstrap log     | Emit a first diagnostic line before any meaningful logic                           |
| Delayed expansion | Use setlocal EnableDelayedExpansion and distinguish %ERRORLEVEL% from !ERRORLEVEL! |
| Prerequisite gate | Implement a dedicated :validar_pre_requisitos routine                              |
| Recovery flow     | Use explicit branching for retry, reauth, or fallback modes                        |
| Log resilience    | Redirect log-write failures with 2>nul when the log must never break the script    |

## Exit Code Taxonomy

| Range | Meaning                             |
| ----- | ----------------------------------- |
| 0     | Success                             |
| 1-9   | Validation or prerequisite failure  |
| 20-29 | Business or runtime flow escalation |
| 30-49 | Launch or environment failure       |
| 99    | Unexpected fatal failure            |

## Troubleshooting

| Symptom                                      | Root Cause                            | Action                                                  |
| -------------------------------------------- | ------------------------------------- | ------------------------------------------------------- |
| Variable value appears stale inside IF block | Percent expansion evaluated too early | Enable delayed expansion and switch to !VAR!            |
| Exit code is lost after subroutine           | Code not preserved after call         | Capture errorlevel immediately and return it explicitly |
| Script fails silently                        | No bootstrap or branch logging        | Add early append-only logging                           |
| External tool launches in wrong folder       | Missing cd /d or path validation      | Set working directory explicitly before launch          |

## Pre-Delivery Checklist

- [ ] Delayed expansion is enabled when block evaluation requires it.
- [ ] `chcp 65001` is set when non-ASCII output or log content is expected.
- [ ] Prerequisite validation is isolated in its own routine.
- [ ] Exit codes are documented and preserved.
- [ ] Bootstrap logging happens before main branching.
- [ ] ExecId is passed to downstream Node.js processes via `--exec-id` argument.
- [ ] External process launch paths and working directory are validated.
