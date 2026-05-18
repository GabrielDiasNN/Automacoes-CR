# Security Governance: Automações Hub v6.5.2 (Hardened)

## 1. Zero-Trust & API Security
- **Dynamic API Key**: Removidos segredos do código. O Dashboard solicita a chave ao administrador.
- **Timing-Safe Auth**: Uso de `hmac.compare_digest()` para mitigar ataques de timing na API.
- **Secure-by-Default**: Se `ORCHESTRATOR_API_KEY` não estiver no `.env`, o sistema gera um segredo UUID aleatório por sessão, bloqueando acessos não configurados.

## 2. Data & Execution Integrity
- **Anti-Path Traversal**: Validação estrita em `utils.py` e nos routers de download para impedir acesso a arquivos fora do escopo do projeto.
- **Worker Isolation**: Uso de `subprocess.CREATE_NO_WINDOW` e encerramento forçado de processos filhos para evitar persistência de robôs após cancelamento (Graceful Shutdown).
- **SQL Hardening**: Pragmas SQLite configurados para integridade referencial (`foreign_keys=ON`) e resiliência sob carga.
- **Diagnóstico Sem Segredos**: Achados operacionais de `/api/system/diagnostics` devem expor severidade, componente e ação sugerida sem revelar credenciais, caminhos sensíveis fora do contrato ou conteúdo de `.env`.
- **Mutação Administrativa Validada**: Alterações de `.env` e `schedule` devem passar por validação pré-save antes de atingir disco ou banco.
- **Retry Auditável**: Requeue de execuções deve preservar trilha de auditoria, origem da execução, motivo operacional e limite explícito de tentativas.
- **Ações Diagnósticas Sem Segredo**: `action_code`, `operator_actions`, hotspots e impactos operacionais podem orientar o operador, mas não devem expor conteúdo de `.env`, credenciais, caminhos sensíveis fora do contrato ou payloads de negócio.

---
Mantido pela equipe de Automações & Antigravity AI
