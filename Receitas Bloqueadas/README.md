# Automação - Receitas Bloqueadas

## Visão Geral

Este projeto automatiza o processamento, a consolidação e a distribuição da planilha de **Receitas Bloqueadas**. O sistema integra fluxos de atualização via Excel/VBA com entregas multicanal (Email e WhatsApp Business).

## Arquitetura de Fluxo

A execução segue o pipeline:

`MonitorAutomacoes.ps1` (Monitor) -> `run.ps1` (Runner PS) -> `Excel COM` (VBA) -> `Send-WhatsApp.ps1` (Bridge) -> `sendWhatsApp.js` (Node.js) -> **WhatsApp**

---

## Arquitetura de Componentes

### 1. Runner PowerShell (`run.ps1`)
Orquestrador de runtime que substitui o orquestrador VBScript legado:
- Executa a instância do Excel de forma invisível via COM.
- **Preflight VBA**: Verificação prévia de integridade via `Invoke-VbaCompilationCheck`.
- **Monitoramento de Fluxo**: Leitura em tempo real do log da macro `ExecutarProcessoCompleto`.
- **Orquestração Síncrona**: Dispara o bridge de WhatsApp (`Send-WhatsApp.ps1`) imediatamente após a conclusão bem-sucedida do processo Excel.

### 2. Workbook de Negócio (`Receitas Bloqueadas.xlsm`)
Contém o núcleo de inteligência em VBA e Power Query:
- Atualização determinística das conexões de dados externos.
- Normalização de campos e formatação para o padrão PT-BR.
- Geração de corpo de e-mail dinâmico em HTML.
- Persistência do snapshot final para transmissão via WhatsApp.

### 3. Bridge WhatsApp (`lib/Send-WhatsApp.ps1`)
Abstração PowerShell para o ecossistema Node.js:
- Verificação de pré-requisitos de ambiente (Runtime Node.js e dependências).
- **Gestão de Sessão**: Relançamento automático em modo `PAIRING` caso a sessão esteja expirada.
- **Controle de Concorrência**: Utilização de trava de arquivo (`.sendwhatsapp.lock`) para evitar múltiplas execuções simultâneas.

### 4. Distribuidor Node.js (`sendWhatsApp.js`)
Camada de integração via `whatsapp-web.js`:
- **Idempotência**: Garantida pela verificação do estado persistido em `whatsapp-state.json`.
- **Mecânica de Retry**: Sistema resiliente para lidar com instabilidades de conexão ou picos de carga.

---

## Operação e Diagnóstico

### Logs e Auditoria
- **Log de Processo**: `Logs/ReceitasBloqueadas.log` (Prefixos `[PS]` e `[VBA]`).
- **Log de Infraestrutura**: `sendWhatsApp-bootstrap.log`.

### Matriz de Exit Codes
| Código | Significado |
| :--- | :--- |
| **0** | Sucesso em todas as camadas |
| **7** | Workbook bloqueado para escrita (Read-Only) |
| **21** | Sessão WhatsApp expirada: requer re-pareamento manual |
| **23** | Bridge em Cooldown de retentativas |
| **40** | Erro de concorrência: lock ativo em outra instância |

---

## 🗺️ Roadmap Futuro
O núcleo de extração (Excel/VBA/PowerQuery) deste projeto está planejado para migração para a **Arquitetura Nativa (Python + Oracle)**, mantendo a entrega multicanal (Email + WhatsApp) via PowerShell e Node.js.
