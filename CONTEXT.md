# Cognitive Context: Automacoes Hub

## Repository Philosophy
Este repositório é um ecossistema de automações **AI-Native**, 100% migrado para uma arquitetura moderna e soberana. O projeto abandonou formalmente o uso de VBA e Power Query como motores ativos, operando agora sob padrões rigorosos de segurança e confiabilidade industrial (Padão Ouro).

## System Architecture
O hub opera sob o modelo **Monitor-Trigger-Action** com stack 100% nativa:
- **Monitor:** `MonitorAutomacoes.ps1` coordena agendamentos e saúde dos robôs com diagnóstico preventivo (Pre-Flight).
- **Orquestração:** Scripts `run.ps1` em PowerShell gerenciam o fluxo, garantindo interoperabilidade entre camadas.
- **Data Engine:** Python (Pandas/OracleDB) processa dados complexos com performance O(n) e soberania técnica (Zero dependência de Excel).
- **Communication:** Node.js (WhatsApp Web Headless) e Outlook COM (PowerShell) realizam a entrega multicanal.

## AI Interoperability Standards (Skill: ai-native-development-standard)
1.  **Contextual Headers:** Todos os arquivos fonte possuem metadados JSON para auto-identificação por LLMs.
2.  **ASCII-Safe Core:** Mensagens de log utilizam sequências de escape, garantindo integridade de código independente do encoding.
3.  **Base64 Bridge Protocol:** Transporte de strings acentuadas entre PowerShell/Python/Node via Base64 para garantir integridade PT-BR.
4.  **Universal Traceability:** `ExecId` é a chave mestra de correlação em logs, e-mails e telemetria.

## Security & Resilience (Zero Trust)
- **Zero Secrets:** Credenciais geridas estritamente via `.env` e variáveis de ambiente.
- **Idempotency State:** Controle de estado via arquivos JSON (`*_state.json`) para evitar spam e garantir envios apenas em mudanças.
- **Auto-Masking:** Proteção automática de dados sensíveis em logs via `Lib-Logging.psm1`.

## Knowledge Graph (8 SKILLs Consolidadas)
O repositório é governado por 8 diretrizes canônicas em `.github/skills/`:
- `enterprise-orchestration-contract`: Fluxo ponta-a-ponta e ExecId.
- `automation-runtime-safety`: Zero Trust, Diagnósticos e Logs limpos.
- `python-oracle-migration`: Vetorização O(n), Type Hints e BAN de `SELECT *`.
- `powershell-automation-monitor`: Tipagem PowerShell estrita.
- `nodejs-communications`: Automação do WhatsApp e bridges `.bat`.
- `vba-enterprise-core`: **(Arquivado)** Padrões para o legado mantido em `Legacy/`.
- `html-css-enterprise-standard`: Contratos de layout e dashboard.
- `ai-native-development-standard`: Regras de metadados JSON.

## Absolute Rules (Anti-Regression)
- **Legacy Freeze:** É proibido criar novas funcionalidades em VBA ou Power Query. Qualquer evolução deve ser feita em Python/PS.
- **Portability First:** Proibido caminhos absolutos (ex: `C:\...`). Utilize `.\` ou variáveis dinâmicas.
- **Explicit SQL:** Proibido `SELECT *`. Colunas devem ser listadas nominalmente para performance e previsibilidade.
