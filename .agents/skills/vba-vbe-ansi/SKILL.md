---
name: vba-vbe-ansi
description: "Use when generating, reviewing, or refactoring VBA code that must remain safe inside the VBE and compatible with ANSI or Windows-1252 workflows."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# VBA VBE ANSI Safety Standard

## Purpose
Use this skill whenever VBA code may be edited, stored, or displayed inside the Visual Basic Editor. Its role is to prevent mojibake, broken identifiers, and visual corruption caused by the mismatch between Unicode-oriented tooling and the VBE ANSI ecosystem.

## Core Rule
If text belongs to the internal VBA or VBE surface, default to ASCII-safe content.

## Mandatory ASCII Normalization
Apply ASCII normalization to the following categories:

- Variable, constant, function, sub, and module names.
- Form and control names when they are part of the VBA project surface.
- Comments.
- MsgBox and Debug.Print strings.
- Internal status messages that live primarily inside VBA code.

## Safe vs Unsafe Contexts
| Context | Keep accents? | Rule |
|---|---|---|
| Identifiers | No | Always normalize to ASCII |
| Comments | No | Prefer ASCII-safe wording |
| MsgBox and Debug.Print | No | Avoid visual corruption inside VBE |
| MailItem.Subject or HTMLBody | Yes, if external | Preserve user-facing language when the destination supports it |
| JSON, SQL, HTML, external files | Yes, when required | Keep fidelity only if the external system supports the encoding |

## Normalization Examples
| Preferred | Avoid |
|---|---|
| dataUltima | dataÚltima |
| ProcessarRelatorio | ProcessarRelatório |
| ' Verifica se a data e valida | ' Verifica se a data é válida |
| Debug.Print "Erro ao carregar configuracao" | Debug.Print "Erro ao carregar configuração" |
| MsgBox "Operacao concluida com sucesso" | MsgBox "Operação concluída com sucesso" |

## Priority Rule
When there is any doubt between preserving accents and preserving VBE compatibility, choose VBE compatibility.

## Corrupted Text Recovery
If source text already contains mojibake or corrupted characters, normalize it to the ASCII-safe form.

| Corrupted | Safe replacement |
|---|---|
| InformaÃ§Ã£o | Informacao |
| AtenÃ§Ã£o | Atencao |
| UsuÃ¡rio | Usuario |
| ConfiguraÃ§Ã£o | Configuracao |

## Expected Agent Behavior
1. Remove accents from identifiers and internal VBE-facing strings.
2. Preserve accents only for clearly external strings.
3. Default to ASCII if the destination is unclear.
4. Normalize legacy code whenever encoding risk is visible.
5. Never deliver VBA identifiers with accents.

## Troubleshooting
| Symptom | Root Cause | Action |
|---|---|---|
| Text appears corrupted inside VBE | Unicode text passed into ANSI editor surface | Normalize internal strings to ASCII |
| Identifier cannot be trusted across exports/imports | Non-ASCII naming | Rename to ASCII-safe identifiers |
| Message text is readable outside but broken inside editor | Wrong string kept accented in VBE path | Split internal ASCII text from external Unicode content |

## Pre-Delivery Checklist
- [ ] No identifiers contain accents.
- [ ] Comments are ASCII-safe.
- [ ] MsgBox and Debug.Print strings are ASCII-safe unless clearly external.
- [ ] External Unicode strings were preserved only where justified.
- [ ] The code can be pasted into VBE without visual corruption.