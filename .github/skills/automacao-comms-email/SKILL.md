---
name: automacao-comms-email
description: "Use when implementing, reviewing, or troubleshooting Outlook email delivery from VBA automation flows."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise Outlook Email Automation

## Purpose

Use this skill for VBA routines that compose and send email through Microsoft Outlook. The standard focuses on reliable attachment handling, professional HTML composition, deterministic object cleanup, and predictable unattended delivery.

## Architecture Overview

| Component               | Responsibility                                                  |
| ----------------------- | --------------------------------------------------------------- |
| Outlook.Application     | Mail client automation boundary                                 |
| MailItem                | Message composition, recipients, subject, body, and attachments |
| VBA caller              | Validates data, saves workbook outputs, handles failures        |
| ClsEmailComposerService | Composes the HTMLBody from a template with validated data       |
| ClsOutlookAdapter       | Creates the MailItem, assigns fields, attaches files, and sends |
| Templates/Email/        | Shared HTML template fragments used across all automations      |

## Non-Negotiable Rules

1. Always create Outlook through CreateObject("Outlook.Application") unless the project already standardizes a shared instance pattern.
2. Never attach a file before validating both existence and size greater than zero.
3. Use .Send for unattended automation. Use .Display only for explicit interactive workflows.
4. Preserve the user signature by appending to HTMLBody instead of replacing it blindly.
5. Release Outlook COM objects in all exit paths.

## Implementation Standard

| Concern                | Standard                                            |
| ---------------------- | --------------------------------------------------- |
| Outlook object         | CreateObject("Outlook.Application")                 |
| Attachment validation  | Dir() or FileSystemObject plus FileLen > 0          |
| Delivery mode          | .Send for automation                                |
| Signature preservation | Prepend custom HTML to existing HTMLBody            |
| Error handling         | On Error GoTo ErrHandler with deterministic cleanup |

## Recommended Flow

1. Save or export the workbook output before composing the email.
2. Validate recipients, subject, and attachment path.
3. Create the MailItem and assign To, CC, BCC, Subject, and HTMLBody.
4. Attach files only after validation succeeds.
5. Send and release all COM references.

## Professional Patterns

| Pattern           | Rule                                                                                                       |
| ----------------- | ---------------------------------------------------------------------------------------------------------- |
| HTML body         | Use structured HTML for readable, corporate-safe formatting; apply `vba-html-vba` and `vba-css-vba` skills |
| Template source   | Reuse fragments from `Templates/Email/`; avoid hardcoded inline HTML inside adapter code                   |
| Audit trail       | Use BCC only when the process truly requires audit copy behavior                                           |
| Attachment timing | Save workbook outputs before Add attachment is called                                                      |
| Error surface     | Bubble meaningful failure reason back to the caller or log layer                                           |

## Security and Reliability Notes

| Topic                   | Guidance                                                                                                  |
| ----------------------- | --------------------------------------------------------------------------------------------------------- |
| Outlook security prompt | If corporate policy triggers prompts, solve through trusted enterprise configuration, not ad hoc bypasses |
| Draft instead of send   | Check whether .Display replaced .Send or exceptions interrupted the send path                             |
| Broken attachment       | Validate save completion before mail composition                                                          |

## Troubleshooting

| Symptom                       | Root Cause                                    | Action                                                           |
| ----------------------------- | --------------------------------------------- | ---------------------------------------------------------------- |
| Outlook object creation fails | Outlook unavailable or misconfigured          | Validate installation, profile availability, and runtime context |
| Security prompt appears       | Office policy or untrusted automation context | Align with enterprise trust policy or approved add-in strategy   |
| Attachment not found          | Workbook not saved yet or wrong path          | Save first, then validate with Dir or FileSystemObject           |
| Message stays in drafts       | .Display used or send interrupted             | Review delivery method and error handling path                   |

## Pre-Delivery Checklist

- [ ] Recipients, subject, and reference date are validated.
- [ ] Attachment exists and has non-zero size.
- [ ] HTMLBody is composed via `ClsEmailComposerService` using validated data.
- [ ] HTML templates are sourced from `Templates/Email/` when applicable.
- [ ] HTMLBody preserves the Outlook signature when required.
- [ ] The routine uses `.Send` for unattended execution.
- [ ] `MailItem` and `Outlook.Application` are released on all exits.
