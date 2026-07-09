# Fluxo de Desenvolvimento — Hub de Automações

> **Versão:** v1.0.0 | **Atualizado:** 05/07/2026

---

## 1. Visão Geral

Este documento descreve o ciclo de desenvolvimento adotado no Hub de Automações, desde a criação de uma nova branch até o merge e o commit de release.
Todos os agentes (Codex, Gemini CLI, Antigravity) e colaboradores humanos devem seguir este fluxo.

---

## 2. Fluxo de Branches

```
main
  └── feat/<escopo>-<descricao-curta>   ← nova funcionalidade
  └── fix/<escopo>-<descricao-curta>    ← correção de bug
  └── docs/<escopo>-<descricao-curta>   ← documentação
  └── chore/<escopo>-<descricao-curta>  ← tarefas internas (deps, CI, config)
  └── refactor/<escopo>-<descricao-curta>  ← refatoração sem mudança comportamental
```

**Regras:**
- Nunca commitar diretamente em `main` sem aprovação explícita.
- Nomes de branch em **kebab-case**, sem acentuação.
- Exemplos: `feat/dashboard-sla-por-automacao`, `fix/worker-heartbeat-timeout`.

---

## 3. Convenção de Commits (PT-BR Semântico)

Padrão baseado em [Conventional Commits](https://www.conventionalcommits.org/):

```
<tipo>(<escopo>): <descrição imperativa em PT-BR>

[corpo opcional — por que, não o que]
[referência de issue opcional]
```

### Tipos Válidos

| Tipo | Uso |
|---|---|
| `feat` | Nova funcionalidade visível |
| `fix` | Correção de bug |
| `docs` | Atualização de documentação |
| `refactor` | Refatoração sem mudança de comportamento |
| `test` | Adição/ajuste de testes |
| `chore` | Tarefas de manutenção (deps, CI, scripts) |
| `perf` | Melhoria de performance |
| `sec` | Correção de segurança ou Zero Trust |

**Exemplos:**
```
feat(dashboard): adiciona painel de fila por prioridade e badge de SLA
fix(worker): corrige condição de race no requeue sob queue_group ativo
docs(governance): adiciona política de segurança e checklist de release
chore(deps): atualiza fastapi para 0.115.x e stamina para 1.2.0
```

---

## 4. Ciclo de Qualidade Local (Gates Obrigatórios)

Antes de qualquer `git push`, execute a sequência:

```powershell
# 1. Formatação Python
& ".venv\Scripts\python.exe" -m black Orchestrator/app/ Orchestrator/tests/ --line-length 88

# 2. Ordenação de imports
& ".venv\Scripts\python.exe" -m isort Orchestrator/app/ Orchestrator/tests/

# 3. Lint estático
& ".venv\Scripts\python.exe" -m pylint Orchestrator/app/ --fail-under=7.5

# 4. Verificação de tipos
& ".venv\Scripts\python.exe" -m mypy Orchestrator/app/ --ignore-missing-imports

# 5. Suite de testes (a partir do diretório Orchestrator/)
& ".venv\Scripts\python.exe" -m pytest tests/ -q

# 6. Validação de governança canônica
pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/ValidarAutomacoes.ps1 -OnlyGovernance
```

**Todos os gates devem passar** antes de abrir PR ou commitar em `main`.

---

## 5. Uso de Lockfiles e Atualização de Dependências

- O arquivo `requirements.txt` (e/ou `requirements-dev.txt`) é a fonte canônica de dependências.
- Para adicionar uma dependência:
  ```powershell
  # Adicione ao requirements.txt com versão fixada (ex: fastapi==0.115.5)
  # Depois instale:
  & ".venv\Scripts\pip.exe" install -r requirements.txt
  ```
- **Nunca** instalar pacotes sem atualizar o `requirements.txt`.
- Ao atualizar versões, rodar toda a suite de testes antes de commitar.

---

## 6. Processo de Criação de Nova Automação

1. **Criar o diretório** da automação em `Automacoes/<nome-do-robo>/`.
2. **Criar o script principal** (`.ps1` com UTF-8 BOM, `.py` com UTF-8 sem BOM).
3. **Registrar no Orchestrator** via `POST /api/automations` com payload JSON.
4. **Configurar `sla_minutes`** se a automação tiver SLA definido.
5. **Configurar `queue_group`** se a automação pertencer a um grupo operacional.
6. **Testar** com `dry-run` antes de habilitar em produção.
7. **Documentar** com runbook baseado em `docs/templates/automation-runbook-template.md`.
8. **Atualizar** `docs/automation-criticality-map.md` com o novo SLA.

---

## 7. Gates Obrigatórios Antes do Push

Execute o validador canônico:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance
```

O validador verifica:
- Encoding correto de todos os arquivos (UTF-8 BOM para `.ps1`, UTF-8 sem BOM para demais).
- Ausência de caminhos absolutos hardcoded.
- Consistência das skills (`.github/skills/` vs `.gemini/skills/`).
- Ausência de segredos expostos.
- Tempo por etapa e modo de seleção governada do ciclo local, para triagem rápida de gargalos.

**Zero erros é obrigatório.**

---

## 8. Mudanças de Dashboard/UI

Para qualquer mudança em `Dashboard/` ou nas rotas FastAPI consumidas pela UI:

1. Implementar a mudança.
2. Iniciar o Orchestrator real: `uvicorn app.main:app --host 127.0.0.1 --port 8000`
3. Rodar a suíte Playwright E2E: ver [playwright-e2e-standard.md](playwright-e2e-standard.md).
4. Gerar evidência conforme [playwright-e2e-evidence-template.md](playwright-e2e-evidence-template.md).
5. Incluir evidência no PR.

> A validação E2E é **a última etapa obrigatória** para mudanças de UI.

---

## 🧠 Gestão de Contexto (AI-Native)

- Este documento reflete o fluxo de desenvolvimento do Hub de Automações em `v9.3.0`.
- Atualize quando houver mudança de convenção de commit, de pipeline CI ou de gates obrigatórios.
