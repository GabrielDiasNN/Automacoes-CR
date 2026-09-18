---
name: log-triage
description: Triagem autônoma das falhas de execução das automações — coleta falhas da janela, resume o envelope de log estruturado, classifica causa (transiente vs defeito) e aplica a recuperação documentada (requeue) ou abre PR de correção. Use para "analisar os logs das automações", "por que a automação X falhou", "triagem de falhas", "resolver as falhas da noite" ou quando rodar como agendado de plantão.
---

# Triagem de falhas das automações

Objetivo: transformar falha de execução em **desfecho** — recuperada, corrigida
em PR, ou escalada com diagnóstico pronto — sem exigir operação manual do
usuário para o caminho mecânico.

O coletor é `.claude/skills/log-triage/triagem.py`. Ele lê
`ORCHESTRATOR_API_KEY` do `.env` da raiz; **nunca peça a chave ao usuário**.

## 0. Antes de tudo: a instância é de produção

```bash
.venv\Scripts\python .claude\skills\run-orchestrator\driver.py health
```

Se responder `[OK] saudavel` ou `[AVISO] degradado`, **use a instância viva**.
Nunca rode `Start-Orchestrator.ps1` nesta triagem: ele faz surgical reset, mata
o worker e aborta execuções em voo. API fora do ar é **escalação**, não conserto
autônomo — a recuperação (`Recover-Orchestrator.ps1`) mexe em processo de
produção e é checkpoint humano.

## 1. Coletar

```bash
.venv\Scripts\python .claude\skills\log-triage\triagem.py coletar --horas 24
```

JSON no stdout (UTF-8) com `saude`, `total_falhas`,
`reincidencia_por_automacao` e, por falha:

| Campo | Para que serve na decisão |
|---|---|
| `status`, `exit_code`, `failure_reason` | classificação oficial do Orchestrator (`EXIT_CODE_MAP` em `Orchestrator/app/constants.py`) |
| `recovery_action` | **a ação que o próprio sistema prescreve** — é o eixo da decisão, ver §2 |
| `retry_count` / `max_retries` | quanto do orçamento de retry já foi gasto |
| `requeue_allowed`, `requeue_block_reason` | se a rota de requeue vai aceitar; `False` é veto, não obstáculo a contornar |
| `envelope` | `outcome_reason`, `steps_falhos`, `record_counts`, `trace_id`, `mensagens_erro` do log JSONL |
| `pista` | heurística de texto: `provavel_transitoria`, `provavel_deterministica`, `ambigua`, `indefinida` |
| `log_erro` | **presente só quando o log não pôde ser lido** (429, 5xx, transporte) |

### O relatório declara quando está incompleto

Três campos de nível superior existem para que você não trate relatório cego
como relatório limpo. **Nenhuma decisão de requeue quando eles aparecem:**

| Campo | Significado |
|---|---|
| `janela_inicio` | timestamp ISO real do início da janela — confira contra `janela_horas` |
| `coleta_incompleta` + `erros_parciais` | um ou mais status de falha não foram listados; a contagem de reincidência está **subestimada** |
| `logs_ilegiveis` | quantas falhas vieram sem log legível (cada uma traz `log_erro`) |

Uma falha com `log_erro` tem `envelope: {}` e `pista: "indefinida"` **porque o
log não foi lido**, não porque a execução não logou nada — são coisas
diferentes, e só a primeira exige nova tentativa antes de qualquer decisão.
`coleta_incompleta` com reincidência aparentemente baixa é o caso clássico:
requeue ali reenfileira o sintoma de um problema cujo tamanho você não mediu.

`pista` é **pista**, não veredito: leia `envelope.mensagens_erro` antes de
decidir. Para o log cru de uma execução:

```bash
.venv\Scripts\python .claude\skills\log-triage\triagem.py logs <exec_id> --linhas 120
```

Agrupe por causa antes de agir. `reincidencia_por_automacao` alto com o mesmo
`outcome_reason` é **um** problema com N sintomas: requeue N vezes não resolve e
consome orçamento de retry.

## 2. Decidir pela `recovery_action`

| `recovery_action` | O que o agente faz |
|---|---|
| `REQUEUE_IF_SAFE` | requeue autônomo, se `requeue_allowed` e a causa no log for transiente |
| `REVIEW_LOGS_AND_OPTIONALLY_REQUEUE` | ler o log primeiro; requeue só se a causa for transiente **e** não for reincidente na janela |
| `REVIEW_LOGS_BEFORE_REQUEUE` (preflight) | nunca requeue cego: o ambiente está quebrado. Diagnostique (Python, Oracle, paths) e escale |
| `REVIEW_TIMEOUT_AND_REQUEUE` | confirme que o timeout foi de rede/Oracle, não trabalho legítimo estourando `max_runtime` |
| `REAUTHENTICATE_WHATSAPP_SESSION` | **checkpoint humano** — exige QR code, nenhum agente resolve |
| `REVIEW_CHANNEL_STATE_BEFORE_REQUEUE` | `PARTIAL`: o entregável principal saiu. Nunca requeue (duplica entrega) — relate |
| `REVIEW_WORKER_LOGS` | falha interna do worker; diagnostique e escale |
| `NONE` | desfecho normal disfarçado de falha; não age |

Lembre que `auto_retry_transient_failures` (scheduler, a cada 3 min) já
reenfileira ERROR/TIMEOUT com `max_retries > 0`. Falha que chega à triagem com
`max_retries = 0` **nunca teve retry automático configurado**; falha com
`retry_count = max_retries` já esgotou o orçamento e requeue manual repetido é
justamente o que o operador não quer.

```bash
.venv\Scripts\python .claude\skills\log-triage\triagem.py requeue <exec_id> --motivo "Triagem: <causa transiente observada no log>"
```

`--motivo` é obrigatório e vira trilha de auditoria (`requested_by=AGENTE_TRIAGEM`
em `GET /api/system/audit`). Um requeue por causa, não um por sintoma.

## 3. Defeito de código

Causa determinística (traceback, `ORA-00904`, path inexistente, contrato de
função quebrado) **não** se resolve com requeue. Aí o agente corrige:

1. Confirme que `main` local está sincronizado
   (`git rev-list --left-right --count main...origin/main` → `0 0`).
2. Branch (`fix/...`), correção cirúrgica, teste que cobre a regressão.
3. `cd Orchestrator && ..\.venv\Scripts\pytest` e o lint do CI (`ruff`) antes do push.
4. PR com o `exec_id` e o `trace_id` como evidência.

**Nunca** commite direto em `main`, nunca dê merge sem o CI verde, e nunca edite
`.env` nem o código de uma automação em produção fora do fluxo de PR.

## 4. Checkpoint humano (pare e escale)

- API/worker fora do ar → não reinicie nada; relate.
- `REAUTHENTICATE_WHATSAPP_SESSION` (QR code).
- Pausar, desabilitar ou alterar cron/config de automação.
- `POST /api/system/purge`, `/backup`, `/worker/recover`, mudança em `.env`.
- Merge de PR de correção em produção.
- Falha cuja causa você não conseguiu determinar — escale com log, não com palpite.

## 5. Relatar

Sempre feche com: janela analisada, total de falhas, causas agrupadas, o que foi
recuperado (com `exec_id` novo), o que foi aberto em PR, e o que precisa do
usuário. Quando a triagem roda como agendado e **nada** falhou, diga isso em uma
linha — silêncio é indistinguível de agendado quebrado.
