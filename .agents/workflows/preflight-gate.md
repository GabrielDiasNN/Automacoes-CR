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
>
> Passar um array PowerShell explicito **nao resolve isso sozinho**: um array
> so' sobrevive intacto em `-Paths` quando o script e' chamado **no mesmo
> processo** (`& Tools\Test-PowerShellGovernance.ps1 -Paths @('a','b')`).
> Cruzar para um `pwsh -File ... -Paths @('a','b')` — a forma que TODO comando
> deste playbook usa — gera um novo processo, e a array colapsa para o
> PRIMEIRO elemento apenas (confirmado: `Count` vira 1, o resto e' descartado
> em silencio). O mesmo verde falso, por um mecanismo diferente. Se precisar
> mesmo chamar um script isolado, use `&` sem `-File` na mesma sessao — nunca
> `pwsh -File` — e confirme que a saida lista **cada** arquivo esperado com
> `Analisando: <caminho>`, nao so' o primeiro.

Este passo tambem cobre o job `conformidade-log`: `Invoke-LogConformidadeCheck`
roda dentro do mesmo `ValidarAutomacoes.ps1` (independente de `-OnlyGovernance`)
sempre que houver arquivo PowerShell operacional elegivel no diff.

---

### Passo 2: Segredos vazados (equivale ao job `gitleaks`)

Bloqueante e roda em **todo** PR, independente do que o diff toca — sem
excecao por tipo de arquivo, ao contrario dos demais passos. Se este passo for
pulado, o preflight nao cobre a mesma superficie que o CI.

```powershell
gitleaks git --config .gitleaks.toml -v
```

Se o binario `gitleaks` nao estiver instalado nesta maquina (nao faz parte do
`.venv` nem de `requirements*.txt` — e' um binario Go, nao um pacote Python),
rode via Docker com uma tag **8.x fixada** (nunca `latest`: a v9 remove o
comando `detect` e muda a superficie; o job do CI usa `gitleaks-action@v3`,
que embarca a serie 8.x):

```powershell
docker run --rm -v "${PWD}:/repo" zricethezav/gitleaks:v8.24.3 git --config /repo/.gitleaks.toml -v /repo
```

Sem `gitleaks` nem Docker disponiveis localmente, este passo fica **pendente**
— nao marque o preflight como equivalente ao CI, va direto para o PR e deixe o
job `gitleaks` do CI ser a primeira execucao real desta checagem.

---

### Passo 3: Lint bloqueante Python (equivale ao job `lint-python`)

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

### Passo 4: Testes Python (equivale ao job `testes-python`)

```powershell
cd Orchestrator; ..\.venv\Scripts\pytest -m "not e2e"
```

`-m "not e2e"` exclui deliberadamente os testes Playwright — e' o mesmo filtro
do `pytest.ini`. Este passo **nao** cobre o job `testes-e2e`; use o Passo 5
para isso. Nao trate "Passo 4 verde" como "E2E passou".

---

### Passo 5: Testes E2E Playwright (equivale ao job `testes-e2e`)

Dispara no CI sempre que o diff toca Python OU JS/TS (`has_python == 'true' ||
has_js == 'true'`) — ou seja, a maioria dos PRs de codigo. Exige o Dashboard
buildado, porque o FastAPI serve a SPA a partir de `Dashboard/dist/`:

Rode **da raiz do repositorio**, como o job `testes-e2e` do CI — `$env:PYTHONPATH
= "Orchestrator"` so' resolve a partir da raiz; de dentro de `Orchestrator/` ele
apontaria para `Orchestrator/Orchestrator/`, que nao existe:

```powershell
npm run build --prefix Dashboard
$env:PYTHONPATH = "Orchestrator"
.venv\Scripts\pytest "Orchestrator\tests\test_e2e_dashboard.py" -v -m e2e --basetemp="Orchestrator\tests\e2e-evidence"
```

Se os browsers do Playwright ainda nao estiverem instalados nesta maquina:

```powershell
.venv\Scripts\python -m playwright install chromium
```

Registre a evidencia com `Tools/Test-PlaywrightEvidence.ps1` conforme
`docs/playwright-e2e-standard.md` — o Passo 1 (governanca agregada) ja invoca
esse checker sobre os artefatos elegiveis, mas so' depois que a suite acima
os gerou.

---

### Passo 6: Testes PowerShell (equivale ao job `testes-powershell`)

Se a alteracao envolveu `.ps1`, `.psm1` ou integracoes em `lib/`:

```powershell
Import-Module Pester -RequiredVersion 5.7.1 -Force
Invoke-Pester -Path .\lib\tests -CI
```

---

### Passo 7: Frontend (equivale ao job `frontend`, se o diff tocar `Dashboard/`)

```powershell
npm run lint --prefix Dashboard
npm run test:coverage --prefix Dashboard
npm run build --prefix Dashboard
```

---

### Passo 8: Markdown (equivale ao job `markdown`, se o diff tocar `.md`)

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Fix-MarkdownStyle.ps1 -DryRun
```

---

### Passo 9: Inspecao de Worktree e Zero-Trust

Confira o estado do Git e certifique-se de que nenhum segredo (`.env`), banco local ou arquivo temporario sera comitado:

```powershell
git status -s
```

E confirme que o `CHANGELOG.md` foi atualizado — o CI reprova o PR sem entrada
correspondente (`Validar atualizacao do CHANGELOG`).

---

## 3. Criterio de conclusao

O preflight so' esta verde quando **todos** os passos aplicaveis ao diff
retornaram exit 0. Um passo pulado por nao se aplicar (ex.: Passo 7 sem
alteracao em `Dashboard/`) e' legitimo; um passo pulado por conveniencia, nao —
em particular o Passo 5 (E2E): ele se aplica a quase todo PR de codigo
(qualquer diff em Python ou JS/TS), entao "nao da' tempo" nao e' motivo valido
para pula-lo. O Passo 2 (gitleaks) pendente por falta de binario/Docker local
e' a unica excecao tolerada — documente que ficou pendente e deixe o CI ser a
primeira execucao real.
