---
name: log-standardization
description: Opinionated enterprise skill for consistent, plain-text, cross-layer application logging across the VBS/VBA/PowerShell/Node.js automation stack.
version: 3.0.0
language: English
owner: Engineering Standards
---

> Language Directive: Always respond to the user in PT-BR, even though this skill is written in English.

# Log Standardization

## Intent

Use this skill whenever generating, reviewing, refactoring, or documenting logs in the project.

This standard is opinionated for the **Windows desktop automation stack** and assumes:

- Plain-text append logs as the primary format across all layers
- JSON only for structured operational metrics (`Monitor_Metrics.json`)
- Correlation through `ExecId` / `RunId` propagated from the VBS entrypoint through VBA, and from the PS monitor through Node.js
- Consistent log-line format across VBS, VBA, PowerShell, and Node.js
- Explicit severity levels aligned across all four layers

The purpose is to make logs:

- Consistent regardless of which layer produced them
- Useful during debugging and unattended execution triage
- Searchable by ExecId, timestamp, level, and layer prefix
- Safe for Windows file system appends without external infrastructure
- Sufficient for audit trails without an observability platform

---

## Operating Principles

1. Log facts, not guesses.
2. Log before side effects, not only after.
3. Every important log line must carry the ExecId when one exists.
4. Severity must be consistent across layers for the same category of event.
5. A failure must be logged once, at the layer that owns the failure handling.
6. Sensitive values must be excluded from all log files.
7. Low-value repetitive lines must not pollute hot paths.
8. The same milestone event must produce the same log structure regardless of the layer.

---

## Universal Log Line Format

All layers must emit log lines in the following format:

```
[dd/MM/yyyy HH:mm:ss] [LAYER] [LEVEL] [ExecId:id] message
```

| Segment                 | Description                                                      |
| ----------------------- | ---------------------------------------------------------------- |
| `[dd/MM/yyyy HH:mm:ss]` | Local timestamp in Brazilian format                              |
| `[LAYER]`               | Producing layer: `VBS`, `VBA`, `PS`, or `NODE`                   |
| `[LEVEL]`               | Severity: `DEBUG`, `INFO`, `WARN`, `ERROR`, or `FATAL`           |
| `[ExecId:id]`           | Correlation identifier. Omit only when unavailable at bootstrap. |
| `message`               | Concise factual description of what happened                     |

### Canonical examples

```
[30/03/2026 08:00:01] [VBS]  [INFO]  [ExecId:20260330_080001] Iniciando Receitas Bloqueadas
[30/03/2026 08:00:03] [VBA]  [INFO]  [ExecId:20260330_080001] Atualizacao Oracle concluida | linhas=42
[30/03/2026 08:00:05] [VBA]  [ERROR] [ExecId:20260330_080001] Falha ao enviar email | Err=438
[30/03/2026 08:00:06] [VBS]  [ERROR] [ExecId:20260330_080001] Macro encerrada com falha | ExitCode=1
[30/03/2026 08:01:00] [NODE] [INFO]  [ExecId:20260330_080001] Mensagem enviada | destino=5511XXXXXX
```

---

## Layer Prefixes

| Layer              | Prefix | Log file                                                 |
| ------------------ | ------ | -------------------------------------------------------- |
| VBS entrypoint     | `VBS`  | `Module/Logs/Execution.log`                              |
| VBA macros         | `VBA`  | `Module/Logs/log_yyyy-mm-dd.log`                         |
| PowerShell monitor | `PS`   | `Logs/yyyy-MM_Monitor.log`                               |
| Node.js bridge     | `NODE` | Configured via `paths.logFile` in `whatsapp-config.json` |

---

## Severity Model

Use exactly these levels across all layers:

| Level   | When to use                                            |
| ------- | ------------------------------------------------------ |
| `DEBUG` | Verbose technical diagnostics for local debugging only |
| `INFO`  | Normal expected flow events and business milestones    |
| `WARN`  | Degraded or unusual state that did not cause failure   |
| `ERROR` | Operation failed, requires investigation               |
| `FATAL` | Unrecoverable state, process must stop                 |

**Opinionated rules:**

- Validation errors caused by expected business conditions are `WARN`, not `ERROR`
- Retries are `WARN` on intermediate attempts and `ERROR` only on final failure
- A single failure must be logged once at the ownership boundary, not cascaded across layers
- Heartbeat and polling loops must not emit `INFO` on every tick unless state changed

**PowerShell exception:** The PS monitor uses `ERRO` (not `ERROR`) by established project convention. All other layers use `ERROR`.

---

## ExecId / RunId — Correlation Contract

ExecId is the single correlation mechanism across all layers.

### Generation rules

| Layer              | Rule                                                                                         |
| ------------------ | -------------------------------------------------------------------------------------------- |
| VBS entrypoint     | `GerarExecId()` produces `yyyyMMdd_HHmmss` at the very start of the script                   |
| PowerShell monitor | Generates its own ExecId per triggered task and passes it via process argument               |
| VBA                | Receives from VBS via `modLogging.DefinirRunId()`; generates internally only if not provided |
| Node.js            | Receives via `--exec-id` CLI argument from the BAT orchestrator                              |

### Propagation chain

```
VBS (GerarExecId)
  --> VBA (DefinirRunId from VBS-passed value)
        --> Email/Outlook (ExecId in subject line when traceability matters)
  --> BAT (receives ExecId as argument)
        --> Node.js (receives via --exec-id)
```

### Rules

- Never generate a new ExecId mid-flow unless intentionally restarting after failure.
- Always log ExecId on the first line each layer produces.
- Include ExecId in all error lines and the final outcome line.

