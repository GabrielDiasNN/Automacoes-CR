---
name: vba-enterprise-vbe-safe
description: "Use when generating, reviewing, or refactoring enterprise-grade VBA code that must remain safe inside the VBE, maintainable over time, and organized through class-based orchestration with ASCII-safe internal code conventions."
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Enterprise VBA VBE Safe Standard

## Purpose

Use this skill whenever VBA code is generated, reviewed, refactored, or documented for projects that run inside the Visual Basic Editor and require long-term maintainability.

This skill has five goals:

1. Preserve compatibility with the VBE editing surface.
2. Avoid mojibake, broken identifiers, and text corruption in ANSI-sensitive workflows.
3. Enforce enterprise architecture and class-based orchestration.
4. Improve readability, maintainability, and supportability.
5. Enable safe incremental refactoring of legacy VBA projects.

## Core Philosophy

- If text belongs to the VBE/internal VBA surface, default to ASCII-safe content.
- If logic belongs to an application flow, default to class orchestration.
- If responsibilities are mixed, split them.
- If dependency construction is repeated, centralize it.
- If the refactor is risky, refactor incrementally.

## Core Rules

- Standard modules are entry points and helpers, not workflow engines.
- Classes orchestrate use cases.
- Services hold business logic.
- Adapters and repositories isolate infrastructure.
- Application context centralizes dependencies.
- Internal code-facing text must be ASCII-safe.
- External user-facing PT-BR text may preserve accents when the destination supports it.

## Architectural Standard

### Standard Modules (`mod*`)

Use standard modules only for:

- Public macros
- Excel/VBA runtime entry points
- Ribbon callbacks
- Thin event wrappers
- Stateless helper functions
- Transitional compatibility wrappers during refactoring

Avoid in standard modules:

- Full business workflows
- Shared mutable global state
- Dependency construction spread across procedures
- Mixed business + infrastructure logic
- Large multi-step orchestration

### Application Context (`ClsAppContext`)

Use one central application context class when the project has shared dependencies.

Responsibilities:

- Bootstrap application state
- Load configuration
- Expose logger
- Expose repositories, adapters, and services
- Cache reusable objects when appropriate
- Act as the composition root

### Orchestrators (`Cls*Orchestrator`)

Use orchestrators to coordinate use cases end to end.

Responsibilities:

- Receive process input
- Sequence the execution steps
- Coordinate validation, data loading, business actions, persistence, notifications, and logging
- Own the readable business flow

### Services (`Cls*Service`)

Use services for business rules.

Responsibilities:

- Validation logic
- Calculation logic
- Transformation logic
- Message composition
- Decision logic
- Rules independent from infrastructure details

### Adapters / Repositories (`Cls*Adapter`, `Cls*Repository`)

Use for:

- Oracle access
- Outlook automation
- Worksheet I/O
- File system operations
- External APIs
- Config persistence

Adapters and repositories must not contain business decisions.

### Domain / Model Classes (`Cls*Model`, `Cls*Dto`, `Cls*Entity`)

Use domain/model classes when:

- Many fields travel together
- Signatures are becoming noisy
- Data meaning should be explicit
- You want safer handoff between layers

## Mandatory Orchestration Rule

If a process has more than one meaningful step, it must be orchestrated by a class.

Examples:

- Validate input -> query Oracle -> build dashboard output -> log result
- Load NF rows -> validate business rules -> create email -> send Outlook notification -> write processing status
- Read config -> refresh data -> publish status -> handle failures

Do not leave these flows spread across large `mod*` procedures.

## Dependency Management Rule

### Preferred Pattern

Dependencies should be:

- Created in `ClsAppContext`
- Exposed via properties or factory methods
- Passed into orchestrators explicitly when useful

Avoid:

- Recreating dependencies across many procedures
- `Public` mutable objects in modules
- Copy-pasted bootstrap code
- Hidden state shared implicitly

## Layering Rules

Allowed dependency flow:

