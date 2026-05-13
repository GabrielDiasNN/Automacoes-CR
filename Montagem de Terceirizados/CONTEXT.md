# Cognitive Context: Montagem de Terceirizados

## Business Purpose
Esta automacao e o guardiao da integridade entre a **Programacao de Producao** e a **Montagem Fisica** realizada por terceirizados (faccoes). 
O objetivo e garantir que a Ordem de Fabricacao (OB) que esta sendo montada corresponda exatamente a Nota Fiscal (NF) enviada pelo cliente. Divergencias aqui podem gerar erros de estoque, faturamento errado e multas fiscais.

## Why this architecture? [ARCH-PURE-NATIVE]
- **Pure-Native (v2.0):** Migramos para uma arquitetura 100% nativa (Python/Oracle) para eliminar a fragilidade da interface COM do Excel e a lentidao de processos baseados em UI.
- **SQL Performance:** Substituimos as Views pesadas do banco por queries otimizadas (`SQL-MontagemTerceirizados.sql`) que utilizam CTEs. Isso estabilizou a conexao nativa e eliminou a necessidade de fallback.
- **Background execution:** A automacao agora roda de forma invisivel e ultra-rapida, ideal para ambientes de servidor.

## Cognitive Map
1.  **Trigger:** `MonitorAutomacoes.ps1` (Agendado de hora em hora).
2.  **Fetch Layer:** `extract_oracle.py` carrega o SQL externo e extrai dados diretamente via driver `oracledb`.
3.  **Intelligence Layer:** `validate_and_generate_html.py`.
    -   **Validation Rule 1:** A NF na observacao da OB (`NF:\d+`) deve ser igual a Ref. Cliente.
    -   **Validation Rule 2:** A NF no campo de Montagem (`QT_PC_NF` formatado como `Qtd-NF`) deve ser igual a Ref. Cliente.
4.  **Delivery Layer:** PowerShell envia e-mail moderno via Outlook COM (Outlook-Safe).

## Key Identifiers
-   `ExecId`: Correlation ID para rastrear o fluxo entre Python e Logs.
-   `.cache_erros.json`: Persistencia de estado para garantir **Idempotencia** (nao repetir alertas identicos).
-   `SQL-MontagemTerceirizados.sql`: Unica fonte de verdade para a extracao de dados de producao.

## Security & Integrity
-   **Logging:** Todas as mensagens acentuadas utilizam o **Base64 Bridge Protocol**.
-   **No UI dependency:** Remocao total de dependencias do Office Excel para processamento de dados.
-   **Encapsulamento SQL:** Regras de negocio complexas estao isoladas no arquivo SQL, facilitando o tuning sem alterar o core da aplicacao.

---

## 🧠 Gestão de Contexto (AI-Native) - Atualizado em 12/05/2026
- **Estado:** Estabilizado v2.2.1.
- **Resiliência:** Corrigido erro de sintaxe Python e endurecida a lógica de orquestração PowerShell para garantir o envio de notificações mesmo em situações de variabilidade nos parâmetros de entrada.
- **Idempotência:** Mantida a lógica de Two-Phase Commit para consolidação do estado apenas após sucesso confirmado.
