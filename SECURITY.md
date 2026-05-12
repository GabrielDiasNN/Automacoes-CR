# Security Governance: Automações Hub v5.1.1 (Hardened)

## 1. Zero-Trust & API Security
- **Dynamic API Key**: Removidos segredos do código. O Dashboard solicita a chave ao administrador.
- **Timing-Safe Auth**: Uso de `hmac.compare_digest()` para mitigar ataques de timing na API.
- **Secure-by-Default**: Se `ORCHESTRATOR_API_KEY` não estiver no `.env`, o sistema gera um segredo UUID aleatório por sessão, bloqueando acessos não configurados.

## 2. Data & Execution Integrity
- **Anti-Path Traversal**: Validação estrita em `utils.py` e nos routers de download para impedir acesso a arquivos fora do escopo do projeto.
- **Worker Isolation**: Uso de `subprocess.CREATE_NO_WINDOW` e encerramento forçado de processos filhos para evitar persistência de robôs após cancelamento (Graceful Shutdown).
- **SQL Hardening**: Pragmas SQLite configurados para integridade referencial (`foreign_keys=ON`) e resiliência sob carga.

---
Mantido pela equipe de Automações & Antigravity AI
