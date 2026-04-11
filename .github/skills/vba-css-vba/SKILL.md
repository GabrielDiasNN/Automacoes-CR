---
name: vba-css-vba
description: "Use when defining, reviewing, or refactoring CSS used by VBA-generated HTML, especially Outlook email content where inline styling and constrained compatibility are mandatory."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise VBA CSS Compatibility Standard

## Purpose

Use this skill when CSS is produced or embedded by VBA routines. It governs the lowest reliable styling subset for Outlook and other Office-hosted renderers that do not behave like modern browsers.

## When to Use

- Styling HTML built in VBA for `MailItem.HTMLBody`.
- Reviewing inline CSS, table layouts, spacing, and typography in Outlook-targeted output.
- Converting modern CSS ideas into email-safe equivalents.

## Do Not Use When

- The HTML is generated outside VBA for dashboards or report pages; use `nodejs-html-css`.
- The question is about HTML structure or escaping rather than CSS behavior; use `vba-html-vba`.

## Related Skills

- `vba-html-vba`: HTML structure and content assembly in VBA.
- `automacao-comms-email`: Outlook delivery ownership and attachment/send behavior.
- `nodejs-html-css`: modern HTML/CSS outside the Outlook/VBA surface.

## Non-Negotiable Rules

1. Treat Outlook desktop rendering as constrained.
2. Inline critical visual properties.
3. Use table-based layout for essential structure.
4. Do not depend on flex, grid, or unsupported selectors for business-critical content.
5. Keep typography, spacing, and colors explicit.

## Rendering Contract

| Concern | Standard |
| --- | --- |
| CSS location | Critical styles inline on each element |
| Layout model | Table-based email layout |
| Spacing | Explicit padding, widths, and table cell spacing |
| Typography | Fallback-safe font stacks and explicit sizes |
| Colors | Explicit foreground and background colors |

## Repo-Specific Constraints

- This skill exists for Outlook-targeted VBA output. Do not import assumptions from the Node.js HTML/CSS stack.
- Keep styling decisions simple enough to survive Outlook desktop rendering without relying on runtime assets or advanced browser behavior.

## Validation

1. Verify that critical visual rules are inline.
2. Confirm the layout still reads correctly without non-essential enhancements.
3. Validate wrapper widths, padding, and fallback fonts explicitly.
4. Check at least one representative Outlook render path before considering the styling stable.

## Troubleshooting

| Symptom | Root Cause | Action |
| --- | --- | --- |
| CSS ignored in Outlook | Unsupported selector or property | Replace it with inline, table-safe styling |
| Unexpected spacing | Client-specific box model behavior | Use explicit cell padding and width rules |
| Font inconsistency | Primary font unavailable | Add robust fallback stack |
| Header style breaks | Too much inherited complexity | Flatten styles at the element level |

## Pre-Delivery Checklist

- [ ] Critical styles are inline.
- [ ] Core structure is table-based.
- [ ] Typography and spacing are explicit.
- [ ] Styling does not depend on flex, grid, or external assets.
- [ ] The design still reads correctly under degraded rendering.
