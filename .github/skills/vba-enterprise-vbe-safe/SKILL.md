---
name: vba-enterprise-vbe-safe
description: "Use when generating, reviewing, or refactoring VBA code that must stay safe inside the VBE, ASCII-safe in internal surfaces, and maintainable through class-based orchestration."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise VBA VBE Safe Standard

## Purpose

Use this skill for VBA code that must remain maintainable inside the VBE, survive export and import workflows, and evolve incrementally without breaking workbook-backed automations. The focus is architecture, readability, ASCII-safe internal text, and practical refactoring.

## When to Use

- Refactoring large `mod*` procedures into classes.
- Reviewing architecture smells in workbook automation.
- Standardizing naming, layering, logging surfaces, and error handling in VBA.

## Do Not Use When

- The main task is workbook synchronization, import tooling, or compile gate discipline; use `vba-governance-sync`.
- The question is only about HTML or CSS output.
- The task is strictly about PowerShell or monitor behavior.

## Related Skills

- `vba-governance-sync`: import/export workflow, compile-before-save, `VB_Name`, and drift prevention.
- `automacao-standard`: end-to-end VBS to Excel/VBA orchestration.
- `log-standardization`: canonical log-line structure and ownership model.
- `automacao-comms-email`: Outlook delivery through adapters and composer services.

## Non-Negotiable Rules

1. Standard modules are entry points and helpers, not workflow engines.
2. Multi-step flows must be orchestrated by classes.
3. Business logic belongs in services; infrastructure belongs in adapters or repositories.
4. Internal code-facing text must be ASCII-safe.
5. `Option Explicit` is mandatory.
6. Refactor incrementally; preserve macro entrypoints and workbook contracts while moving logic.

## Architecture Standard

| Layer | Responsibility |
| --- | --- |
| `mod*` | Public macros, event wrappers, thin compatibility entrypoints |
| `Cls*Orchestrator` | End-to-end coordination of a use case |
| `Cls*Service` | Validation, transformation, calculation, and business decisions |
| `Cls*Adapter` / `Cls*Repository` | Oracle, Outlook, worksheets, files, and other infrastructure |
| `ClsAppContext` | Composition root for shared dependencies |

If a process validates data, loads external inputs, updates workbook state, and notifies users, it is already large enough for orchestrator plus services.

## Naming and Text Rules

| Topic | Rule |
| --- | --- |
| Standard modules | Use the `mod*` prefix |
| Classes | Use the `Cls*` prefix |
| Internal identifiers | Never use accents |
| Comments and internal messages | Keep ASCII-safe |
| External PT-BR text | Preserve accents only when the destination is known to support them |

Examples of safe internal normalization: `Informacao`, `Configuracao`, `Operacao`, `Validacao`, `Usuario`.

## Readability and Error Handling

- Keep procedures small and top-to-bottom readable.
- Default members to `Private`.
- Centralize logging and configuration access.
- Use `On Error GoTo TratarErro` with predictable cleanup labels such as `Finalizar:`.
- Avoid duplicated bootstrap code and repeated magic strings.

## Dependency Management

Use `ClsAppContext` or an equivalent composition root when dependencies repeat across procedures.

Preferred dependency flow:

- `mod*` -> orchestrators or thin helpers
- `Cls*Orchestrator` -> services, adapters, repositories, logger
- `Cls*Service` -> repositories or adapters only when needed
- `Cls*Domain` -> no infrastructure concerns

Avoid hidden shared state and circular references.

## Repo-Specific Constraints

- VBA logging should align with the repository log contract and receive `ExecId` through `modLogging.DefinirRunId` when the outer layer provides it.
- Internal strings that feed `Logs/Montagem.log` must remain ASCII-safe to avoid mojibake in the unified UTF-8 log path.
- Keep wrappers stable while migrating legacy procedures into orchestrators and services.
- Component naming limits, `VB_Name`, compile-before-save, and workbook-lock rules are governed by `vba-governance-sync`.

## Validation

1. Confirm that public macros and workbook callbacks still exist after refactoring.
2. Confirm that multi-step workflows moved out of large `mod*` procedures.
3. Verify that comments, identifiers, and internal strings remain ASCII-safe.
4. Confirm that logging and error handling are centralized instead of duplicated.
5. When `.bas` or `.cls` files changed, follow the sync contract before finishing.

## Troubleshooting

| Symptom | Root Cause | Action |
| --- | --- | --- |
| `mod*` file keeps growing and owns the whole workflow | Orchestration never moved to classes | Extract an orchestrator and keep the module as the entrypoint |
| Same setup code appears in many procedures | Dependencies constructed ad hoc | Introduce or extend `ClsAppContext` |
| Accented or corrupted identifiers break maintenance | Internal text not normalized | Rename to ASCII-safe identifiers and comments |
| Outlook or Oracle logic is mixed with decisions | Layering boundary missing | Move infrastructure into adapters and keep decisions in services |

## Pre-Delivery Checklist

- [ ] Standard modules are thin.
- [ ] Multi-step workflows use orchestrators.
- [ ] Business logic and infrastructure are separated.
- [ ] Internal identifiers, comments, and messages are ASCII-safe.
- [ ] Logging and error handling are centralized.
- [ ] Workbook-backed changes follow the sync and compile contract.
