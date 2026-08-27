# Padrão de Logging e Observabilidade do Hub de Automações

> **Versão:** v0.2.0 (27/08/2026) | **Status:** PR1 entregue (fundação + piloto ORB-07); gate `Test-LogEventSchema.ps1` em modo `warn`. Ver `CHANGELOG.md` [1.3.48].

### PR1 — o que já está no repositório

| Arquivo | Papel |
|---|---|
| `docs/log-event.schema.json` | Contrato do evento (fonte única dos enums) |
| `lib/Lib-LogEvent.psm1` | Emissores `Write-Hub*`, `Initialize-HubLogContext`, `Resolve-HubTraceId`, `Write-HubForwardedLine` |
| `lib/python/automation_log.py` | `make_logger` com modo estruturado (env `HUB_LOG_STRUCTURED=1`) e modo legado |
| `lib/python/log_masking.py` | `mask_sensitive()` em paridade com `Protect-SensitiveData` |
| `Tools/log_event_validator.py` + `Tools/Test-LogEventSchema.ps1` | Validador (check nº 15 da governança, modo `warn`) |
| `lib/Lib-Retry.psm1` | Encoder `B64:` removido; emite `retry.attempt` |
| `lib/Lib-Logging.psm1` | `Write-AutomacaoLog` roteia p/ evento estruturado; `Exit-AutomationWithCode` emite `execution.end`; `Protect-SensitiveData` exportada |
| `OBs Restricao Branco/{run.ps1,extract_orb.py,format_message.py}` | Piloto migrado ponta a ponta |
| `Dashboard/src/lib/logParser.ts` | Aceita envelope JSON + formato legado |

Define o contrato único de log para **todas** as camadas do Hub: `run.ps1`, scripts Python de domínio (`lib/python`, `*/extract_*.py`, `*/format_message.py`), motor Node (`lib/WhatsApp-Core.js`) e o próprio Orchestrator (`Orchestrator/app/**`, `worker.py`, scheduler). Complementa `AGENTS.md`, `docs/architecture-standard.md` e `docs/governance-contracts.md`.

Objetivo primário: **um agente de IA deve conseguir diagnosticar qualquer execução lendo o log, sem heurística de texto livre** — saber em qual etapa quebrou, se é infra ou dado, se exige intervenção humana ou se o retry/cron cobre, e qual foi o resultado quantitativo.

---

## 1. Decisões da entrevista (27/08/2026)

| # | Tema | Decisão |
|---|------|---------|
| 1 | **Base64 Bridge** | **Removido.** UTF-8 ponta a ponta. O encoder em `lib/Lib-Retry.psm1` e a menção em `lib/README.md` saem. |
| 2 | **Níveis** | 4 níveis, semântica **redefinida** (§5). Sem campo `action_required` — `ERRO` já implica intervenção. |
| 3 | **Schema** | **JSON único** emitido nativamente por PS + Python + Node + Orchestrator. Fim do re-parse por regex (`Get-ForwardedLogLevel`). |
| 4 | **Campos obrigatórios** | `step`, `outcome_code` + `outcome_reason` (evento final), `duration_ms`, `record_counts` (quando aplicável). |
| 5 | **Correlação** | `trace_id` **global**, nascido no `run.ps1` e propagado a Python (arg/env), Node (arg/env) e Orchestrator (header `X-Trace-Id`). `exec_id` permanece como id da camada local. |
| 6 | **Mascaramento** | **Defesa em profundidade:** cada runtime mascara antes de gravar; o Orchestrator revalida na ingestão (`sanitize_log_payload`). |
| 7 | **Retenção** | `Logs/*.jsonl` local: **15 dias**, todos os níveis. DB (`Execution.logs`): **90 dias**, `INFO` para cima. `DEBUG` **não** persiste no DB. |
| 8 | **Evento final** | Um evento `execution.end` estruturado único substitui as 2–3 linhas atuais (`FIM - ExitCode=…` + mensagem + separador `====`). |
| 9 | **Taxonomia** | Eventos **nomeados**: `execution.start` / `execution.end` / `step.start` / `step.end` / `retry.attempt` / `log`. |
| 10 | **Enforcement** | JSON Schema versionado (`docs/log-event.schema.json`) + `Tools/Test-LogEventSchema.ps1` no pre-commit e no CI. |
| 11 | **Enum `step`** | Fixo: `preflight | lock | extract | transform | dispatch | commit | cleanup | custom`. `custom` exige `step_name` livre. |
| 12 | **Rollout** | Piloto em **ORB-07**, depois as outras 5 automações `run.ps1`, gate `warn` → **bloqueante** no PR final. Produção Beneficiamento entra no PR do Orchestrator (consumo é snapshot-first via API). |

