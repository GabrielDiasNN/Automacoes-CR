---
name: automacoes-hub-implementation
description: Use when planning, refactoring, hardening, and validating the Automacoes Hub project involving PowerShell, Excel/VBA, Oracle, Outlook COM, and Node.js/WhatsApp.
---

# Automacoes Hub Implementation

## Purpose
Use when planning, refactoring, hardening, and validating the Automacoes Hub project involving PowerShell, Excel/VBA, Oracle, Outlook COM, and Node.js/WhatsApp, preserving operational compatibility and prioritizing short deliveries executed by agents.

## When to Use
- Implementing new automation features or modules.
- Refactoring legacy VBA/Power Query logic for better maintainability.
- Hardening PowerShell orchestration scripts with better error handling.
- Validating changes against repository standards and operational contracts.
- Planning incremental migrations from legacy runtimes to modern stacks.

## Do Not Use When
- Creating entirely unrelated automation projects outside this hub's architecture.
- Performing one-off manual tasks that do not require code or script changes.
- Proposing massive, "big-bang" architectural rewrites without an incremental path.

## Project Context
This repository is an automation hub based on a Monitor-Trigger-Action model.
- **MonitorAutomacoes.ps1**: Central scheduler and monitor.
- **TriggerAutomation.vbs**: Legacy entry point for some automations.
- **Excel/VBA + Power Query**: Core business logic execution.
- **Oracle**: Main data source.
- **Outlook COM**: Email delivery service.
- **Node.js**: WhatsApp bridge (AUTO and PAIRING modes).
- **ExecId**: Correlation key across the entire execution flow.

## Non-Negotiable Rules
- Preserve the current architecture unless a controlled migration is requested.
- Do not remove existing entry points without providing compatibility.
- Maintain ExecId propagation across all layers.
- Reuse existing helper modules and patterns (e.g., Lib-Logging, Lib-Email).
- Every change must be reversible and include a validation checklist.
- Prefer adapters and wrappers over wholesale rewrites.

## Task Priorities
- **P0**: Timeout protection, Excel/Workbook lock handling, ExecId propagation, WhatsApp safety, Watchdog/Heartbeat reliability, Governance validation.
- **P1**: Runbooks, JSONL structured logs, retention improvements, troubleshooting helpers, documentation sync.
- **P2**: Cosmetic cleanup, markdown polish, non-critical internal consistency.

## Engineering Patterns
- **Command Pattern**: For individual automation units.
- **Adapter/Wrapper**: For bridging legacy VBA behavior.
- **Strangler Fig**: For gradual migration of legacy components.
- **Chain of Responsibility**: For staged execution validation.

## Logging & Operational Rules
- Treat logs as an operational contract; maintain human-readable logs.
- Preserve mutex/lock behavior and idempotency protections.
- Ensure exit codes remain meaningful (e.g., 0=OK, 7=Blocked, 23=Cooldown, 40=Concurrent).

## Validation
### Validation Rules
1. Static review and governance checks.
2. Dry run / Smoke test.
3. Controlled execution in a safe environment.
4. Final operational review.

### Definition of Done
A task is done only if the scope is controlled, backward compatibility is preserved, the operational contract is intact, validation evidence exists, and no unnecessary files were touched.

## Repo-Specific Constraints
- Environment: Windows-based automation.
- Dependencies: Microsoft Office (Excel/Outlook COM), Node.js, PowerShell 5.1/7.
- Governance: Strict adherence to PT-BR naming for VBA and approved verbs for PowerShell.

## Troubleshooting
- **Excel Hangs**: Check for orphan processes and use `Stop-Process -Name Excel` in cleanup scripts.
- **WhatsApp Lock**: Verify `whatsapp-lock.json` and session status.
- **VBA Drift**: Run `Test-VbaDrift.ps1` to ensure workbook code matches repository files.

## Related Skills
- `powershell-automation`: For deep dives into orchestration scripts.
- `vba-enterprise-vbe-safe`: For safe handling of Excel/VBA code.
- `nodejs-automation`: For maintaining the WhatsApp bridge.
- `log-standardization`: For details on structured logging contracts.

## Pre-Delivery Checklist
- [ ] Backward compatibility verified.
- [ ] ExecId propagation tested.
- [ ] No breaking changes to the operational dashboard.
- [ ] Governance scripts (`Tools/Test-*.ps1`) pass without errors.
- [ ] Rollback path is clear and documented.
