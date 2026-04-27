# Cognitive Context: Automacoes Hub

## Repository Philosophy
Este repositorio e um ecossistema de automacoes "AI-Native". Ele foi projetado para ser mantido e evoluido por Inteligencia Artificial, mantendo padroes rigorosos de seguranca e confiabilidade empresarial (Padrao Ouro).

## System Architecture
O hub opera sob o modelo **Monitor-Trigger-Action**:
- **Monitor:** `MonitorAutomacoes.ps1` coordena agendamentos e saude dos robos com diagnostico preventivo (Pre-Flight).
- **Bridges:** Scripts `run.ps1` gerenciam a interoperabilidade, suportando estrategias de **Fallback** (Nativo -> Hibrido).
- **Runtimes:** Uso harmonioso de Excel (Bypass de politica Oracle), Python (Inteligencia e UI) e Node.js (Comunicacoes Moveis).

## AI Interoperability Standards (Skill: ai-native-development-standard)
1.  **Contextual Headers:** Todos os arquivos fonte possuem metadados JSON para auto-identificacao por LLMs.
2.  **ASCII-Safe Core:** As mensagens de log no codigo-fonte utilizam apenas ASCII ou sequencias de escape, garantindo que o codigo nao corrompa independente do encoding do editor.
3.  **Base64 Bridge Protocol:** A troca de strings entre camadas utiliza Base64 para garantir 100% de integridade no Portugues Brasileiro (PT-BR).
4.  **Traceability:** `ExecId` e a chave mestra de correlacao universal em logs, e-mails e banco de dados (DNA de Correlacao SQL).

## Security & Resilience
- **Zero Secrets:** Credenciais geridas via `.env` e variaveis de ambiente de processo.
- **Auto-Masking:** Protecao proativa de dados sensiveis em logs via `Lib-Logging.psm1`.
- **Zombie Prevention:** Gestao rigorosa de instancias COM (Outlook/Excel) com liberacao explicita de memoria.

## Knowledge Graph (Skills)
Consulte `.github/skills/` para as diretrizes canonicas:
- `log-standardization`: Regras de escrita e transporte de logs.
- `automation-execution-contract`: Contratos de ID e Exit Codes.
- `enterprise-local-automation-stack`: Padroes da stack local Windows.