### Decisões da Rodada 3 (27/08/2026)

| Tema | Decisão |
|------|---------|
| **Montagem do `execution.end`** | O Python de domínio grava `record_counts` em `orb_result.json` (arquivo que já produz). O `run.ps1` (`Exit-AutomationWithCode`) lê esse arquivo, junta com o exit code e a timeline de `step`s que ele mesmo mediu, e emite o **único** `execution.end`. |
| **Canal de saída** | `stdout` = **exclusivamente linhas JSON** (eventos estruturados). `stderr` = rastro humano opcional de debug, **não** persistido. `logParser.ts` e o worker passam a parsear JSON no PR1 (sem período de emissão dupla). |
| **`lib/python/automation_log.py`** | `make_logger` é **reescrito** para emitir `{event:"log",…}` em `stdout`. Continua sendo o único helper Python (ganha as funções de ciclo de vida). Sem arquivo `log_event.py` separado. |
| **Node (`WhatsApp-Core.js`)** | No PR1 permanece emitindo texto; o `run.ps1` embrulha cada linha num envelope `event:"log"`. Migração nativa do Node fica para PR posterior. |

---

## 2. O evento de log

Uma linha de log = **um objeto JSON** (JSON Lines), emitido em `stdout` **e** gravado em `Logs/<slug>.jsonl`. Os dois destinos carregam o mesmo formato. `stderr` fica reservado para rastro humano de debug e não é persistido.

### 2.1 Envelope (todo evento)

| Campo | Tipo | Regra |
|-------|------|-------|
| `ts` | string | ISO-8601 **UTC** com sufixo `Z`, precisão de segundo. Ex.: `2026-08-27T07:01:51Z`. |
| `level` | enum | `INFO` \| `WARN` \| `ERRO` \| `DEBUG` (§5). |
| `component` | enum | `ps_script` \| `python_domain` \| `node_whatsapp` \| `orchestrator_api` \| `orchestrator_worker` \| `orchestrator_scheduler`. |
| `event` | enum | `execution.start` \| `execution.end` \| `step.start` \| `step.end` \| `retry.attempt` \| `log`. |
| `automation` | string | Nome canônico, idêntico ao `automation.manifest.json`. Ex.: `OBs Restricao Branco`. |
| `exec_id` | string | Id da execução na camada local (telemetria `TEL_…`, cron `CRON_…`, ou `New-ExecId`). |
| `trace_id` | string | Id global da cadeia (§4). Ex.: `orb-20260827T070140Z-a4f2`. |
| `message` | string | Texto livre em **pt-BR**, já mascarado. Chaves e valores de enum sempre em inglês/ASCII. |

Campos opcionais do envelope: `env` (`PRD` default), `request_id` (HTTP, só `orchestrator_*`).

### 2.2 Campos condicionais

| Campo | Obrigatório em | Tipo | Nota |
|-------|----------------|------|------|
| `step` | `step.start`, `step.end`, `retry.attempt` | enum (§ decisão 11) | Recomendado também em `event: log`. |
| `step_name` | quando `step == "custom"` | string | Ex.: `snapshot`, `persist`, `reconcile` (Produção Beneficiamento). |
| `attempt` / `max_attempts` | `retry.attempt` | int | |
| `duration_ms` | `step.end`, `execution.end` | int | Milissegundos. Em `execution.end` é o total. |
| `ok` | `step.end` | bool | |
| `outcome_code` | `execution.end` | int | **Igual ao exit code do processo.** |
| `outcome_reason` | `execution.end` | string | String canônica do `EXIT_CODE_MAP` (`Orchestrator/app/constants.py`). Ex.: `idempotente: nada a notificar`. |
| `record_counts` | `execution.end`, quando a automação processa registros | objeto | Chaves canônicas: `read`, `qualified`, `notified`, `skipped`, `suppressed`. Chaves extras específicas do domínio permitidas. |
| `steps` | `execution.end` | array | Resumo da timeline: `[{ "step": "extract", "ok": true, "duration_ms": 8300 }, …]`. |

