---
name: ai-native-development-standard
description: Use when establishing or reviewing mandatory standards for creating AI-sustainable code and documentation to ensure high-fidelity context for LLMs.
---

# SKILL: AI-Native Development & Documentation Standard

## Purpose
This skill defines the structural and metadata requirements to make the repository "AI-Sustainable". It ensures that any LLM (Gemini, GPT, Claude) can immediately grasp the architectural intent, business rules, and security boundaries of any file it reads.

## When to Use
- Always, when creating new Python, PowerShell, VBA, or Node.js scripts.
- When reviewing existing scripts for AI-Native compliance.

## Do Not Use When
- This standard applies to all executable automation code. Do not skip it.

## Contextual Headers (Mandatory)

Every source file must begin with a standardized header block.

### Python Headers
```python
# {
#   "version": "1.0.0",
#   "skill": "python-oracle-migration",
#   "contract": "ipc-stdio",
#   "description": "Short business purpose here",
#   "reliability": "Base64-Bridge-Logs"
# }
```

### PowerShell Headers
```powershell
<#
.SYNOPSIS
    Short description.
.NOTES
    Version: 1.0.0
    Skill: powershell-automation
    Contract: hybrid-fetch-logic
#>
```

## AI-Readable Documentation Rules

1.  **Business Logic First:** Documentation should explain *Why* a rule exists (e.g., "Oracle policy restricts Python connections") before explaining *How* it was implemented.
2.  **Explicit Mapping:** When data flows between languages (VBA -> Python), the documentation must explicitly name the columns or JSON keys used.
3.  **The "Context Anchor" File:** Every module folder must contain a CONTEXT.md file summarizing the "Cognitive Map" of that automation for a new model reading it for the first time.
4.  **Traceability DNA:** Always include the ExecId in external side-effects (SQL comments, Email metadata, File properties).

## Non-Negotiable Rules
- Never use ambiguous variable names (e.g., 	emp, data). Use df_raw_divergences, json_ipc_payload.
- Every "Hack" or "Workaround" (like using Excel for fetch) must be tagged with [ARCH-WORKAROUND] followed by the reason.

## Validation
- Confirm that every script has a valid contextual header.
- Confirm that `CONTEXT.md` exists and is accurate for every module.
- Verify that ASCII-Safe core rules are followed in source files.

## Related Skills
- `log-standardization`: Defines how logs are generated.
- `automation-execution-contract`: Defines how executions are tracked.

## Repo-Specific Constraints
- PowerShell 5.1 buffer issues dictate the use of Secure File-Payload IPC instead of pure Stdio for large JSON payloads.
- Base64 Bridge Protocol MUST be used for logs to preserve PT-BR accents.

## Troubleshooting
- If a model hallucinates context, check if `CONTEXT.md` is up-to-date and accurate.
- If PowerShell drops accents, ensure the Base64 Bridge Protocol is active in `Lib-Logging`.

## Pre-Delivery Checklist
- [ ] Contextual header is present in the source file.
- [ ] `CONTEXT.md` is updated if new business logic is added.
- [ ] Explicit mapping is used for cross-language data flows.
- [ ] Hacks are tagged with `[ARCH-WORKAROUND]`.
