# Cognitive Context: Receitas Emitidas

## Business Purpose
Esta automacao controla a emissao semanal do relatorio de **Receitas de Tingimento** que foram liberadas pelo laboratorio, mas que ainda nao foram pesadas na Cozinha de Quimicos. 
O objetivo e fornecer uma visao clara para a equipe de producao sobre o volume de carga pendente, permitindo o planejamento da sequencia de tingimento e a conferencia fisica dos lotes.

## Technical Identity
- **Architecture:** 100% Nativa e Soberana (Python + PowerShell). Primeira automacao do Hub a eliminar totalmente o Excel do ciclo de vida produtivo.
- **Interoperability:** Utiliza IPC via Stdio (Standard Input/Output) blindado com o protocolo `utf-8-sig` para transferencia de dados JSON/HTML.

## Cognitive Map
1.  **Trigger:** `MonitorAutomacoes.ps1` (Agendado semanalmente).
2.  **Extract Layer:** `extract_oracle.py` se conecta ao Oracle (`sgtprd`) e utiliza uma **Query CTE (Common Table Expressions)** otimizada para extrair dados em segundos sem timeouts.
3.  **Intelligence Layer:** `generate_html_report.py` processa o agrupamento e aplica o layout adaptativo de colunas.
4.  **Delivery Layer:** PowerShell coordena o fluxo e realiza o disparo via Outlook COM (Outlook-Safe).

## Key Rules
# Cognitive Context: Receitas Emitidas

## Business Purpose
Esta automacao controla a emissao semanal do relatorio de **Receitas de Tingimento** que foram liberadas pelo laboratorio, mas que ainda nao foram pesadas na Cozinha de Quimicos. 
O objetivo e fornecer uma visao clara para a equipe de producao sobre o volume de carga pendente, permitindo o planejamento da sequencia de tingimento e a conferencia fisica dos lotes.

## Technical Identity
- **Architecture:** 100% Nativa e Soberana (Python + PowerShell). Primeira automacao do Hub a eliminar totalmente o Excel do ciclo de vida produtivo.
- **Interoperability:** Utiliza IPC via Stdio (Standard Input/Output) blindado com o protocolo `utf-8-sig` para transferencia de dados JSON/HTML.

## Cognitive Map
1.  **Trigger:** `MonitorAutomacoes.ps1` (Agendado semanalmente).
2.  **Extract Layer:** `extract_oracle.py` se conecta ao Oracle (`sgtprd`) e utiliza uma **Query CTE (Common Table Expressions)** otimizada para extrair dados em segundos sem timeouts.
3.  **Intelligence Layer:** `generate_html_report.py` processa o agrupamento e aplica o layout adaptativo de colunas.
4.  **Delivery Layer:** PowerShell coordena o fluxo e realiza o disparo via Outlook COM (Outlook-Safe).

## Key Rules
-   **Layout Adaptativo:** O sistema calcula um "Volume Score" para decidir o tamanho da fonte e o numero de colunas (2 ou 3).
-   **SQL DNA:** Injecao obrigatoria de comentarios `/* ExecId: ... */` para auditoria de DBAs no Oracle.

## Security & Resilience
-   **ASCII-Safe Core:** Todo o codigo-fonte das mensagens de log e interface e mantido em ASCII ou Escape Sequences, garantindo que regressoes de encoding nunca corrompam o robo.
-   **Base64 Bridge:** Blindagem de logs contra falhas de codificacao do terminal Windows.
-   **Auto-Masking:** Protecao de dados sensiveis integrada a `Lib-Logging`.

---

## 🧠 Gestão de Contexto (AI-Native)
- **Obrigação:** Atualizar este contexto se houver mudanças na Query CTE, no layout HTML ou no fluxo IPC Stdio.
- **Estado (2026-05-11):** Idempotência estabilizada via remoção de campos voláteis (SYSDATE) e ordenação determinística por NUMERO_OB.
- **Objetivo:** Garantir que a IA entenda a natureza "VBA-Free" e "Soberana" deste módulo sem re-analisar o código Python.
