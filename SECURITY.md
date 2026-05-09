# Security Governance: Automacoes Hub v4.0 (Hardened)

## Repository Security Philosophy
Este projeto opera sob a política de **Soberania Digital e Hardening de Acesso**. Na v4.0, implementamos camadas adicionais de proteção na API e no Motor de Execução para blindar o ambiente contra explorações locais e corrupção de dados.

---

## 1. Zero-Secrets & Timing-Safe Auth
**Regra de Ouro:** Credenciais são geridas via `.env` ou variáveis de ambiente.
- **Timing-Safe Authentication:** A API utiliza `hmac.compare_digest()` para comparar tokens de acesso. Isso impede que um atacante deduza a chave através da análise do tempo de resposta da CPU.
- **X-API-Key:** Todas as requisições administrativas exigem o header de segurança, validado em nível de middleware.

---

## 2. API Hardening (Anti-Exploit)
A v4.0 introduz validação rigorosa de payloads via Schemas Pydantic:
- **Anti-Path-Traversal:** O sistema bloqueia automaticamente qualquer tentativa de injetar caminhos como `../../` ou caracteres nulos em parâmetros de script ou downloads de artefatos.
- **ASCII-Safe Naming:** Nomes de automações são restritos a caracteres seguros, impedindo ataques de injeção de scripts (XSS) e corrupção de arquivos no sistema operacional.
- **Busy Timeout:** Configuração de 5000ms no banco de dados para prevenir negação de serviço (DoS) por travamento de tabelas.

---

## 3. Trilha de Auditoria (Audit Log)
Toda ação sensível é registrada permanentemente na tabela `audit_log`:
- **Criação/Edição/Deleção:** Registra o autor (IP/Sistema), o timestamp e o payload da alteração.
- **Execuções Manuais:** Registra quem disparou cada robô fora do agendamento.
- **Ações de Sistema:** Registra backups manuais e eventos de migração.

---

## 4. Isolamento e Resiliência
- **Taskkill Tree:** Ao interromper uma tarefa, o Hub encerra toda a árvore de processos descendentes, garantindo que nenhum robô fique "preso" consumindo recursos em background.
- **Integridade Referencial:** A ativação de `PRAGMA foreign_keys = ON` impede a deleção de automações que possuam histórico de execução, preservando a integridade estatística do hub.

---

## 5. Auditoria de Código (Pre-Commit)
O pipeline de desenvolvimento bloqueia:
1.  Vazamento de segredos via scanner de padrões.
2.  Ausência de validação em novos endpoints da API.
3.  Strings de conexão Oracle expostas em logs (Auto-Masking ativo).

---

## 🧠 Gestão de Contexto (AI-Native)
Este arquivo define as restrições de segurança v4.0.
- **Obrigação:** Qualquer alteração em middleware de auth ou validação de schemas deve ser refletida aqui.
- **Objetivo:** Garantir que a IA projete evoluções sempre dentro do perímetro de segurança soberana.

---
Mantido pela equipe de Automacoes & Antigravity AI
