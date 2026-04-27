# Cognitive Context: Receitas Bloqueadas

## Business Purpose
Esta automacao gerencia o fluxo de **Receitas de Producao Retidas** no sistema por falta de insumos ou inconsistencias tecnicas. 
O objetivo e garantir que a equipe de planejamento receba alertas em tempo real via WhatsApp e e-mail sempre que uma nova receita for bloqueada, permitindo a liberacao rapida para evitar paradas de maquina na fabrica.

## Technical Identity
- **Architecture:** Hibrida (PowerShell + Excel COM + Node.js).
- **Outlook-Safe:** Protocolo de espera sincrona para garantir que e-mails gerados via VBA saiam da Outbox antes do encerramento do script.

## Cognitive Map
1.  **Trigger:** `MonitorAutomacoes.ps1` (Execucao agendada).
2.  **Logic Layer:** `run.ps1` abre o Excel `Receitas Bloqueadas.xlsm` e executa a macro `modReceitasBloqueadas.ExecutarProcessoCompleto`. 
3.  **Safe Exit:** O script aguarda 5 segundos apos o VBA para sincronizacao do Outlook.
4.  **Bridge Layer:** `Send-WhatsApp.ps1` (Bridge PS) invoca o motor Node.js.
5.  **Delivery Layer:** `sendWhatsApp.js` utiliza uma sessao autenticada para enviar a planilha e alertas para grupos especificos no WhatsApp.

## Key Identifiers
-   `ExecId`: Correlation ID para rastrear o fluxo entre PowerShell, VBA e Node.js.
-   `whatsapp-state.json`: Controle de **Idempotencia** do WhatsApp.

## Security & Reliability
-   **Pre-Flight:** Validacao de diagnostico antes do disparo do Excel e Node.js.
-   **ASCII-Safe Source:** Codigo-fonte das mensagens blindado contra corrupcao de encoding.
-   **Base64 Bridge:** Transporte de logs acentuados entre processos para garantir PT-BR.
-   **Auto-Masking:** Protecao automatica de contatos e e-mails em logs.
