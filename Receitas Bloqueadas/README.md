# Automacao - Receitas Bloqueadas (v2.3.2 - Pure Python + Resilience) 🌟

[⬅️ Voltar para o Hub Central](../README.md)

## Visão Geral

Este projeto automatiza o processamento, a consolidação e a distribuição das **Receitas Bloqueadas**. O sistema foi modernizado de VBA para **Python Nativo**, com foco em resiliência de banco de dados e distribuição inteligente via E-mail (Outlook) e WhatsApp (Node.js).

## Arquitetura Soberana (Resiliente)

A execução segue o pipeline de missão crítica:

`MonitorAutomacoes.ps1` (Monitor) -> `run.ps1` (Orquestrador)
  -> **Fase 1**: `processar_receitas.py` (Python)
     - Extração Oracle com **Retry Exponencial** via biblioteca `stamina`.
     - Lógica SQL desacoplada em `SQL-ReceitasBloqueadas.sql`.
     - Controle de estado (Diff) para detecção de Novas, Alteradas e Liberadas.
  -> **Fase 2**: Idempotência Unificada (PowerShell)
     - Verifica o hash gerado pela Fase 1. Se não houver mudanças, aborta E-mail e WhatsApp.
  -> **Fase 3**: Distribuição Multicanal
     - **E-mail**: Envio via Outlook (COM) com corpo HTML artístico.
     - **WhatsApp**: Bridge via `lib/WhatsApp-Core.js` (Node.js), acionado por `lib/Send-WhatsApp.ps1`, com protocolo de Ack e tratamento gracioso de erros de contato (LID).

---

## Engenharia de Resiliência

### 1. Banco de Dados (Oracle)
- **Retry Policy**: Em caso de falhas de rede (`ORA-00028`, `DPY-4011`), o sistema realiza até 3 tentativas automáticas com esperas crescentes.
- **Arquitetura**: O código Python é agnóstico à consulta, lendo o SQL de arquivo externo, permitindo ajustes de performance sem alteração no binário.

### 2. Idempotência Cruzada
Para evitar redundância e "fadiga de alertas", o sistema só dispara notificações se o estado das receitas bloqueadas for diferente do ciclo anterior. O estado é persistido em `receitas_state.json`.

### 3. WhatsApp Soberano
- **Graceful Degradation**: Erros de validação de número (LID) são tratados como avisos (`WARN`), permitindo que a automação finalize com sucesso mesmo se um contato específico estiver indisponível.
- **Session Management**: Bloqueio de concorrência (`.lock`) e reconexão automática.

---

## Operação e Diagnóstico

### Logs e Auditoria
- **Log Central**: `Logs/ReceitasBloqueadas.log` (formato padronizado).
- **Log WhatsApp**: `Logs/WhatsApp_Global.log` (detalhamento do bootstrap, envio e protocolo de Ack).
- **Orchestrator Online**: o detalhamento do bridge WhatsApp agora tambem deve aparecer em tempo real no modal de execucao do Orchestrator; o arquivo global continua sendo a trilha canônica do canal.

### Hardening do WhatsApp
- O bridge ativo é `lib/WhatsApp-Core.js`, chamado pelo wrapper PowerShell global.
- O bootstrap do cliente usa `protocolTimeout` ampliado para reduzir falhas de inicialização do Puppeteer em sessões lentas.
- A inicialização agora registra bootstrap, autenticação, desconexão e ACK para facilitar a triagem sem reenviar o e-mail.
- Falhas transitórias de inicialização fazem uma retentativa curta antes do erro definitivo.
- Erros de inicialização agora registram payload serializado e preview de stack, evitando diagnósticos vazios como `undefined`.
- Quando o e-mail conclui e o WhatsApp falha, a execução fecha com falha parcial do canal, preservando a idempotência do e-mail já entregue.

### Matriz de Exit Codes
| Código | Significado |
| :--- | :--- |
| **0** | Sucesso (ou supressão por idempotência) |
| **1** | Erro Fatal / Crash |
| **3** | Erro de Negócio (ex: Falha DB após retentativas) |
| **9** | Falha no Pre-Flight Check (Ambiente/Dependências) |
| **24** | Erro não tratado no Bridge WhatsApp |
| **40** | Concorrência Bloqueada (WhatsApp Lock) |

---

## 🛠️ Tecnologias
- **Python 3.12+** (Pandas, oracledb, stamina, openpyxl)
- **PowerShell 7.x** (Orquestração e Logging)
- **Node.js** (whatsapp-web.js)
- **Oracle DB** (ERP/SGT)

---

## 🧠 Gestão de Contexto (AI-Native) - Atualizado em 22/05/2026
- **Ajuste Fino de Datas (v2.3.2 - 22/05/2026):** Alteração da inteligência de estado para auditar e marcar receitas modificadas unicamente sob alteração da coluna "Data Bloqueio", mantendo silenciada a alteração da coluna "Data Última Prod." que causava falsos positivos de alteração no painel.
- **Obrigação:** Atualizar este documento após alterações na lógica de Retry (`stamina`), no motor de WhatsApp ou na lógica de Diff de receitas.
- **Objetivo:** Preservar o histórico de resiliência e evitar que a IA degrade os protocolos de segurança e idempotência.
