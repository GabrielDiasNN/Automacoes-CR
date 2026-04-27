---
name: enterprise-local-automation-stack
description: Use when orchestrating local Windows automation stacks using PowerShell, Python, Node.js, and Outlook Desktop COM integration.
---

# Skill: Enterprise Local Automation Guardian

## Purpose
This skill governs the architecture, development, and integration of local desktop automation pipelines spanning PowerShell, Python, and Node.js with local Outlook Desktop integrations.

## When to Use
Use when:
- Orchestrating tasks locally using Node.js as the runtime coordinator or UI backend.
- Processing data, automating local files, or executing complex logic using Python.
- Interacting with the Windows OS, Active Directory, or legacy local systems via PowerShell.
- Manipulating local Outlook Desktop clients via COM objects.

## Do Not Use When
- The automation is intended to run as a background Windows Service (Session 0) without user interaction.
- Outlook Desktop is not installed or available in the execution environment.

## Non-Negotiable Rules
- Python and PowerShell scripts interacting with Outlook MUST connect to an existing Outlook instance if available.
- Explicit cleanup logic to release COM objects is mandatory.
- Inter-process communication between Python and PowerShell MUST use the **Secure File-Payload Protocol** (e.g., writing to `.payload_ExecId.json` or `.data_ExecId.json`) instead of pure `stdio`. This bypasses PowerShell 5.1 buffer corruption on large JSON payloads.
- Responses must always be in PT-BR.

## Repo-Specific Constraints
- PowerShell code must handle Windows Execution Policies safely.
- Python scripts must declare local virtual environment dependencies in requirements.txt.

## Related Skills
- python-oracle-migration
- log-standardization

## Troubleshooting
- **OUTLOOK.EXE zombie processes**: Ensure Marshal.ReleaseComObject is called in the finally block.
- **IPC Failures**: If using `stdio`, check for `Unexpected UTF-8 BOM` or `Expecting value` errors. If these occur, migrate to the **Secure File-Payload Protocol**.

## Validation
Review the IPC implementation to ensure temporary files (`.data_*.json`, `.payload_*.json`) are used for large data exchange between runtimes, and that they are securely deleted in the `finally` block or after successful processing.

## Pre-Delivery Checklist
- [ ] COM objects explicitly released?
- [ ] IPC using Secure File-Payload for large JSON?
- [ ] Temporary IPC files are cleaned up reliably?
- [ ] No hardcoded credentials?
- [ ] All explanations in PT-BR?
