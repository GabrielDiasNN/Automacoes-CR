# Checklist de Release — Hub de Automações

> **Versão:** v9.5.0 | **Atualizado:** 27/05/2026

---

## Visão Geral

Este checklist deve ser seguido **na íntegra** antes de qualquer promoção de versão para produção.
Use como artefato de auditoria: registre a data e o executor de cada item.

---

## 1. Gates de Qualidade Obrigatórios

### 1.1 Testes Automatizados

- [ ] `pytest tests/ -q` — **todos os testes passando** (zero falhas)
- [ ] Cobertura de código ≥ 60%: `pytest tests/ --cov=app --cov-fail-under=60 -q`
- [ ] Nenhum teste marcado como `xfail` inesperado

### 1.2 Qualidade de Código Python

- [ ] `black Orchestrator/app/ --check` — sem diferenças de formatação
- [ ] `isort Orchestrator/app/ --check-only` — imports ordenados
- [ ] `pylint Orchestrator/app/ --fail-under=7.5` — score acima do mínimo
- [ ] `mypy Orchestrator/app/ --ignore-missing-imports` — sem erros de tipo críticos
- [ ] `Tools/Get-QualitySnapshot.ps1 -BasePath .` — snapshot consolidado sem alerta estrutural inesperado

### 1.3 Governança e Encoding

- [ ] `Tools/ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance` — **0 erros**
- [ ] `Tools/Test-SourceEncoding.ps1 -RootPath .` — **0 violações de encoding**
- [ ] `Tools/Test-SkillsGovernance.ps1 -BasePath .` — skills consistentes
- [ ] `Tools/Test-AutomationCatalog.ps1 -RootPath .` — catálogo governado consistente
- [ ] `Tools/Test-SemanticGovernance.ps1 -RootPath .` — documentação viva, catálogo e dependências sem drift semântico
- [ ] `Tools/Test-NodeCommunications.ps1 -RootPath .` — contrato offline de WhatsApp/Node validado
- [ ] Nenhum caminho absoluto hardcoded em scripts de automação

### 1.4 Segurança

- [ ] Gitleaks sem alertas: `gitleaks detect --source . --no-git` (ou via CI)
- [ ] Nenhum segredo em texto claro no diff: `git diff main..HEAD`
- [ ] `.env` não está sendo commitado: `git ls-files .env` retorna vazio

---

## 2. Documentação e Changelog

- [ ] `CHANGELOG.md` atualizado com todas as mudanças desta versão
  - Usar categorias: `Adicionado`, `Corrigido`, `Removido`, `Alterado`, `Segurança`
  - Versão semântica incrementada no cabeçalho
- [ ] `README.md` reflete o estado atual (versão, features, links)
- [ ] `CONTEXT.md` atualizado com novas regras de negócio (se aplicável)
- [ ] `docs/ai-native-context-monitor.md` atualizado quando a mudança alterar estado operacional, arquitetura, governança ou contratos relevantes para agentes
- [ ] Runbooks e `automation.manifest.json` atualizados quando a mudança tocar automações de negócio
- [ ] `GEMINI.md` revisado apenas quando a mudança alterar regra local estável de bootstrap, encoding, skills ou validação

---

## 3. Evidência E2E Playwright (Obrigatória para UI)

> **Aplicável quando:** a mudança toca o Dashboard, rotas FastAPI consumidas pela UI, ou contratos front-back operacionais.

- [ ] Servidor Orchestrator iniciado: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- [ ] Playwright E2E executado contra `http://127.0.0.1:8000/dashboard/`
- [ ] Evidência gerada conforme [`playwright-e2e-evidence-template.md`](playwright-e2e-evidence-template.md)
- [ ] Evidência inclui:
  - [ ] URL real do servidor (não localhost mockado)
  - [ ] Screenshots das seções críticas alteradas
  - [ ] Console do browser sem erros JavaScript
  - [ ] Resultado `APROVADO` explícito
- [ ] Evidência salva em `docs/` com data: `playwright-e2e-<feature>-<DD-MM-YYYY>.md`

---

## 4. Commit Semântico de Release

### Formato do commit de versão

```
release(vX.Y.Z): <descrição resumida em PT-BR>

Changelog resumido:
- feat: ...
- fix: ...
- docs: ...
```

### Verificações antes do commit

- [ ] `git status` limpo (sem arquivos não versionados críticos)
- [ ] `git diff --staged` revisado — apenas mudanças intencionais
- [ ] Mensagem de commit segue o padrão semântico PT-BR
- [ ] Versão atualizada em `constants.py` (`ORCHESTRATOR_VERSION`)

---

## 5. Validação Pós-Deploy

Após publicar a nova versão:

- [ ] `GET /api/system/health` retorna `status: "ok"`
- [ ] `GET /api/system/version` confirma a nova versão
- [ ] `GET /api/system/diagnostics` sem findings críticos novos
- [ ] `GET /api/system/baseline` retorna `healthy`, `attention` ou `incident` coerente com o estado real
- [ ] `GET /api/system/history?hours=1` retorna snapshots recentes e `trend_summary` coerente
- [ ] `GET /api/portfolio/health` retorna resumo coerente do catálogo governado
- [ ] `GET /api/portfolio/drift` sem divergências inesperadas para automações promovidas
- [ ] `GET /api/portfolio/runbook/{catalog_id}` responde para automações com runbook cadastrado
- [ ] Dashboard renderiza sem erros de console
- [ ] Worker heartbeat ativo: `GET /api/system/worker/status` → `is_alive: true`
- [ ] APScheduler com jobs carregados: `GET /api/system/scheduler/jobs`

---

## 6. Protocolo de Rollback

Se qualquer validação pós-deploy falhar:

1. **Identificar** o componente com falha via `/api/system/diagnostics`.
2. **Isolar** — se for falha de banco: executar WAL checkpoint manual `POST /api/system/checkpoint`.
3. **Reverter** se necessário (apenas com aprovação explícita):
   ```powershell
   # ATENÇÃO: Operação destrutiva — requer aprovação explícita
   git revert HEAD --no-edit
   git push origin main
   ```
4. **Notificar** o canal operacional com o incident report.
5. **Registrar** o rollback no `CHANGELOG.md` com categoria `Revertido`.

---

## 7. Registro de Release

Preencha após a conclusão bem-sucedida:

| Campo | Valor |
|---|---|
| Versão | `vX.Y.Z` |
| Data | `DD/MM/YYYY` |
| Executor | `<nome>` |
| Testes | ✅ `X passed` |
| Governança | ✅ `0 erros` |
| E2E Playwright | ✅ `APROVADO` / N/A |
| Rollback necessário | Não |

---

## 🧠 Gestão de Contexto (AI-Native)

- Este checklist cobre o processo de release do Hub de Automações em `v9.5.0`.
- Atualize este checklist quando novos gates de qualidade forem adicionados ao pipeline.
- Registre estado operacional relevante para agentes em `docs/ai-native-context-monitor.md`, não em seções longas dentro de `GEMINI.md`.
