# Backlog Semana 1 — Automacoes Hub

## Objetivo

Executar a primeira semana de endurecimento e refatoração incremental do hub sem quebrar o fluxo atual.

## Regras da semana

- diffs pequenos
- uma tarefa por mudança principal
- preservar compatibilidade
- validar antes de expandir escopo
- rollback simples obrigatório
- não mexer em regra de negócio VBA sem necessidade

---

## Dia 1 — Inventário e segurança operacional mínima

### Tarefa 1

**Nome:** Mapear contratos de execução
**Prioridade:** P0

**Objetivo:** identificar entrypoints, artefatos, logs e dependências por automação.

**Arquivos alvo:**

- documentação operacional
- scripts principais de entrada
- configs relacionadas

**Validação:**

- lista consolidada de entradas e saídas
- tabela de exit codes por fluxo
- mapa de artefatos críticos

---

### Tarefa 2

**Nome:** Confirmar propagação de ExecId
**Prioridade:** P0

**Objetivo:** verificar se `ExecId` está íntegro entre PowerShell, VBS/VBA e Node.js.

**Validação:**

- um fluxo real ou controlado com correlação ponta a ponta
- evidência em log

---

### Tarefa 3

**Nome:** Rodar smoke test seguro do monitor
**Prioridade:** P0

**Objetivo:** validar startup, agenda e métricas sem disparar automações reais.

**Validação:**

- `RunOnce + SkipTaskExecution`
- `RunOnce + DryRun`
- leitura de métricas e estado do dashboard

---

## Dia 2 — Timeout e travamento de Excel

### Tarefa 4

**Nome:** Implementar timeout no runner PowerShell
**Prioridade:** P0

**Objetivo:** evitar execução indefinida em fluxos com Excel/COM.

**Validação:**

- timeout disparando corretamente
- log claro com `ExecId`
- retorno operacional coerente

---

### Tarefa 5

**Nome:** Implementar cleanup seguro de Excel órfão
**Prioridade:** P0

**Objetivo:** impedir acúmulo de `Excel.exe` preso após falha.

**Validação:**

- processo órfão detectado
- cleanup controlado
- sem impacto em instâncias não relacionadas

---

### Tarefa 6

**Nome:** Cobrir workbook bloqueado/read-only
**Prioridade:** P1

**Objetivo:** melhorar reação a arquivo bloqueado e leitura somente.

**Validação:**

- erro operacional claro
- rollback simples
- sem mascarar causa raiz

---

## Dia 3 — WhatsApp bridge hardening

### Tarefa 7

**Nome:** Validar `whatsapp-config.json` por schema
**Prioridade:** P0

**Objetivo:** falhar cedo em config inválida.

**Validação:**

- validar `target`
- validar `message`
- validar `runtime`
- validar `retry`
- validar `paths`
- validar `idempotency`

---

### Tarefa 8

**Nome:** Melhorar tratamento do erro 21
**Prioridade:** P0

**Objetivo:** deixar reautenticação clara e operacional.

**Validação:**

- log explícito
- instrução de uso do modo PAIRING
- sem erro genérico

---

### Tarefa 9

**Nome:** Melhorar tratamento dos erros 22, 23 e 40
**Prioridade:** P1

**Objetivo:** diferenciar config inválida, cooldown e lock concorrente.

**Validação:**

- logs distintos
- mensagens operacionais úteis
- sem alterar a semântica do bridge

---

## Dia 4 — Observabilidade

### Tarefa 10

**Nome:** Criar log JSONL paralelo
**Prioridade:** P1

**Objetivo:** adicionar logging estruturado sem remover o log humano atual.

**Campos mínimos:**

- timestamp
- layer
- level
- execId
- message

**Validação:**

- ambos os logs coexistem
- nenhuma quebra no parser/manual atual

---

### Tarefa 11

**Nome:** Criar watchdog externo do monitor
**Prioridade:** P0

**Objetivo:** detectar monitor sem heartbeat recente.

**Base de verificação:**

- `Monitor_Metrics.json`
- `dashboard-state.json`

**Validação:**

- stale heartbeat detectado
- alerta mínimo emitido
- sem acoplamento forte ao monitor principal

---

## Dia 5 — Governança e fechamento

### Tarefa 12

**Nome:** Atualizar runbook operacional
**Prioridade:** P1

**Objetivo:** registrar resposta para os incidentes mais prováveis.

**Cobrir:**

- monitor parado
- Excel travado
- WhatsApp reauth
- config inválida
- cooldown e lock

---

### Tarefa 13

**Nome:** Validar governança do repositório
**Prioridade:** P0

**Objetivo:** garantir conformidade antes de merge.

**Validação:**

- validadores centrais
- conformidade de log
- markdown dry-run
- governança de skill

---

### Tarefa 14

**Nome:** Smoke test final controlado
**Prioridade:** P0

**Objetivo:** validar o pacote completo da semana.

**Cenários mínimos:**

- startup seguro
- dry run
- timeout
- cleanup
- config inválida
- reauth
- cooldown
- lock concorrente

---

## Critérios de pronto da semana

A semana estará concluída quando:

- nenhum fluxo crítico perder compatibilidade
- os logs permanecerem legíveis
- `ExecId` estiver preservado
- o monitor continuar íntegro
- o bridge WhatsApp continuar operando com AUTO/PAIRING
- existir rollback simples para cada mudança principal
- a governança do repositório passar

---

## Ordem recomendada por agente

### Agente 1 — Runtime PowerShell / Excel

- Tarefa 4
- Tarefa 5
- Tarefa 6

### Agente 2 — WhatsApp / Node.js

- Tarefa 7
- Tarefa 8
- Tarefa 9

### Agente 3 — Observabilidade / Governança

- Tarefa 10
- Tarefa 11
- Tarefa 12
- Tarefa 13

### Revisão final

- Tarefa 14

---

## Model routing sugerido

- Modelo de código: implementação, testes, scripts, validações locais
- Modelo de revisão rápida: leitura do repo, backlog, runbooks, revisão de diff
- Modelo de revisão profunda: auditoria final, P0, análise de falha e risco residual

---

## Versão melhor com tecnologia atual

Depois desta semana 1, a evolução natural é criar semana 2 com foco em adapter layer, isolamento de repositório Oracle e redução progressiva da dependência direta do Excel/VBA.