---

## Log File Naming Conventions

| Layer              | Pattern                                              | Rotation                          |
| ------------------ | ---------------------------------------------------- | --------------------------------- |
| VBS                | `Execution.log`                                      | Single file, append-only          |
| VBA                | `log_yyyy-mm-dd.log`                                 | Daily; max `LOG_MAX_BACKUPS` kept |
| PowerShell monitor | `yyyy-MM_Monitor.log`                                | Monthly                           |
| Node.js            | Defined in `whatsapp-config.json` at `paths.logFile` | Bounded manually                  |

---

## Lifecycle Logging Requirements

Every automation flow must emit log lines at these milestones:

| Milestone                        | Level   | Layer                   |
| -------------------------------- | ------- | ----------------------- |
| Process started                  | `INFO`  | VBS or PS               |
| Excel workbook opened            | `INFO`  | VBS                     |
| Macro execution started          | `INFO`  | VBA                     |
| Key business step started        | `INFO`  | VBA                     |
| Key business step completed      | `INFO`  | VBA with elapsed time   |
| Validation failure (expected)    | `WARN`  | VBA or Node             |
| Send attempt (email or WhatsApp) | `INFO`  | VBA or Node             |
| Send succeeded                   | `INFO`  | VBA or Node             |
| Retry scheduled                  | `WARN`  | Node                    |
| Fatal failure                    | `ERROR` | VBS, VBA, or Node       |
| Process completed                | `INFO`  | VBS or PS with ExitCode |

---

## Layer-Specific Implementation Standards

### VBS

```vbscript
WriteLog "INFO",  "Processo iniciado | ExecId=" & execId
WriteLog "INFO",  "Workbook aberto"
WriteLog "INFO",  "Macro executada com sucesso"
WriteLog "ERROR", "Falha critica | ExitCode=" & exitCode
```

### VBA (via modLogging)

```vb
GravarLogEx "Oracle atualizado | linhas=" & lngLinhas, LOG_INFO
GravarLogEx "Falha ao enviar email | Err=" & Err.Number & " | " & Err.Description, LOG_ERROR
LogStepStart "RefreshOracle"
' ... work ...
LogStepEnd "sucesso"
```

### PowerShell (via Write-Log)

```powershell
Write-Log "Monitor iniciado | versao=3.6" -Type "INFO"
Write-Log "Tarefa suprimida por overlap | task=$taskName" -Type "WARN"
Write-Log "Falha critica no ciclo principal | $_" -Type "ERRO"
```

### Node.js

```js
// Before any require() — bootstrap log
_bootstrapLog("=== BOOTSTRAP NODE INICIADO ===");
_bootstrapLog(`ExecId=${execId} | pid=${process.pid}`);

// After initialization
log("INFO", `Mensagem enviada | destino=[MASKED]`);
log("WARN", `Tentativa ${attempt} de ${maxAttempts} falhou`);
log("ERROR", `Falha final | exitCode=20`);
```

---

## Structured Metrics (JSON exception)

The only JSON output in this project is `Monitor_Metrics.json`, maintained by the PowerShell monitor.

This file is an operational snapshot, not a log stream. Expected fields:

- `generatedAt`: ISO 8601 timestamp
- `monitorVersion`: string version
- `runningTasks`: integer count
- `cumulative`: lifetime counter set
- `window.startedAt`, `window.endedAt`, `window.counters`: rolling window metrics

Do not convert operational log files to JSON. Plain text is the standard for all log files.

---

## Privacy and Security Rules

Never include in any log file:

- Passwords, credentials, or secrets
- API keys or access tokens
- Session cookies or auth headers
- Personal document numbers in full
- Private cryptographic material
- Full phone numbers or email addresses of recipients

Mask or redact when necessary:

- Phone: `5511XXXXXX`
- Token: `[REDACTED]`
- Document: `***.123.456-**`

---

## Error Logging Contract

When an operation fails:

1. Log once at the layer that owns the error handling.
2. Include ExecId, error code, description, and the step or component that failed.
3. Do not re-log the same failure in every upstream layer.

```
[30/03/2026 08:00:05] [VBA] [ERROR] [ExecId:20260330_080001] Falha em ClsOutlookAdapter.Enviar | Err=287 | Operacao cancelada
```

---

## Noise Reduction Rules

Avoid:

- Logging on every loop tick when no state changes
- Repeating the same value across multiple layers
- Verbose object dumps in production logs
- DEBUG-level output enabled in scheduled runs

Preferred approach:

- Log state transitions, not steady states
- Summarize loop results in one line after completion
- Emit `WARN` with attempt number for retries

---

## Review Policy

Reject log lines or log implementations that:

- Do not carry ExecId where one should exist
- Use non-standard level names
- Leak passwords, tokens, or personal data
- Duplicate the same failure across multiple layers
- Produce excessive noise in tight loops
- Use non-standard layer prefix or timestamp format

Approve when logs:

- Follow the universal format
- Carry appropriate level for the event
- Include ExecId where available
- Are free of sensitive data
- Log failures once at the ownership boundary

---

## Pre-Delivery Checklist

- [ ] All log lines follow: `[dd/MM/yyyy HH:mm:ss] [LAYER] [LEVEL] [ExecId:id] message`.
- [ ] ExecId is propagated from VBS/PS through VBA and Node.js.
- [ ] Severity levels are consistent with the model above.
- [ ] Log files follow the layer-specific naming conventions.
- [ ] Required lifecycle milestones are logged.
- [ ] No sensitive data appears in any log file.
- [ ] Failures are logged once at the ownership boundary.
- [ ] JSON output is limited to `Monitor_Metrics.json` only.
