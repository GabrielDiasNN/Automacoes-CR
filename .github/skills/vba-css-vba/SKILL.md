---
name: vba-css-vba
description: "Use when defining, reviewing, or refactoring CSS styles used by VBA-generated HTML, especially for Outlook email rendering where CSS support is limited and inline styling is mandatory."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise VBA CSS Compatibility Standard

## Purpose

Use this skill when CSS is produced, transformed, or embedded by VBA routines. The standard ensures that styling remains stable in Outlook and other Office-hosted renderers with limited CSS support.

## Non-Negotiable Rules

1. Treat Outlook desktop rendering as constrained; design for the lowest reliable CSS subset.
2. Prefer inline CSS for critical visual properties.
3. Never rely on unsupported selectors or advanced layout mechanisms for essential content.
4. Keep typography, spacing, and alignment deterministic across clients.
5. Avoid CSS that depends on external loading or runtime execution.

## Rendering Contract

| Concern      | Standard                                                          |
| ------------ | ----------------------------------------------------------------- |
| CSS location | Critical styles inline on each element                            |
| Layout model | Use table-based layout for email bodies                           |
| Spacing      | Prefer cellpadding, fixed paddings, and explicit widths           |
| Typography   | Declare fallback-safe font stacks and explicit sizes              |
| Colors       | Define explicit text and background colors for all key containers |

## Enterprise Patterns

| Pattern                   | Guidance                                                           |
| ------------------------- | ------------------------------------------------------------------ |
| Critical style inlining   | Inline font-family, font-size, color, background-color, text-align |
| Defensive widths          | Set explicit width on wrapper tables and key cells                 |
| Graceful degradation      | Ensure readability if advanced CSS is ignored                      |
| Visual consistency        | Maintain a controlled style token set for headings, labels, values |
| Minimal selector strategy | Prefer class-per-block and avoid deep selector chains              |

## CSS Compatibility Guardrails

| Topic             | Rule                                                       |
| ----------------- | ---------------------------------------------------------- |
| Positioning       | Avoid relying on absolute or fixed positioning             |
| Modern layout     | Do not depend on flex or grid for core structure           |
| Pseudo-elements   | Avoid for business-critical text                           |
| Media queries     | Use only as optional enhancement, not as required behavior |
| Background images | Use only when optional and with acceptable plain fallback  |

## Suggested Styling Flow

1. Define style tokens for colors, spacing, typography, and borders.
2. Map tokens to reusable style fragments.
3. Inline critical styles into generated HTML nodes.
4. Verify readability without non-critical enhancements.
5. Capture rendering notes in logs for future regression checks.

## Troubleshooting

| Symptom                | Root Cause                         | Action                                      |
| ---------------------- | ---------------------------------- | ------------------------------------------- |
| CSS ignored in Outlook | Unsupported selector or property   | Replace with inline, table-safe styling     |
| Unexpected spacing     | Client-specific box model behavior | Use table cell padding and explicit widths  |
| Font inconsistency     | Unavailable primary font           | Add resilient fallback stack                |
| Header style breaks    | Overly complex inheritance         | Flatten style declarations at element level |

## Pre-Delivery Checklist

- [ ] Critical visual rules are inline.
- [ ] Core layout does not depend on flex or grid.
- [ ] Readability is preserved if enhancements are dropped.
- [ ] Typography and spacing are explicit and deterministic.
- [ ] CSS choices match known Outlook compatibility constraints.
