# Security Governance: Automações Hub v1.0.0 (Hardened)

## 1. Zero-Trust & API Security
- **Dynamic API Key**: Removidos segredos do código. O Dashboard solicita a chave ao administrador.
- **Timing-Safe Auth**: Uso de `hmac.compare_digest()` para mitigar ataques de timing na API.
- **Secure-by-Default**: Se `ORCHESTRATOR_API_KEY` não estiver no `.env`, o sistema gera um segredo UUID aleatório por sessão, bloqueando acessos não configurados.

## 2. Data & Execution Integrity
- **Anti-Path Traversal**: Validação estrita em `utils.py` e nos routers de download para impedir acesso a arquivos fora do escopo do projeto.
- **Worker Isolation**: Uso de `subprocess.CREATE_NO_WINDOW` e encerramento forçado de processos filhos para evitar persistência de robôs após cancelamento (Graceful Shutdown).
- **SQL Hardening**: Pragmas SQLite configurados para integridade referencial (`foreign_keys=ON`) e resiliência sob carga.
- **Diagnóstico Sem Segredos**: Achados operacionais de `/api/system/diagnostics` devem expor severidade, componente e ação sugerida sem revelar credenciais, caminhos sensíveis fora do contrato ou conteúdo de `.env`.
- **Contrato Versionado Sem Segredos**: `contract_version`, `checks` e `recovery` podem orientar front-end e operação, mas não devem carregar credenciais, conteúdo de `.env` ou detalhes de infraestrutura fora do contrato público.
- **Mutação Administrativa Validada**: Alterações de `.env` e `schedule` devem passar por validação pré-save antes de atingir disco ou banco.
- **Preflight de Automação**: `script_path`, `queue_group`, canais e agenda devem ser validados em uma etapa única de preflight antes de criar ou atualizar automações.
- **Retry Auditável**: Requeue de execuções deve preservar trilha de auditoria, origem da execução, motivo operacional e limite explícito de tentativas.
- **Ações Diagnósticas Sem Segredo**: `action_code`, `operator_actions`, hotspots e impactos operacionais podem orientar o operador, mas não devem expor conteúdo de `.env`, credenciais, caminhos sensíveis fora do contrato ou payloads de negócio.
- **Bloqueio por Grupo Operacional**: Requeue deve respeitar execução ativa no mesmo `queue_group`, evitando duplicidade de canal, banco ou recurso externo compartilhado.
- **Ownership do Worker**: Metadados como `worker_instance_id`, `worker_pid` e `claimed_at` podem ser expostos para triagem operacional, mas nunca devem carregar segredos, argumentos de processo sensíveis ou conteúdo bruto de ambiente.
- **Histórico Operacional Sanitizado**: Snapshots de `system_health_snapshots` devem registrar somente sinais agregados de saúde, filas, WAL e SLOs, sem payloads de negócio ou conteúdo sensível.
- **Evidência E2E Auditável**: Evidências Playwright devem registrar apenas metadados operacionais, sem API keys, credenciais, payloads sensíveis ou conteúdo bruto de logs.
- **Catálogo e Runbook Sem Path Arbitrário**: `/api/portfolio/health` e `/api/portfolio/drift` expõem apenas metadados sanitizados do catálogo; a leitura de runbook ocorre por `catalog_id` validado, nunca por caminho arbitrário fornecido pelo cliente.
- **Beneficiamento Sem Oracle em GET**: endpoints `/api/beneficiamento/*` devem ler apenas snapshots locais sanitizados. Conexões Oracle, credenciais e DSN permanecem restritos ao runner de refresh e nunca devem aparecer em respostas, logs de Dashboard ou arquivos versionados.
- **Timeout Oracle como Guardrail de Segurança Operacional**: se o `call_timeout` não for aplicado pelo client Oracle, o health do Beneficiamento deve sinalizar `attention`; isso não deve ser mascarado como sucesso pleno.

---
Mantido pela equipe de Automações & Antigravity AI