- `mod*` -> orchestrators / helpers
- `Cls*Orchestrator` -> services / adapters / repositories / logger
- `Cls*Service` -> repositories/adapters only when needed
- `Cls*Adapter` -> external system only
- `Cls*Domain` -> no UI or infrastructure concerns

Avoid circular references.

## Naming Convention

Use ASCII-safe names only.

### Prefixes

- `mod` for standard modules
- `Cls` for classes
- `m_` for private fields
- `c_` for constants when useful
- `p_` for parameters only when it improves readability

### Naming Guidelines

- Use explicit names
- Avoid vague verbs like `Rodar`, `ExecutarTudo`, `ProcessaTudo`
- Prefer technical consistency in code naming
- Keep project/business output in PT-BR when applicable
- Never use accented identifiers
- Avoid mojibake and corrupted naming

### Good Examples

- `modMain`
- `modEntryDashboard`
- `ClsAppContext`
- `ClsDashboardOrchestrator`
- `ClsEmailService`
- `ClsOracleAdapter`
- `ClsExecucaoResultado`

## Readability Standard

All generated or refactored code must be operationally readable.

### Required Rules

- `Option Explicit` everywhere
- `Private` by default
- Small focused procedures
- Guard clauses when they simplify flow
- No deep nesting when avoidable
- No duplicated bootstrap logic
- No repeated magic strings
- Technical comments only
- ASCII-safe comments only
- Keep top-to-bottom flow obvious

### Procedure Design Sequence

A healthy procedure usually reads like this:

1. Validate
2. Load
3. Execute
4. Persist
5. Notify
6. Log
7. Exit cleanly

## Error Handling Standard

All public flows need a consistent error strategy.

### Minimum Pattern

- `On Error GoTo TratarErro`
- Context-aware error logging
- Controlled failure output
- No silent errors
- No ad hoc fragmented handling across the codebase

### Recommended Labels

- `TratarErro:`
- `Finalizar:`

Keep labels ASCII-safe.

## Logging Standard

Logging must be centralized and predictable.

### Log at minimum

- process start
- important checkpoints
- warnings
- failures
- final status

### Avoid

- random `Debug.Print` in many places
- mixed logging styles
- duplicated formatting logic

### Suggested Logger Surface

- `Info`
- `Warn`
- `Error`
- `StepStart`
- `StepEnd`

## Configuration Standard

Configuration must be centralized.

Prefer:

- `ClsConfigRepository`
- `ClsSettingsRepository`
- `ClsAppContext` loading configuration once

Typical configuration:

- worksheet names
- sheet ranges
- recipients
- Oracle settings
- folder paths
- flags
- retry parameters

## Mandatory ASCII Normalization

Apply ASCII normalization to:

- identifiers
- module names
- class names
- comments
- MsgBox strings
- Debug.Print strings
- internal logging strings
- internal status messages
- corrupted legacy text

## Safe vs Unsafe Contexts

| Context                            | Keep accents?              | Rule                                      |
| ---------------------------------- | -------------------------- | ----------------------------------------- |
| Identifiers                        | No                         | Always ASCII-safe                         |
| Comments                           | No                         | Keep ASCII-safe                           |
| MsgBox / Debug.Print               | No                         | Keep ASCII-safe                           |
| Internal log strings               | No                         | Keep ASCII-safe                           |
| Outlook Subject                    | Yes, if external and safe  | Preserve PT-BR if destination supports it |
| Outlook HTMLBody                   | Yes, if external           | Preserve PT-BR if safe                    |
| SQL / JSON / HTML / external files | Yes, if target supports it | Preserve fidelity only when safe          |
| Unknown destination                | No                         | Default to ASCII-safe                     |

## Corrupted Text Recovery

Normalize broken text when found.

Examples:

- `Informacao`
- `Configuracao`
- `Operacao`
- `Validacao`
- `Usuario`

Never preserve mojibake in delivered VBA.

## Example Project Layout

Use this logical layout when proposing or refactoring a VBA project:

