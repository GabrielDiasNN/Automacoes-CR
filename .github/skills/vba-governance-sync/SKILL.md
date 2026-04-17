---
name: vba-governance-sync
description: "Use when importing, exporting, syncing, compiling, or validating VBA modules and classes in workbook-backed automations that must remain safe, canonical, and PT-BR governance compliant."
user-invocable: false
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise VBA Governance and Sync Contract

## Purpose

Use this skill for the operational side of VBA maintenance: import/export workflows, compile gate discipline, workbook lock handling, naming constraints, and governance checks that keep `.bas`, `.cls`, `Audit/vba`, and `.xlsm` aligned.

## When to Use

- Editing `.bas` or `.cls` files that must be synchronized back into a workbook.
- Reviewing tooling such as `ImportarModuloVba.ps1`, `ImportarClassesVba.ps1`, `SyncVbaModulos.ps1`, or export scripts.
- Hardening compile-before-save or read-only detection.
- Applying PT-BR governance, ASCII-safe rules, and drift prevention.

## Do Not Use When

- The task is only about VBA architecture or class responsibilities; use `vba-enterprise-vbe-safe`.
- The change is purely about HTML or CSS rendering.
- The workflow does not touch workbook-backed VBA source synchronization.

## Related Skills

- `vba-enterprise-vbe-safe`: class orchestration, module boundaries, and ASCII-safe coding conventions.
- `automation-runtime-safety`: lock handling, fail-fast behavior, and cleanup discipline.
- `log-standardization`: logging contract for VBA execution and compile diagnostics.

## Non-Negotiable Rules

1. If a `.bas` or `.cls` file changes, synchronize it back into the owning `.xlsm` before closing the task.
2. Abort immediately when `Workbook.ReadOnly = True`; never pretend the import succeeded.
3. Compile the real workbook after import and before save. If compile fails, do not save.
4. Read `Attribute VB_Name` from source files instead of trusting the file name.
5. `.cls` imports must preserve CRLF line endings and use `VBComponents.Import()` for reliability.
6. Never import multiple components into the same workbook in parallel.
7. Avoid creating prefixed wrappers (e.g., `ClsRB*`, `ClsRE*`) for shared components; use the canonical versions from `_Shared\VBA\` directly.

## Canonical Naming and Type Rules

| Topic | Rule |
| --- | --- |
| Standard modules | Must use the `mod*` pattern |
| Classes | Must use `Cls*` naming and stay within the VBE 31-character component limit |
| VB name source | `Attribute VB_Name` is the source of truth |
| Line endings | Normalize `.cls` files to CRLF before import |
| Type integrity | Validate that imported classes remain `Type=2`, not downgraded to modules |

## Sync Workflow

1. Edit the exported `.bas` or `.cls` source.
2. Validate naming, `VB_Name`, and line endings.
3. Import the component into the real workbook using the correct tool and parameter names.
4. Compile the workbook before save.
5. Save only on successful compile.
6. Export canonical VBA back into `Audit/vba` when the workbook state changed.

## Tooling Contract

| Tool | Required parameters |
| --- | --- |
| `Tools/ImportarModuloVba.ps1` | `-XlsmPath -BasPath -ModName` |
| `Tools/ImportarClassesVba.ps1` | `-XlsmPath -ClassPath -ClassName` |
| `Tools/ExportarVbaModulos.ps1` | Use after workbook sync to refresh canonical exported state |

Do not invent alternative parameter names in documentation or automation scripts.

## Drift and Governance Rules

- `Audit/vba` is the canonical exported snapshot used by drift tooling; `Audit/xlsm` is not the same thing.
- After editing VBA, validate governance and refresh exported sources when the workbook changed.
- PT-BR governance checks may flag non-ASCII in `.bas` or `.cls`; keep internal identifiers and comments ASCII-safe.
- Treat false positives from editor diagnostics carefully, but do not skip real compile or governance validation.

## Repo-Specific Constraints

- Long class names beyond 31 characters can turn into generic `Classe1` or `Classe2` during import and break the project.
- LF-only `.cls` files may be imported as standard modules; normalize to CRLF first.
- Outlook `.Send` runtime blocking is not a compile failure; differentiate prompt/policy runtime errors from VBE syntax issues.
- The user preference in this repository is explicit: when a VBA file changes, import it into the corresponding workbook before finishing.

## Validation

1. Confirm `Workbook.ReadOnly` is false before import.
2. Confirm the imported component name matches `Attribute VB_Name` and respects the 31-character limit.
3. Compile the workbook before saving.
4. Refresh exported modules when workbook state changed.
5. Run the PT-BR governance check after VBA edits.

## Troubleshooting

| Symptom | Root Cause | Action |
| --- | --- | --- |
| Import appears to succeed but workbook does not change | Workbook opened read-only | Abort early and require the workbook to be closed or unlocked |
| Class imported as module | LF-only line endings or wrong import path | Normalize to CRLF and use `VBComponents.Import()` |
| Workbook saves broken code | Compile gate skipped | Compile before save and discard invalid state |
| Drift tooling still reports mismatch | `Audit/vba` not refreshed or source not aligned with canonical export | Re-export modules and align text with the canonical snapshot |

## Pre-Delivery Checklist

- [ ] Every changed `.bas` or `.cls` was synchronized back into its workbook.
- [ ] `Attribute VB_Name` was honored.
- [ ] Component names stay within the VBE limit.
- [ ] `.cls` line endings are CRLF and imports use the correct method.
- [ ] **Type integrity validated**: Classes must remain `Type=2` (use `Tools/Test-VbaComponentTypes.ps1`).
- [ ] Compile passed before save.
- [ ] `Audit/vba` was refreshed when needed.
- [ ] PT-BR governance was considered after VBA edits.
