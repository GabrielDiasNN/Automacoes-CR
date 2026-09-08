# Workflow: Preflight e Quality Gate

Workflow padronizado para execucao deterministica da bateria de qualidade e governanca antes de submeter alteracoes, branches ou Pull Requests no Hub de Automacoes.

**Contrato deste playbook:** cada passo abaixo reproduz um job de
`.github/workflows/governanca.yml`. Se um comando aqui divergir do comando la',
o playbook esta errado — o CI e' a fonte de verdade, nao este arquivo. Um
preflight que cobre menos que o CI e' pior do que nenhum: ele devolve verde e o
merge quebra depois.

---

## 1. Quando Executar
- Antes de qualquer `git commit` ou `git push`.
- Apos conclusao de refatoracoes ou correcoes de bugs.
- Como verificacao final obrigatoria em tarefas de agente.

---

## 2. Ordem Sequencial de Execucao

### Passo 1: Governanca agregada (equivale ao job `governanca-agregada`)

Este e' o **mesmo** comando que o pre-commit hook e o CI executam. Sozinho ele
cobre as 15 validacoes — encoding, Zero-Trust, PowerShell (PSScriptAnalyzer +
catch tipado + verbos aprovados), SQL, mypy/pylint, JSON, manifesto,
arquitetura, datas, semantica, Node e schema de evento de log.

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance
```

Para validar apenas o que esta em stage (o modo que o pre-commit usa):

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance -StagedOnly
```

> **Nao substitua este passo por chamadas avulsas aos `Tools/Test-*.ps1`.**
> Ao passar caminhos manualmente para um desses scripts a partir de um shell
> POSIX, `-Paths a,b` chega como string unica, o loop interno pula todos os
> arquivos e o script devolve exit 0 sem ter analisado nada. O verde e' falso.
> Se precisar mesmo chamar um script isolado, passe um array PowerShell
> explicito (`-Paths @('a','b')`) e confirme que a saida lista cada arquivo
> com `Analisando: <caminho>`.

---

### Passo 2: Lint bloqueante Python (equivale ao job `lint-python`)

Ruff — os alvos precisam ser **exatamente** os do CI, incluindo as seis
automacoes de dominio e `.claude/skills`:

```powershell
.venv\Scripts\python -m ruff check Orchestrator/app Orchestrator/worker.py lib/python "Produção Beneficimento/src" "OBs Restricao Branco" "Receitas Bloqueadas" "Montagem de Terceirizados" "Receitas Emitidas" "OBs Paradas Fase" "OBs Fluxo Sem Tingimento" .claude/skills
```

Estilo (o CI aplica sobre os arquivos alterados; localmente vale rodar sobre o
mesmo conjunto):

```powershell
.venv\Scripts\python -m black --check Orchestrator .claude/skills
.venv\Scripts\python -m isort --check-only Orchestrator .claude/skills
```

Seguranca estatica:

```powershell
.venv\Scripts\python -m bandit -r Orchestrator/app Orchestrator/worker.py lib/python "Produção Beneficimento/src" "OBs Restricao Branco" "Receitas Bloqueadas" "Montagem de Terceirizados" "Receitas Emitidas" "OBs Paradas Fase" "OBs Fluxo Sem Tingimento" .claude/skills -ll
```

---

### Passo 3: Testes Python (equivale ao job `testes-python`)

```powershell
cd Orchestrator; ..\.venv\Scripts\pytest -m "not e2e"
```

---

### Passo 4: Testes PowerShell (equivale ao job `testes-powershell`)

Se a alteracao envolveu `.ps1`, `.psm1` ou integracoes em `lib/`:

```powershell
Import-Module Pester -RequiredVersion 5.7.1 -Force
Invoke-Pester -Path .\lib\tests -CI
```

---

### Passo 5: Frontend (equivale ao job `frontend`, se o diff tocar `Dashboard/`)

```powershell
npm run lint --prefix Dashboard
npm run test:coverage --prefix Dashboard
npm run build --prefix Dashboard
```

---

### Passo 6: Markdown (equivale ao job `markdown`, se o diff tocar `.md`)

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Fix-MarkdownStyle.ps1 -DryRun
```

---

### Passo 7: Inspecao de Worktree e Zero-Trust

Confira o estado do Git e certifique-se de que nenhum segredo (`.env`), banco local ou arquivo temporario sera comitado:

```powershell
git status -s
```

E confirme que o `CHANGELOG.md` foi atualizado — o CI reprova o PR sem entrada
correspondente (`Validar atualizacao do CHANGELOG`).

---

## 3. Criterio de conclusao

O preflight so' esta verde quando **todos** os passos aplicaveis ao diff
retornaram exit 0. Um passo pulado por nao se aplicar (ex.: Passo 5 sem
alteracao em `Dashboard/`) e' legitimo; um passo pulado por conveniencia, nao.