### 2.3 Exemplos

```json
{"ts":"2026-08-27T07:01:40Z","level":"INFO","component":"ps_script","event":"execution.start","automation":"OBs Restricao Branco","exec_id":"CRON_6_1787824800_94F5","trace_id":"orb-20260827T070140Z-a4f2","message":"Inicio ORB-07"}
{"ts":"2026-08-27T07:01:41Z","level":"INFO","component":"ps_script","event":"step.start","step":"extract","automation":"OBs Restricao Branco","exec_id":"CRON_6_1787824800_94F5","trace_id":"orb-20260827T070140Z-a4f2","message":"Extracao Oracle + validacao de estoque"}
{"ts":"2026-08-27T07:01:49Z","level":"INFO","component":"python_domain","event":"retry.attempt","step":"extract","attempt":1,"max_attempts":3,"automation":"OBs Restricao Branco","exec_id":"CRON_6_1787824800_94F5","trace_id":"orb-20260827T070140Z-a4f2","message":"Extracao OBs Restrição Branco (extract_orb.py) - sucesso na tentativa 1/3"}
{"ts":"2026-08-27T07:01:50Z","level":"INFO","component":"python_domain","event":"step.end","step":"extract","ok":true,"duration_ms":8300,"automation":"OBs Restricao Branco","exec_id":"CRON_6_1787824800_94F5","trace_id":"orb-20260827T070140Z-a4f2","message":"120 OBs lidas, 2 qualificadas"}
{"ts":"2026-08-27T07:01:50Z","level":"INFO","component":"python_domain","event":"log","step":"dispatch","automation":"OBs Restricao Branco","exec_id":"CRON_6_1787824800_94F5","trace_id":"orb-20260827T070140Z-a4f2","message":"OB #185260 estoque insuficiente: precisa 30 un, saldo livre 8 un"}
{"ts":"2026-08-27T07:01:51Z","level":"INFO","component":"ps_script","event":"execution.end","automation":"OBs Restricao Branco","exec_id":"CRON_6_1787824800_94F5","trace_id":"orb-20260827T070140Z-a4f2","outcome_code":2,"outcome_reason":"idempotente: nada a notificar","duration_ms":11120,"record_counts":{"read":120,"qualified":2,"notified":0,"skipped":118,"suppressed":2},"steps":[{"step":"preflight","ok":true,"duration_ms":900},{"step":"extract","ok":true,"duration_ms":8300},{"step":"dispatch","ok":true,"duration_ms":0}],"message":"Nenhuma OB nova com estoque suficiente"}
```

---

## 3. Ciclo de vida de eventos nomeados

| Evento | Quem emite | Quando |
|--------|-----------|--------|
| `execution.start` | `run.ps1` (via helper), após resolver `ExecId`/`trace_id` e passar no pré-flight | uma vez, no início |
| `step.start` | quem entra na etapa (PS ou o processo filho) | antes de cada etapa |
| `retry.attempt` | `Invoke-WithRetry` (`lib/Lib-Retry.psm1`) e o equivalente Python | cada tentativa > 1 **e** o resultado de cada tentativa |
| `step.end` | quem sai da etapa | após cada etapa, com `ok` + `duration_ms` |
| `execution.end` | `Exit-AutomationWithCode` (`lib/Lib-Logging.psm1`) | uma vez, imediatamente antes do `exit` |
| `log` | qualquer camada | linha informativa/aviso/erro que não é marco de ciclo |

`retry.attempt` substitui as linhas de texto `[RETRY] …` que hoje passam pelo encoder Base64 — é a mudança que fecha o defeito original na raiz, para as 6 automações de uma vez (todas compartilham `Lib-Retry.psm1`).

---

## 4. `trace_id` — propagação

Formato: `<slug>-<ISO8601Z compacto>-<sufixo aleatório 4 hex>`. Ex.: `orb-20260827T070140Z-a4f2`.

