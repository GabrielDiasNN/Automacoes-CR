# Cognitive Context: Receitas Emitidas

## Business Purpose
Esta automacao controla a emissao semanal do relatorio de **Receitas de Tingimento** que foram liberadas pelo laboratorio, mas que ainda nao foram pesadas na Cozinha de Quimicos.
O objetivo e fornecer uma visao clara para a equipe de producao sobre o volume de carga pendente, permitindo o planejamento da sequencia de tingimento e a conferencia fisica dos lotes.

## Technical Identity
- **Architecture:** 100% Nativa e Soberana (Python + PowerShell). Primeira automacao do Hub a eliminar totalmente o Excel do ciclo de vida produtivo.
- **Interoperability:** Utiliza IPC via Stdio (Standard Input/Output): o stdout dos filhos Python e dado (JSON/HTML), o stderr vira evento de log, e a leitura usa `utf-8-sig`.

## Cognitive Map
1. **Trigger:** `MonitorAutomacoes.ps1` (Agendado semanalmente).
2. **Extract Layer:** `extract_oracle.py` se conecta ao Oracle (`sgtprd`) e utiliza uma **Query CTE (Common Table Expressions)** otimizada para extrair dados em segundos sem timeouts.
3. **Intelligence Layer:** `generate_html_report.py` processa o agrupamento e aplica o layout adaptativo de colunas.
4. **Delivery Layer:** `run_receitas.py` (orquestrador Python, sobre `lib/python/hub_runner.py`) coordena o fluxo; o disparo e feito pela CLI `lib/Invoke-OutlookEmail.ps1` (Outlook COM). `run.ps1` e so um shim que chama o runner.

## Key Rules
-   **Layout Adaptativo:** O sistema calcula um "Volume Score" para decidir o tamanho da fonte e o numero de colunas (2 ou 3).
-   **SQL DNA:** Injecao obrigatoria de comentarios `/* ExecId: ... */` para auditoria de DBAs no Oracle.

## Security & Resilience
-   **Envelope de log:** eventos JSON no formato de `docs/log-event.schema.json`, anexados a `Logs/ReceitasEmitidas.jsonl` pelo `hub_runner`.
-   **Pre-flight Oracle:** no modo `queue`, o worker da fila e decidido como no PowerShell (heartbeat de 45 s, 240 s com worker ocupado); fora da fila, o Oracle so gera aviso.
-   **Auto-Masking:** Protecao de dados sensiveis integrada a `Lib-Logging`.

---

## 🧠 Gestão de Contexto (AI-Native)
- **Obrigação:** Atualizar este contexto se houver mudanças na Query CTE, no layout HTML ou no fluxo IPC Stdio.
- **Estado (11/05/2026):** Idempotência estabilizada via remoção de campos voláteis (SYSDATE) e ordenação determinística por NUMERO_OB.
- **Estado (18/11/2026):** Orquestração migrada para `run_receitas.py` (sobre `hub_runner`); `run.ps1` virou shim. Excecao nao prevista fecha a execucao com `ERRO FATAL` (exit 1), e o lock e liberado.
- **Objetivo:** Garantir que a IA entenda a natureza "VBA-Free" e "Soberana" deste módulo sem re-analisar o código Python.
