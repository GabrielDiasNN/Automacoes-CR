---
name: vba-html-vba
description: "Use when creating, reviewing, or refactoring HTML content generated inside VBA automation, especially for Outlook MailItem.HTMLBody, HTML fragments in worksheets, or rich notification templates."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise VBA HTML Composition Standard

## Purpose

Use this skill for HTML markup authored or assembled from VBA. The standard focuses on deterministic rendering in Outlook and Office surfaces, safe variable interpolation, and consistent delivery in unattended automation.

> **Related skill:** Apply `vba-css-vba` together with this skill for all CSS and inline styling decisions in the generated HTML. This skill covers structure and content; `vba-css-vba` covers styling constraints and Outlook rendering safety.

## Non-Negotiable Rules

1. Build HTML from validated data only; never concatenate unchecked user input into markup.
2. Escape dynamic text for HTML entities before insertion into body content.
3. Prefer table-based structure for email-compatible layouts.
4. Keep generated HTML deterministic: same inputs must produce same output.
5. Separate message data from template assembly so business logic does not live inside concatenated strings.

## Runtime Contract

| Concern                    | Standard                                                                  |
| -------------------------- | ------------------------------------------------------------------------- |
| Input validation           | Validate null, empty, and format constraints before HTML assembly         |
| Data escaping              | Encode &, <, >, ", and ' for dynamic text fields                          |
| Template source            | Use explicit template blocks or functions, not scattered inline fragments |
| Date and number formatting | Format explicitly with locale-safe rules before interpolation             |
| Delivery target            | Assume Outlook/Word rendering constraints for email outputs               |

## Enterprise Patterns

| Pattern                | Guidance                                                                 |
| ---------------------- | ------------------------------------------------------------------------ |
| Tokenized templates    | Use placeholders like {{Cliente}} and replace from a validated map       |
| Structural wrappers    | Keep a stable outer wrapper with width, typography, and spacing defaults |
| Section builders       | Split header, summary, table, and footer into dedicated functions        |
| Deterministic ordering | Sort rows before rendering when source order can vary                    |
| Fallback text          | Provide clear plain language fallback for missing optional data          |

## HTML Safety Baseline

| Topic            | Rule                                                                             |
| ---------------- | -------------------------------------------------------------------------------- |
| Inline scripts   | Never use script tags in VBA-generated email HTML                                |
| External assets  | Avoid remote CSS and remote JS dependencies                                      |
| Embedded links   | Validate protocol and target domain before rendering anchors                     |
| Attribute values | Quote all dynamic attribute values                                               |
| Unicode and ANSI | Keep user-facing text readable, but preserve VBA/VBE internal safety constraints |

## Suggested Assembly Flow

1. Validate and normalize source data.
2. Escape dynamic text values.
3. Build deterministic sections (header, content table, footer).
4. Compose final wrapper and inject into MailItem.HTMLBody.
5. Log rendering metadata (template version, row count, execution id).

## Troubleshooting

| Symptom                             | Root Cause                                                    | Action                                                                            |
| ----------------------------------- | ------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Broken characters in generated body | Encoding mismatch between internal VBA text and output target | Normalize internal strings and preserve external user-facing text only where safe |
| Layout shifts across recipients     | Non-email-safe markup assumptions                             | Rework structure to table-based email layout                                      |
| Links are malformed                 | Dynamic URL not validated                                     | Validate URL schema and domain before interpolation                               |
| Missing values in HTML              | Null or empty source fields                                   | Add required-field validation and explicit fallback text                          |

## Pre-Delivery Checklist

- [ ] Dynamic content is escaped before interpolation.
- [ ] HTML layout is email-safe and table-oriented where needed.
- [ ] Templates are modular and not scattered in ad hoc concatenations.
- [ ] Required fields are validated before rendering starts.
- [ ] Output generation is deterministic for the same input set.
- [ ] CSS and inline styles follow the `vba-css-vba` Outlook compatibility constraints.
