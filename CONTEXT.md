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

## Security & Resilience (Zero Trust & Retry Layer)
- **Zero Secrets:** Credenciais geridas estritamente via `.env`.
- **Oracle Thick Mode:** Ativado globalmente para suportar senhas e sessões de alta segurança.
- **Resiliência Multinível (Fail-Fast / Recover-Slow):** Implementada via `Lib-Retry.psm1` (Backoff Exponencial) e `RetryQueue` em memória no Orquestrador.
- **Pre-Flight Rigoroso:** Verificação obrigatória antes da lógica de negócio:
    1. **Oracle (Thick Mode)**: Valida `oci.dll` e conectividade.
    2. **Paths**: Garante acesso ao `.venv` e dependências.
    3. **Zero Trust**: Carrega `.env` e valida variáveis essenciais.

## Knowledge Graph (8 SKILLs Consolidadas)
O repositório é governado pelas diretrizes em `.github/skills/`:
1. `ai-native-development-standard`: Padrões de codificação AI-First.
2. `automation-runtime-safety`: Zero Trust, Diagnósticos e Linter JSON.
3. `enterprise-orchestration-contract`: Fluxo ponta-a-ponta e ExecId.
4. `html-css-enterprise-standard`: Interface de Dashboard e Relatórios.
5. `nodejs-communications`: WhatsApp Soberano (Ack-Monitoring).
6. `powershell-automation-monitor`: Tipagem PowerShell estrita e Camada de Retry.
7. `python-oracle-migration`: Performance O(n) e BAN de `SELECT *`.
8. `vba-enterprise-core`: Padrões de interoperação (quando necessário).

## Absolute Rules (Anti-Regression)
- **Legacy Eradicated:** O uso de VBA, VBS ou Power Query foi completamente erradicado e é estritamente proibido. Todas as soluções devem ser 100% nativas (Soberanas) e aderentes ao Protocolo V.A.L.E.G.
- **Portability First:** Proibido caminhos absolutos. O projeto deve ser 100% móvel.
- **Explicit SQL:** Todas as consultas devem listar colunas nominalmente.
- **JSON Integrity:** Arquivos de config e estado devem passar pelo validador sintático no pre-commit.

---

## 🧠 Gestão de Contexto (AI-Native)
Este é o documento mestre de contexto cognitivo.
- **Obrigação:** Este arquivo **DEVE** ser a primeira leitura da IA em qualquer tarefa complexa e **DEVE** ser atualizado após mudanças em qualquer uma das 8 SKILLs ou na arquitetura Monitor-Trigger-Action.
- **Objetivo:** Minimizar o consumo de tokens e maximizar a precisão da IA através de um mapa mental técnico sempre atualizado.
