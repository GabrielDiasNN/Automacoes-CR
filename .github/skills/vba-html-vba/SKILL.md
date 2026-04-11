---
name: vba-html-vba
description: "Use when creating, reviewing, or refactoring HTML generated inside VBA automation, especially Outlook HTMLBody content and rich notification templates assembled from workbook data."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise VBA HTML Composition Standard

## Purpose

Use this skill for HTML authored or assembled from VBA. It governs template structure, escaping, deterministic rendering, and the boundary between workbook data and the final HTML body used in Outlook or other Office-hosted surfaces.

## When to Use

- Building HTML for `MailItem.HTMLBody`.
- Refactoring long string concatenation into template builders or section functions.
- Reviewing whether dynamic data is escaped and rendered deterministically.

## Do Not Use When

- The main question is CSS behavior under Outlook; use `vba-css-vba`.
- The HTML is generated outside VBA for modern dashboards or report pages; use `nodejs-html-css`.
- The task is only about mail send semantics or attachments.

## Related Skills

- `vba-css-vba`: Outlook-safe CSS and inline styling.
- `automacao-comms-email`: Outlook delivery ownership and send behavior.
- `vba-enterprise-vbe-safe`: modular VBA architecture and ASCII-safe internal text.

## Non-Negotiable Rules

1. Build HTML from validated data only.
2. Escape dynamic text before interpolation.
3. Keep templates deterministic for equal inputs.
4. Separate data preparation from template assembly.
5. Assume Outlook or Office-hosted rendering constraints when the target is email.

## Runtime Contract

| Concern | Standard |
| --- | --- |
| Input validation | Validate null, empty, and format constraints before assembly |
| Data escaping | Encode `&`, `<`, `>`, `"`, and `'` for dynamic text |
| Template source | Use explicit builders, blocks, or tokenized templates |
| Formatting | Format dates and numbers before interpolation |
| Ordering | Sort variable data when source order is not stable |

## Repo-Specific Constraints

- Keep HTML composition modular through builders or services such as `ClsEmailComposerService`; do not bury the whole body in adapter code.
- Internal VBA identifiers and helper text remain ASCII-safe even when the final external HTML preserves PT-BR accents.
- When HTML feeds Outlook email, pair this skill with `vba-css-vba` instead of borrowing rules from the modern Node.js HTML stack.

## Validation

1. Confirm required fields are validated before rendering.
2. Confirm dynamic content is escaped.
3. Render the same payload twice and confirm deterministic output.
4. Validate links, attribute values, and any optional fallback text.

## Troubleshooting

| Symptom | Root Cause | Action |
| --- | --- | --- |
| Broken characters in generated body | Internal text not normalized for the target path | Normalize helper text and preserve accents only in safe external output |
| Layout shifts across recipients | Non-email-safe structure | Rework to stable table-oriented markup |
| Links are malformed | Dynamic URL not validated | Validate protocol and domain before interpolation |
| Missing values in HTML | Source fields were null or empty | Add required-field validation and explicit fallback text |

## Pre-Delivery Checklist

- [ ] Dynamic content is escaped before interpolation.
- [ ] Templates are modular and deterministic.
- [ ] Required fields are validated before render starts.
- [ ] Output structure is compatible with the target Office surface.
- [ ] CSS choices are delegated to `vba-css-vba`.
