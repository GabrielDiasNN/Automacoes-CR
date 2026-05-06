# Cognitive Context: Automacoes Hub

## Repository Philosophy
Este repositório é um ecossistema de automações **AI-Native**, 100% migrado para uma arquitetura moderna e soberana. O projeto opera sob o "Padrão Ouro" de engenharia, priorizando resiliência de protocolo e soberania de ambiente.

## System Architecture
O hub opera sob o modelo **Monitor-Trigger-Action** com stack 100% nativa:
- **Monitor:** `MonitorAutomacoes.ps1` coordena agendamentos e saúde dos robôs.
- **Orquestração:** Scripts `run.ps1` (PowerShell) gerenciam o fluxo e a idempotência cruzada.
- **Data Engine (Soberano):** Python (Pandas/OracleDB Thick) processa dados com carregamento direto de ambiente via `python-dotenv`.
- **Communication (Soberano):** Node.js com protocolo de **Ack Monitoring** para WhatsApp e Outlook COM para e-mails institucionais.

## AI Interoperability Standards
1.  **Contextual Headers:** Metadados JSON em todos os arquivos fonte.
2.  **ASCII-Safe & Base64 Bridge:** Garantia de integridade PT-BR e imunidade a variações de encoding do sistema operacional.
3.  **Strict Idempotency:** Hashes MD5 (`last_hash`) governam a supressão de notificações redundantes em todos os canais.

## Security & Resilience (Zero Trust)
- **Zero Secrets:** Credenciais geridas estritamente via `.env`.
- **Oracle Thick Mode:** Ativado globalmente para suportar senhas e sessões de alta segurança.
- **Auto-Recovery:** Recuperação automática de quedas de sessão de banco e reautenticação visual de WhatsApp.

## Knowledge Graph (8 SKILLs Consolidadas)
O repositório é governado pelas diretrizes em `.github/skills/`:
- `enterprise-orchestration-contract`: Fluxo ponta-a-ponta e ExecId.
- `automation-runtime-safety`: Zero Trust, Diagnósticos e **Linter JSON**.
- `python-oracle-migration`: Performance O(n) e BAN de `SELECT *`.
- `powershell-automation-monitor`: Tipagem PowerShell estrita e catch específico.
- `nodejs-communications`: WhatsApp Soberano (Ack-Monitoring).

## Absolute Rules (Anti-Regression)
- **Legacy Freeze:** Proibido uso de VBA ou Power Query para novas demandas.
- **Portability First:** Proibido caminhos absolutos. O projeto deve ser 100% móvel.
- **Explicit SQL:** Todas as consultas devem listar colunas nominalmente.
- **JSON Integrity:** Arquivos de config e estado devem passar pelo validador sintático no pre-commit.
