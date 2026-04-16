# Arquitetura Atual — Automacoes Hub

## Visão geral

O projeto é um hub de automações fiscais e operacionais baseado no modelo **Monitor-Trigger-Action**.
O objetivo principal é orquestrar execuções agendadas com resiliência, rastreabilidade e observabilidade, preservando a compatibilidade com fluxos legados.

---

## Stack atual

### Orquestração

- PowerShell
- Monitor central: `MonitorAutomacoes.ps1`

### Entradas de automação

- `TriggerAutomation.vbs` para fluxos legados
- `run.ps1` para fluxos PowerShell nativos

### Processamento de negócio

- Excel
- VBA
- Power Query

### Dados

- Oracle SQL

### Saídas

- Outlook COM para e-mail
- Node.js para bridge WhatsApp

---

## Modelo operacional

A arquitetura segue este padrão:

`MonitorAutomacoes.ps1`
→ agenda e valida configuração
→ dispara automação
→ automação entra por `TriggerAutomation.vbs` ou `run.ps1`
→ Excel/VBA/Power Query processa dados do Oracle
→ gera saída operacional
→ e-mail e/ou WhatsApp são enviados

---

## Componentes centrais

### 1. Monitor central

Responsabilidades:

- agendamento
- mutex global
- hot-reload de `config.json`
- heartbeat operacional
- snapshot de métricas
- persistência de estado do dashboard
- publicação do dashboard HTML

Artefatos principais:

- `Monitor_Metrics.json`
- `dashboard-state.json`
- dashboard HTML publicado
- log consolidado do monitor

---

### 2. Camada de entrada das automações

Há dois modelos principais:

- legado via `TriggerAutomation.vbs`
- moderno via `run.ps1`

Esses entrypoints iniciam a execução do Excel, acionam a macro principal, acompanham o fluxo e registram logs operacionais.

---

### 3. Runtime de negócio

A lógica de negócio ainda está concentrada em:

- workbooks `.xlsm`
- módulos VBA
- consultas Power Query
- integração com Oracle

Esse runtime é responsável por:

- atualizar dados
- validar consistência operacional
- gerar relatórios/planilhas
- produzir saídas consumidas por e-mail e WhatsApp

---

### 4. Bridge WhatsApp

O envio via WhatsApp usa Node.js e um bridge com:

- modo `AUTO`
- modo `PAIRING`
- lock de concorrência
- idempotência
- retry
- tratamento de reautenticação
- validação de `whatsapp-config.json`

No fluxo de Receitas Bloqueadas, o VBA salva o artefato final e o launcher chama o bridge Node.js para distribuição.

---

## Contratos operacionais importantes

### ExecId

`ExecId` é a chave de correlação entre as camadas da execução.
Ele deve ser preservado em qualquer refatoração, endurecimento ou evolução de observabilidade.

### Logs

O projeto possui log humano consolidado com formato operacional padronizado.
Mudanças futuras devem preferir manter esse log e, se necessário, adicionar logging estruturado em paralelo.

### Exit codes

Os fluxos usam códigos padronizados para expressar sucesso, timeout, erro de negócio, workbook bloqueado, cooldown e concorrência do bridge WhatsApp.
Esses códigos fazem parte do contrato operacional e não devem ser alterados sem necessidade forte.

### Dashboard e heartbeat

O monitor mantém artefatos de estado e métricas usados para observabilidade.
Esses arquivos são críticos para operação e diagnóstico rápido.

---

## Principais pontos fortes

- arquitetura já operacional em produção
- monitor central com observabilidade básica
- compatibilidade entre fluxo legado e fluxo PowerShell
- logs padronizados
- rastreabilidade por `ExecId`
- bridge WhatsApp com controles operacionais relevantes

---

## Principais limitações atuais

- dependência forte de Excel/VBA para lógica crítica
- parte do fluxo ainda síncrona e frágil a travamentos
- bridge WhatsApp sensível a sessão e pareamento
- observabilidade ainda centrada em logs e artefatos locais
- acoplamento elevado entre runner, workbook e canais de saída

---

## Direção de evolução recomendada

A evolução deve ser incremental e não disruptiva.

Prioridades:

1. timeout e cleanup seguro
2. validação de configuração
3. clareza de erros operacionais
4. watchdog externo do monitor
5. logging estruturado paralelo
6. refatoração por adapters e wrappers
7. migração gradual de partes do runtime legado

---

## Regra de mudança

Qualquer alteração futura deve respeitar estas premissas:

- preservar compatibilidade operacional
- manter rollback simples
- não remover entrypoints legados sem camada de transição
- não quebrar `ExecId`
- não quebrar logs existentes
- não alterar a semântica do bridge WhatsApp sem fallback operacional