| De → Para | Mecanismo |
|-----------|-----------|
| `run.ps1` → Python | argumento `--trace-id` **e** env `HUB_TRACE_ID` |
| `run.ps1` → Node (`Send-WhatsApp.ps1` → `WhatsApp-Core.js`) | argumento `-TraceId` / env `HUB_TRACE_ID` |
| qualquer camada → Orchestrator | header HTTP `X-Trace-Id` nas chamadas a `/api/**` (telemetria, broadcast) |
| Orchestrator worker → `run.ps1` (execução por cron) | env `HUB_TRACE_ID` no `build_subprocess_env()`; o `run.ps1` herda em vez de gerar |

`exec_id` **não muda de significado** — continua sendo o id da execução na camada local. `trace_id` é o que une a cadeia inteira num filtro só no Monitor/Dashboard.

---

## 5. Níveis — semântica canônica

| Nível | Significado | Exemplos |
|-------|-------------|----------|
| `DEBUG` | Rastro fino para investigação. Não persiste no DB. | `Lock global adquirido`, `Limpeza finally: .tmp removido` |
| `INFO` | **Curso normal**, inclusive desfechos "sem ação". | `execution.start`, `nada a notificar`, `OB #X estoque insuficiente` (esperado no domínio), `retry` com sucesso |
| `WARN` | **Desvio** que merece revisão quando houver tempo, mas a execução seguiu. | tentativa de retry que falhou mas a seguinte funcionou; canal secundário degradado; `.env` ausente com fallback |
| `ERRO` | A automação **falhou** — intervenção necessária. | Oracle down após 3 tentativas; sessão WhatsApp expirada (`ExitCode 21`); pré-flight reprovado |

Mudança em relação ao estado atual: **"estoque insuficiente para a OB" deixa de ser `WARN` e passa a `INFO`** — é resultado esperado do domínio, não anomalia. Um run de sucesso não deve emitir `WARN`.

Alinhamento com `EXIT_CODE_MAP`: `outcome_code` ∈ {0, 2, 22} → último evento `INFO`; PARTIAL (24, 25) → `WARN`; ERROR (3, 9, …) → `ERRO`.

---

## 6. Encoding — UTF-8 ponta a ponta

- **Removido:** o branch `if ($Msg -match '[^\x00-\x7F]')` de `lib/Lib-Retry.psm1` e o item "Base64 Bridge" de `lib/README.md`.
- PowerShell: `Lib-Logging.psm1` já fixa `[Console]::OutputEncoding = UTF8`. O `run.ps1` e o registro da tarefa agendada garantem `-OutputFormat Text` sob code page 65001. Ver `project_powershell_5_1_deliberado` — o runtime é `powershell.exe` 5.1 de propósito; o encoding tem de ser forçado no processo, não presumido.
- Python: `PYTHONUTF8=1` e `PYTHONIOENCODING=utf-8` no `build_subprocess_env()`; `sys.stdout.reconfigure(encoding="utf-8")` no bootstrap dos scripts de domínio.
- Node: `stdout` já é UTF-8; garantir que nenhum `toString()` use `latin1`.
- Orchestrator: a captura de `stdout` do worker decodifica como UTF-8 (hoje `_drain_process_output`).

---

## 7. Mascaramento

Regras (e-mail, `token|key|password|secret|credential|auth|apikey`, Oracle DSN/connect string) ficam em **fonte única lógica**, com três implementações mantidas em paridade por teste de contrato:

- PS: `Protect-SensitiveData` (`lib/Lib-Logging.psm1`) — já existe.
- Python: `lib/python/log_masking.py` — **novo**.
- Node: `lib/log-masking.js` — **novo**.

O runtime mascara **antes** de gravar em disco/`stdout`. O Orchestrator revalida na ingestão via `sanitize_log_payload` (`execution_runtime.py`) como rede de segurança para o arquivo local e para dados legados.

---

## 8. Retenção

