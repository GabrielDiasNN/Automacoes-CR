---
name: nodejs-html-css
description: "Use when creating, reviewing, or refactoring HTML and CSS artifacts outside VBA, especially in Node.js automation flows, dashboards, generated reports, and notification pages requiring enterprise reliability."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise HTML CSS Delivery Standard for Node.js

## Purpose

Use this skill for HTML and CSS delivered outside VBA, including Node.js-generated pages, report views, notification portals, and static artifacts. The standard emphasizes deterministic output, security, maintainability, and operational observability.

## Non-Negotiable Rules

1. Separate data, template structure, and styling concerns.
2. Escape or sanitize all untrusted content before rendering.
3. Version assets explicitly to avoid stale cache behavior.
4. Keep builds and output deterministic across environments.
5. Fail fast on missing templates, missing assets, or invalid render inputs.

## Runtime Contract

| Concern         | Standard                                                           |
| --------------- | ------------------------------------------------------------------ |
| Template engine | Use explicit templating with controlled interpolation boundaries   |
| Input schema    | Validate payload shape before render execution                     |
| Asset strategy  | Use hashed filenames or version query parameters                   |
| Error handling  | Raise typed operational errors with deterministic exit mapping     |
| Logging         | Emit render id, template version, duration, and output destination |

## Enterprise Patterns

| Pattern                 | Guidance                                                           |
| ----------------------- | ------------------------------------------------------------------ |
| Componentized templates | Reuse shared header, content card, and footer partials             |
| Style tokens            | Centralize color, spacing, typography, and border tokens           |
| Accessibility baseline  | Ensure semantic structure, heading order, and contrast targets     |
| Deterministic snapshots | Keep stable fixture inputs for output regression checks            |
| Environment parity      | Keep render output consistent between local and unattended runtime |

## Security and Reliability Baseline

| Topic                 | Rule                                                                 |
| --------------------- | -------------------------------------------------------------------- |
| XSS prevention        | Escape untrusted text and sanitize allowed rich content              |
| CSP readiness         | Prefer architecture compatible with strict content security policies |
| External dependencies | Bound remote fetches with timeout and fallback behavior              |
| Path safety           | Resolve output paths safely and prevent directory traversal          |
| Secret handling       | Never embed credentials in generated HTML or CSS                     |

## Suggested Delivery Flow

1. Validate and normalize render payload.
2. Build view model with explicit defaults.
3. Render template with escaped data.
4. Attach versioned CSS and static assets.
5. Persist output and log metadata for traceability.

## Troubleshooting

| Symptom                               | Root Cause                                            | Action                                                     |
| ------------------------------------- | ----------------------------------------------------- | ---------------------------------------------------------- |
| Different output between environments | Non-deterministic data or locale-dependent formatting | Freeze locale and sort data before rendering               |
| Broken styles in production           | Asset path mismatch or stale cache                    | Enable versioned asset references and verify publish paths |
| Rendering exception at runtime        | Missing template variable or invalid payload          | Enforce schema validation and required field checks        |
| Security scan flags XSS risk          | Unsanitized interpolation                             | Apply escaping and strict HTML sanitization policy         |

## Pre-Delivery Checklist

- [ ] Input payload is schema-validated before rendering.
- [ ] Untrusted text is escaped or sanitized.
- [ ] Assets are versioned and path-safe.
- [ ] Output is deterministic for equal inputs.
- [ ] Render logs include enough metadata for audit and triage.
