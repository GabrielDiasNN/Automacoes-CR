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

## Knowledge Graph (8 SKILLs Consolidadas)
Consulte `.github/skills/` para as diretrizes canônicas, que agora governam rigidamente a base:
- `enterprise-orchestration-contract`: Fluxo ponta-a-ponta e ExecId.
- `automation-runtime-safety`: Zero Trust, Diagnósticos e Logs limpos.
- `python-oracle-migration`: Uso de vetorização O(n), Type Hints e restrição total ao `SELECT *`.
- `powershell-automation-monitor`: Tipagem PowerShell estrita e restrição de Try/Catch genérico.
- `nodejs-communications`: Automação do WhatsApp e bridges `.bat`.
- `vba-enterprise-core`: Segurança no VBE, Exportação PT-BR e COM do Outlook.
- `html-css-enterprise-standard`: Contratos de layout e dashboard.
- `ai-native-development-standard`: Regras de frontmatter JSON em todos os scripts.

## Absolute Rules (Anti-Regression)
- **Portability First:** É expressamente proibido comitar arquivos com caminhos absolutos (ex: `C:\...`). O projeto foi desenhado para operar puramente em variáveis e caminhos relativos (`.\` ou `$PSScriptRoot`). Existe um Linter de pre-commit blindando o repositório contra isso.
