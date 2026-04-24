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
- Inter-process communication between Node.js, Python, and PowerShell must use structured JSON via stdio.
- Responses must always be in PT-BR.

## Repo-Specific Constraints
- PowerShell code must handle Windows Execution Policies safely.
- Python scripts must declare local virtual environment dependencies in requirements.txt.

## Related Skills
- python-oracle-migration
- log-standardization

## Troubleshooting
- **OUTLOOK.EXE zombie processes**: Ensure Marshal.ReleaseComObject is called in the finally block.
- **IPC Failures**: Verify if JSON is being correctly printed to stdout and logs to stderr.

## Validation
Review the IPC implementation to ensure no temporary files are used for data exchange between runtimes.

## Pre-Delivery Checklist
- [ ] COM objects explicitly released?
- [ ] IPC using structured JSON?
- [ ] No hardcoded credentials?
- [ ] All explanations in PT-BR?
