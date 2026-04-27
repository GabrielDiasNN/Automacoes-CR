# Automacao - Receitas Bloqueadas (v1.2.1 - VBA Legado + WhatsApp)

## Visao Geral

Este projeto automatiza o processamento, a consolidacao e a distribuicao da planilha de **Receitas Bloqueadas**. O sistema integra fluxos de atualizacao via Excel/VBA com entregas multicanal (Email e WhatsApp Business), garantindo que o planejamento da fabrica nunca pare.

## Arquitetura de Fluxo (Outlook-Safe)

A execucao segue o pipeline resiliente:

`MonitorAutomacoes.ps1` (Monitor) -> `run.ps1` (Orquestrador)
  -> **Fase 1**: `Excel COM` (VBA) atualiza dados e envia e-mail legado.
  -> **Fase 2**: PowerShell aguarda 5s para esvaziamento da *Outbox* do Outlook.
  -> **Fase 3**: `Send-WhatsApp.ps1` (Bridge) -> `sendWhatsApp.js` (Node.js) -> **WhatsApp**.

---

## Arquitetura de Componentes

### 1. Orquestrador PowerShell (`run.ps1`)
Gerente de runtime e sincronizacao:
- Executa a macro `modReceitasBloqueadas.ExecutarProcessoCompleto`.
- **Outlook-Safe Protocol**: Implementa um *Buffer de Estabilidade* de 5 segundos apos a macro, garantindo que o Outlook COM conclua o envio da mensagem antes do fechamento do processo.
- **Base64 Bridge**: Mantem a integridade dos logs entre camadas PS e VBA.

### 2. Workbook de Negocio (`Receitas Bloqueadas.xlsm`)
Nucleo de inteligencia em VBA e Power Query:
- Atualizacao deterministica das conexoes do Oracle.
- Geracao de alertas fiscais com formatacao PT-BR absoluta.
- Ponto de origem do arquivo binario consumido pelo WhatsApp.

### 3. Bridge WhatsApp (`lib/Send-WhatsApp.ps1`)
Interface para o ecossistema Node.js:
- **Gestao de Sessao**: Relancamento automatico em modo `PAIRING` se necessario.
- **Lock Concorrente**: Bloqueia execucoes paralelas via arquivo `.sendwhatsapp.lock` para evitar banimento no WhatsApp.

### 4. Distribuidor Node.js (`sendWhatsApp.js`)
Integracao via `whatsapp-web.js`:
- **Idempotencia**: Verifica o estado persistido para evitar notificacoes repetitivas.
- **Mecanica de Retry**: Resiliencia contra quedas momentaneas de conexao.

---

## Operacao e Diagnostico

### Logs e Engenharia
- **Localizacao**: `Logs/ReceitasBloqueadas.log` (Prefixos `[PS]` e `[VBA]`).
- **ASCII-Safe Source**: Mensagens de log em codigo-fonte sao mantidas em ASCII puro, garantindo independencia de terminal.

### Matriz de Exit Codes
| Codigo | Significado |
| :--- | :--- |
| **0** | Sucesso em todas as camadas |
| **7** | Workbook bloqueado (Read-Only) |
| **21** | Sessao WhatsApp expirada: requer pareamento |
| **23** | Bridge em Cooldown de retentativas |
| **40** | Erro de concorrencia: lock ativo |

---

## 🗺️ Roadmap
O nucleo de extracao esta planejado para migracao para a **Arquitetura Nativa (Pure-Python)** futuramente, eliminando a dependencia do Excel.
