# Automação - Receitas Bloqueadas

## Visão Geral

Este projeto automatiza o processamento e a distribuição da planilha de **Receitas Bloqueadas**. A automação envolve a atualização de dados via Excel/VBA, envio de e-mails e distribuição do arquivo atualizado através do WhatsApp.

## Fluxo do Processo

O fluxo técnico segue esta ordem:

`MonitorAutomacoes.ps1` (Orquestrador) -> `run.ps1` (Runner PS) -> `Excel COM` (VBA) -> `Send-WhatsApp.ps1` (Bridge) -> `sendWhatsApp.js` (Node.js) -> **WhatsApp**

---

## Componentes do Projeto

### 1. Runner PowerShell (`run.ps1`)
Orquestrador nativo que substitui o antigo VBScript:
- Inicia a instância do Excel em modo invisível via COM.
- Gerencia a compilação preventiva (Preflight) do VBA para evitar quebras em tempo de execução.
- Executa a macro principal `ExecutarProcessoCompleto`.
- **Monitoramento de Log**: Acompanha o arquivo de log do VBA em tempo real para detectar o fim do processo ou erros fatais.
- Dispara o `Send-WhatsApp.ps1` de forma síncrona após o sucesso da macro.

### 2. Workbook Excel (`Receitas Bloqueadas.xlsm`)
Contém a inteligência de negócio no VBA:
- Atualiza as conexões de dados (Power Query/Connections).
- Ajusta a formatação de data para o padrão PT-BR (`dd/mm/yyyy`).
- Gera o corpo do e-mail em HTML.
- Realiza o envio do e-mail (se houver dados na tabela).
- Salva o arquivo final para ser enviado pelo WhatsApp.

### 3. Bridge WhatsApp (`lib/Send-WhatsApp.ps1`)
Wrapper PowerShell que encapsula a execução do Node.js:
- Valida pré-requisitos (Node.exe, Script, Config).
- Gerencia o modo de execução (**AUTO** vs **PAIRING**).
- **Auto-Redirecionamento**: Se a sessão estiver expirada (Exit 21), abre automaticamente uma janela interativa para re-pareamento.
- Aplica lock de execução (`.sendwhatsapp.lock`) para evitar concorrência.

### 4. Distribuidor Node.js (`sendWhatsApp.js`)
Utiliza a biblioteca `whatsapp-web.js` para o envio das mensagens:
- **Idempotência**: Verifica no `whatsapp-state.json` se a execução já foi enviada.
- **Resiliência**: Sistema de retentativas (Retry) configurável.

---

## Operação e Manutenção

### Logs e Diagnóstico
- **Log Unificado**: `Logs/ReceitasBloqueadas.log`
  - Contém a trilha consolidada: `[PS]` para o orquestrador e `[VBA]` para a macro.
- **Log de Bootstrap WhatsApp**: `sendWhatsApp-bootstrap.log`.

### Códigos de Saída (Exit Codes)
- `0`: Sucesso.
- `7`: Workbook bloqueado (somente leitura).
- `21`: Reautenticação do WhatsApp necessária.
- `23`: WhatsApp em cooldown de retry.
- `40`: Execução concorrente bloqueada (lock ativo).
