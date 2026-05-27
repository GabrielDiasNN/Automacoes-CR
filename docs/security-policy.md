# Política de Segurança — Hub de Automações

> **Versão:** v7.0.0 | **Atualizado:** 19/05/2026
> **Referência complementar:** [`SECURITY.md`](../SECURITY.md)

---

## 1. Princípios Fundamentais

O Hub de Automações opera com os seguintes princípios de segurança não negociáveis:

| Princípio | Descrição |
|---|---|
| **Zero Trust** | Nenhum componente confia implicitamente em outro. Toda comunicação é autenticada e validada. |
| **Mínimo Privilégio** | Cada automação opera com as permissões mínimas necessárias para sua função. |
| **Zero Exposure** | Segredos nunca aparecem em logs, respostas de API, commits, mensagens de erro ou exemplos. |
| **Auditabilidade** | Toda ação administrativa gera trilha em `AuditLog`. Logs permitem reconstruir o fluxo sem reler o código. |
| **Idempotência** | Automações toleram reexecução sem efeitos colaterais indevidos (idempotência por hash MD5). |

---

## 2. Mandatos de Encoding (Soberania PT-BR)

> ⚠️ **REGRA ABSOLUTA — NÃO PODE SER VIOLADA**

| Extensão | Encoding Obrigatório | Motivo |
|---|---|---|
| `.ps1`, `.psm1` | **UTF-8 with BOM** | PowerShell 5.1 não reconhece acentuação sem BOM |
| `.py`, `.js`, `.json`, `.md`, `.sql`, `.html`, `.css`, `.txt` | **UTF-8 sem BOM** | Padrão universal; BOM causa problemas em parsers Python/Node |

**Validação automática:**
```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-SourceEncoding.ps1 -RootPath .
```

---

## 3. Gestão de Segredos

### Onde segredos podem residir

| Local | Permitido | Observação |
|---|---|---|
| `.env` (raiz do Orchestrator) | ✅ Sim | Nunca commitar. Listado no `.gitignore`. |
| Variáveis de ambiente do processo | ✅ Sim | Carregadas via `Lib-Config` no PowerShell |
| Arquivos de configuração por automação | ✅ Sim | Criptografia recomendada para senhas Oracle |
| Logs de execução | ❌ Nunca | Usar `sanitize_log_payload` antes de persistir |
| Respostas de API | ❌ Nunca | Endpoint `/api/system/env` retorna apenas conteúdo sanitizado |
| Mensagens de commit | ❌ Nunca | Violação = revogação imediata da credencial exposta |
| Comentários de código | ❌ Nunca | Usar referência ao `.env` em vez de valor literal |

### Higienizador de Logs

O módulo `Orchestrator/app/security.py` provê `sanitize_log_payload()`:

```python
from app.security import sanitize_log_payload

# Antes de persistir qualquer payload de log externo:
safe_payload = sanitize_log_payload(raw_payload)
```

**O que é mascarado automaticamente:**
- Chaves: `password`, `senha`, `token`, `secret`, `key`, `api_key`, `auth`, `credential`, `pwd`
- Valores com padrões de DSN Oracle (`//host:port/service`)
- Valores que correspondem a segredos conhecidos do `.env`

---

## 4. Gitleaks e Detecção de Segredos

O repositório usa **Gitleaks** via GitHub Actions para detectar segredos commitados acidentalmente.

### Configuração

O scan roda dentro do workflow `.github/workflows/governanca.yml`, em todo `push` e `pull_request` coberto pelo gate de governança.

### O que fazer quando um segredo for detectado

1. **NÃO** fechar o PR ou deletar o commit — isso não remove o segredo do histórico.
2. **Revogar imediatamente** a credencial exposta no sistema de origem (Oracle, WhatsApp, etc.).
3. **Gerar nova credencial** e atualizar o `.env` local.
4. **Purgar o histórico Git** usando `git filter-repo` ou abrir um incident report.
5. **Notificar** o responsável técnico via canal operacional.

### Regras de allow-list

Se um falso positivo for detectado, adicionar exceção documentada em `.gitleaks.toml`:
```toml
[[rules.allowlist]]
description = "Chave de exemplo em documentação"
paths = ["docs/security-policy.md"]
```

---

## 5. Autenticação e Autorização

### Dashboard e API

- O Dashboard e os endpoints da API requerem o header `X-Monitor-Token`.
- O token é configurado no `.env` e validado em cada requisição pelo middleware de autenticação.
- **Nunca** expor o token em URLs (query params), logs ou respostas de erro.

### Automações

- Scripts PowerShell usam `Lib-Config.psm1` para carregar variáveis do `.env` sem expô-las.
- Conexões Oracle usam credenciais por automação, nunca compartilhadas.
- Tokens de WhatsApp são carregados via variável de ambiente, nunca hardcoded.

---

## 6. Política de Rotação de Credenciais

| Credencial | Frequência de Rotação | Responsável |
|---|---|---|
| Token do Dashboard (`MONITOR_TOKEN`) | A cada 90 dias | Administrador do Hub |
| Senha Oracle por automação | A cada 180 dias | DBA responsável |
| Token WhatsApp/Puppeteer | Quando expirar ou vazar | Responsável técnico |

**Procedimento de rotação:**
1. Gerar nova credencial no sistema de origem.
2. Atualizar `.env` local.
3. Reiniciar o Orchestrator: `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
4. Verificar saúde via `GET /api/system/health`.
5. Registrar no `AuditLog` via `POST /api/system/audit` (se disponível).

---

## 7. Proteção de Dados Sensíveis

- **Dados de produção** (ex: NFs, OBs da Costa Rica Malhas) **nunca** devem ser usados em ambiente de desenvolvimento ou testes.
- Fixtures de teste usam dados fictícios ou anonimizados.
- Artefatos de execução (`/Orchestrator/Executions/`) devem ser purgados periodicamente via `POST /api/system/purge`.
- O endpoint de purge respeita `retention_days >= 7` por padrão (configurável via parâmetro).

---

## 8. Checklist de Segurança (Pre-Push)

- [ ] Nenhum segredo em texto claro no diff (`git diff --staged`)
- [ ] `.env` está no `.gitignore` e não está sendo commitado
- [ ] Logs sanitizados com `sanitize_log_payload` antes de persistir
- [ ] Encoding correto verificado (`Test-SourceEncoding.ps1`)
- [ ] Gitleaks não detectou nada no commit local

---

## 🧠 Gestão de Contexto (AI-Native)

- Este documento formaliza a política de segurança do Hub de Automações em `v7.0.0`.
- Atualize quando houver mudança na política de rotação, novos mecanismos de autenticação ou novos tipos de segredos gerenciados.