| Destino | Janela | Níveis | Mecanismo |
|---------|--------|--------|-----------|
| `Logs/<slug>.jsonl` | 15 dias | todos | `Invoke-LogRotation` (`Lib-Logging.psm1`), já existe |
| `Execution.logs` (DB) | 90 dias | `INFO`+ | filtro na ingestão + poda periódica no worker; `DEBUG` descartado ao persistir |
| broadcast WebSocket ao vivo | efêmero | `INFO`+ | sem mudança |

`Execution.logs` continua comprimido (`CompressedText`, zlib+base64) — não confundir com o Base64 Bridge removido; são coisas distintas.

---

## 9. Enforcement

- **`docs/log-event.schema.json`** — JSON Schema (draft 2020-12) do evento, fonte única. Versionado.
- **`Tools/Test-LogEventSchema.ps1`** — valida amostras de `Logs/*.jsonl` e as fixtures de teste contra o schema. Entra como validação nº 15 de `ValidarAutomacoes.ps1 -OnlyGovernance` e no job de governança do CI (`.github/workflows/governanca.yml`).
- **Modo `warn`** até todas as automações migrarem: reporta divergência sem falhar o gate. O PR final vira `blocking` e remove a tolerância a linha de texto legada no `logParser.ts` e no worker.
- Teste de paridade de mascaramento entre os 3 runtimes (`lib/tests/`).

---

## 10. Rollout

| PR | Conteúdo |
|----|----------|
| **PR1 — fundação + piloto** | `log-event.schema.json`; helper `lib/Lib-LogEvent.psm1`; `lib/python/automation_log.py` reescrito + `lib/python/log_masking.py`; `Test-LogEventSchema.ps1` (modo `warn`); `Lib-Retry.psm1` passa a emitir `retry.attempt` estruturado (remove o encoder B64); `Lib-Logging.psm1` emite envelope estruturado em `stdout`; **ORB-07** adaptada ponta a ponta (`run.ps1` + `extract_orb.py` + `format_message.py`); `logParser.ts` + worker passam a aceitar JSON **e** o formato legado. Validar 1 ciclo em produção. |
| **PR2** ✅ | Helpers `Start-HubStep`/`Complete-HubStep`/`Get-HubRecordCounts` + `Exit-AutomationWithCode -RecordCountsPath`; **OFST-06** migrada; ORB-07 refatorada para os helpers. |
| **PR3** ✅ | **OBP-04** migrada; `Invoke-OraclePythonScript -StdoutIsData` (preparação p/ RE-03). |
| **PR4** ✅ | **RE-03, RB-01, MT-02** migradas — rollout de código-fonte das 6 automações completo. |
| **PR Node** | `lib/WhatsApp-Core.js` + `lib/log-masking.js` / `lib/log-event.js` — envelope nativo, sem embrulho do `run.ps1`. |
| **PR Orchestrator** | `Orchestrator/app/**`, `worker.py`, scheduler e `Produção Beneficimento/src/runner.py` no mesmo envelope. |
| **PR final** | Gate → `blocking`; remove `Get-ForwardedLogLevel` e o caminho de texto legado; atualiza `lib/README.md`, `AGENTS.md`, `docs/ai-native-context-monitor.md`; entrada no `CHANGELOG.md`. |

---

## 11. Impacto no Dashboard (fora do caminho crítico do PR1)

- `Dashboard/src/lib/logParser.ts`: parser de JSON Lines com fallback ao `LINE_RE` atual durante o rollout.
- `LogViewer`: timeline de etapas a partir de `step.start`/`step.end`; cabeçalho de diagnóstico a partir de `execution.end` (`outcome_reason`, `record_counts`, etapa que falhou). Mantém o teto de 2.000 linhas e os chips de nível.
- Filtro por `trace_id` no Monitor para reconstruir a cadeia entre processos.

---

## 12. Questões de implementação em aberto

1. **`record_counts` por automação:** cada automação expõe seus contadores no seu `orb_result.json`/equivalente; mapear chaves canônicas vs. específicas do domínio no PR de cada uma.
2. **Teto de 5 MB / 2.000 linhas:** confirmar no PR1 que `_drain_process_output` e `logParser.ts` lidam bem com linhas longas de JSON.
3. **Migração nativa do Node** (`WhatsApp-Core.js` emitindo envelope direto, sem embrulho do `run.ps1`): PR próprio, depois das 6 automações.