```text
VBA Project
├── modMain.bas
├── modEntryDashboard.bas
├── modEntryNotificacao.bas
├── modUtil.bas
├── modAnsiSafe.bas
├── ClsAppContext.cls
├── ClsDashboardOrchestrator.cls
├── ClsDeclaracaoOrchestrator.cls
├── ClsNotificacaoNfOrchestrator.cls
├── ClsDashboardService.cls
├── ClsEmailService.cls
├── ClsValidationService.cls
├── ClsOracleAdapter.cls
├── ClsOutlookAdapter.cls
├── ClsWorksheetRepository.cls
├── ClsConfigRepository.cls
├── ClsNotaFiscal.cls
├── ClsEmailPayload.cls
└── ClsExecucaoResultado.cls
```

Even though VBE does not provide real folders, naming must reflect logical grouping.

## Code Templates

### Template: `modMain`

```vb
Option Explicit

Public Sub ExecutarDashboard()
    On Error GoTo TratarErro

    Dim appContext As ClsAppContext
    Dim orchestrator As ClsDashboardOrchestrator

    Set appContext = New ClsAppContext
    appContext.Initialize

    Set orchestrator = New ClsDashboardOrchestrator
    orchestrator.Setup appContext
    orchestrator.Run

Finalizar:
    Set orchestrator = Nothing
    Set appContext = Nothing
    Exit Sub

TratarErro:
    If Not appContext Is Nothing Then
        appContext.Logger.Error "Falha em ExecutarDashboard", Err.Number, Err.Description
    End If

    MsgBox "Falha ao executar dashboard.", vbExclamation
    Resume Finalizar
End Sub
```

### Template: `ClsAppContext`

```vb
Option Explicit

Private m_logger As ClsLogger
Private m_oracleAdapter As ClsOracleAdapter
Private m_outlookAdapter As ClsOutlookAdapter
Private m_configRepository As ClsConfigRepository
Private m_blnReady As Boolean

Public Sub Initialize()
    If m_blnReady Then Exit Sub
    Set m_logger = New ClsLogger
    Set m_configRepository = New ClsConfigRepository
    Set m_oracleAdapter = New ClsOracleAdapter
    Set m_outlookAdapter = New ClsOutlookAdapter
    m_blnReady = True
End Sub

Public Property Get Logger() As ClsLogger
    Set Logger = m_logger
End Property

Public Property Get OracleAdapter() As ClsOracleAdapter
    Set OracleAdapter = m_oracleAdapter
End Property

Public Property Get OutlookAdapter() As ClsOutlookAdapter
    Set OutlookAdapter = m_outlookAdapter
End Property

Public Property Get ConfigRepository() As ClsConfigRepository
    Set ConfigRepository = m_configRepository
End Property

Private Sub Class_Terminate()
    Set m_logger           = Nothing
    Set m_configRepository = Nothing
    Set m_oracleAdapter    = Nothing
    Set m_outlookAdapter   = Nothing
End Sub
```

### Template: `ClsDashboardOrchestrator`

```vb
Option Explicit

Private m_appContext As ClsAppContext
Private m_dashboardService As ClsDashboardService

Public Sub Setup(ByVal appContext As ClsAppContext)
    Set m_appContext = appContext
    Set m_dashboardService = New ClsDashboardService
    m_dashboardService.Setup m_appContext
End Sub

Public Sub Run()
    On Error GoTo TratarErro

    m_appContext.Logger.StepStart "Dashboard.Run"

    m_dashboardService.RefreshData
    m_dashboardService.UpdateIndicators

    m_appContext.Logger.StepEnd "Dashboard.Run"
    Exit Sub

TratarErro:
    m_appContext.Logger.Error "Falha em Dashboard.Run", Err.Number, Err.Description
    Err.Raise Err.Number, "ClsDashboardOrchestrator.Run", Err.Description
End Sub
```

### Template: `ClsDashboardService`

