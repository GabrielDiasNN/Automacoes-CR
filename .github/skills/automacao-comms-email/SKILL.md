---
name: automacao-comms-email
description: "Use when implementing, reviewing, or troubleshooting Outlook email delivery from VBA automation flows that compose HTML, attach workbook outputs, and run unattended."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise Outlook Email Automation

## Purpose

Use this skill for VBA-driven Outlook delivery. It covers composition, attachment validation, HTML body assembly, delivery mode, and COM cleanup for automations that send email after workbook processing.

## When to Use

- Building or refactoring Outlook delivery from VBA.
- Reviewing `ClsOutlookAdapter`, `ClsEmailComposerService`, or equivalent routines.
- Troubleshooting attachments, signatures, drafts, or corporate prompt behavior.

## Do Not Use When

- The work is only about HTML/CSS markup structure; use `vba-html-vba` and `vba-css-vba`.
- The question is about Node.js or WhatsApp delivery.
- The flow is still unstable at the Excel/VBA core and not ready for outbound delivery.

## Related Skills

- `automacao-standard`: end-to-end flow and manual-first gating.
- `vba-html-vba`: HTML structure and escaping inside VBA.
- `vba-css-vba`: Outlook-safe CSS and inline styling.
- `vba-enterprise-vbe-safe`: adapter/service layering and ASCII-safe internals.
- `log-standardization`: delivery logs and ownership of send failures.

## Non-Negotiable Rules

1. Create Outlook through `CreateObject("Outlook.Application")` unless the project already owns a shared instance pattern.
2. Validate recipients, subject, and attachment readiness before composing the final send.
3. Never attach a file before confirming existence and size greater than zero.
4. Use `.Send` for unattended automation and `.Display` only for explicit interactive workflows.
5. Release `MailItem` and `Outlook.Application` on every exit path.

## Delivery Contract

| Concern | Standard |
| --- | --- |
| Composition | Use a composer service or dedicated builder for `HTMLBody` |
| Attachment validation | Check path existence and non-zero file size |
| Signature preservation | Prepend or append custom HTML without blindly discarding the Outlook signature when it matters |
| Error handling | Catch send failures in the owning adapter and log meaningful context |
| Audit copy | Use BCC only when the process truly requires an audit recipient |

## Recommended Flow

1. Save or export workbook outputs first.
2. Validate recipients, subject, reference date, and attachment path.
3. Build the HTML body from validated data.
4. Create the `MailItem`, assign fields, and add attachments only after validation succeeds.
5. Send, log the outcome, and release COM objects.

## Repo-Specific Constraints

- If Outlook `.Send` blocks with errors such as `0x800A9C68`, treat it as a runtime Outlook or corporate-policy issue, not as a VBA compile problem.
- HTML email composition should stay modular through composer services and the VBA HTML/CSS skills rather than growing inside adapter code.
- External PT-BR accents may be preserved in subject or body when the destination supports them; internal VBA identifiers and helper text remain governed by ASCII-safe rules.

## Validation

1. Confirm the attachment exists and is complete before the mail is created.
2. Test the body with realistic data and verify the signature or wrapper behavior.
3. Validate one failure path and confirm the adapter logs the send error with context.
4. Confirm all COM references are released after both success and failure.

## Troubleshooting

| Symptom | Root Cause | Action |
| --- | --- | --- |
| Outlook object creation fails | Outlook unavailable, no profile, or COM issue | Validate installation, profile, and runtime context |
| Security prompt appears or send blocks | Corporate policy or untrusted programmatic access | Resolve through approved trust configuration, not ad hoc bypasses |
| Attachment not found | Workbook output not saved yet or wrong path | Save first and validate with filesystem checks |
| Message stays in drafts | `.Display` used or send interrupted by an exception | Review delivery mode and adapter error handling |

## Pre-Delivery Checklist

- [ ] Recipients, subject, and attachments are validated.
- [ ] HTML body is composed by a dedicated service or builder.
- [ ] Attachment files exist and have non-zero size.
- [ ] `.Send` is used for unattended delivery.
- [ ] COM objects are released on every exit path.
- [ ] Outlook runtime failures are logged at the adapter boundary.