```vb
Option Explicit

Private m_appContext As ClsAppContext

Public Sub Setup(ByVal appContext As ClsAppContext)
    Set m_appContext = appContext
End Sub

Public Sub RefreshData()
    Dim rawData As Variant
    rawData = m_appContext.OracleAdapter.LoadDashboardData

    m_appContext.Logger.Info "Dados do dashboard carregados"
End Sub

Public Sub UpdateIndicators()
    m_appContext.Logger.Info "Indicadores atualizados"
End Sub
```

### Template: `ClsOracleAdapter`

```vb
Option Explicit

Public Function LoadDashboardData() As Variant
    On Error GoTo TratarErro

    Dim result As Variant

    ' Implementar acesso Oracle aqui
    LoadDashboardData = result
    Exit Function

TratarErro:
    Err.Raise Err.Number, "ClsOracleAdapter.LoadDashboardData", Err.Description
End Function
```

## Refactoring Playbook

### Step 1. Identify Entry Points

Find:

- public macros
- worksheet events
- workbook events
- button callbacks
- Ribbon callbacks

Do not break these first.

### Step 2. Preserve Behavior

Before changing structure:

- keep macro names stable
- keep external triggers stable
- keep worksheet contract stable

Refactor architecture without breaking usage.

### Step 3. Move Workflow Out of `mod*`

Take large procedures and split:

- entry point remains in module
- flow goes to orchestrator class

### Step 4. Extract Business Logic

Move:

- validation rules
- calculations
- composition logic
- business decisions

into service classes.

### Step 5. Extract Infrastructure

Move:

- Oracle code
- Outlook code
- worksheet read/write
- file operations

into adapters or repositories.

### Step 6. Introduce `ClsAppContext`

When dependencies repeat, centralize them:

- logger
- adapters
- repositories
- config access

### Step 7. Normalize Naming

Rename:

- vague modules
- generic procedures
- corrupted text
- accented identifiers

Keep names explicit and ASCII-safe.

### Step 8. Reduce Public Surface

Make members `Private` unless a public contract is truly needed.

### Step 9. Standardize Error Handling

Unify:

- top-level handler
- logger usage
- user-facing fallback message
- label names

### Step 10. Remove Dead Code Last

Only after the new flow is stable:

- remove obsolete wrappers
- remove duplicate logic
- remove temporary compatibility code

## Architecture Smells To Flag

Flag these as maintainability issues:

- modules that do everything
- globals shared across many files
- repeated setup logic
- duplicate error blocks
- repeated Outlook or Oracle code
- process methods too long to scan comfortably
- infrastructure mixed with business decisions
- corrupted internal text
- accented identifiers
- hidden state changes

## Review Rules

When reviewing VBA:

- identify architecture smells
- propose extraction order
- suggest orchestrators where flow is procedural
- suggest services where business logic is mixed
- suggest adapters where external access is embedded
- preserve practical migration paths
- avoid big-bang rewrite bias

## Delivery Rules

When delivering output with this skill:

- explain in PT-BR
- keep the skill body in English
- keep internal VBE-facing content ASCII-safe
- preserve external PT-BR accents only where safe
- prioritize maintainability over clever shortcuts
- prefer practical and incremental recommendations

## Expected Agent Behavior

1. Remove accents from internal identifiers and VBE-facing strings.
2. Preserve accents only for clearly external user-facing text.
3. Default to ASCII when there is doubt.
4. Refactor multi-step flows into orchestrators.
5. Keep standard modules thin.
6. Centralize dependencies in `ClsAppContext` when appropriate.
7. Separate business logic from infrastructure.
8. Flag architecture smells clearly.
9. Prefer incremental refactoring.
10. Never deliver VBA identifiers with accents.

## Pre-Delivery Checklist

- [ ] No identifiers contain accents.
- [ ] Comments are ASCII-safe.
- [ ] Internal messages are ASCII-safe.
- [ ] Standard modules are thin.
- [ ] Multi-step processes use orchestrator classes.
- [ ] Shared dependencies are centralized.
- [ ] Business logic is separated from adapters/repositories.
- [ ] Error handling is consistent.
- [ ] Logging is centralized.
- [ ] Naming is explicit and maintainable.
- [ ] Delivered code is safe to paste into the VBE.
