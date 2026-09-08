# Validação em produção — revisão completa [1.3.81]

> **Status:** PENDENTE. Nenhum item abaixo foi executado.
> **Branch:** `claude/orchestrated-quality-loop-revision-kbi7b7` (14 commits)
> **Criado em:** 08/09/2026

## Por que este documento existe

A revisão [1.3.81] rodou num container **Linux sem `pwsh`, sem rota para o `dbprd` e sem
credenciais de Oracle**. Tudo que é Python foi executado e medido; tudo que é PowerShell,
Oracle ou navegador foi apenas **lido**. Este runbook lista o que falta exercer de verdade
antes do PR, com o comando exato, o resultado esperado e o critério de rollback.

Não confunda "suíte verde" com "validado": a suíte Python passa (1082 testes) e isso não
diz nada sobre os 88 scripts PowerShell nem sobre o comportamento contra o Oracle real.

## Ordem recomendada

Do mais barato ao mais caro, e do que bloqueia o commit para o que bloqueia o merge.

---

### 1. Governança local (bloqueia o commit)

```powershell
pwsh -File Tools\ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance
```

**Esperado:** os 15 checks passam.
**Por que importa:** é o gate do pre-commit e nenhum dos 15 rodou nesta revisão. Cobre
zero-trust, SQL, mypy/pylint, PowerShell, encoding, JSON, Playwright, manifesto,
arquitetura, datas, semântica, Node e schema de evento de log.
**Atenção especial:** o check de **arquitetura** lê `Tools/architecture-standard.rules.json`,
que esta revisão editou (removeu 4 entradas órfãs de allowlist). O check de **encoding**
cobre os `.ps1` alterados — `OBs Fluxo Sem Tingimento/run.ps1`,
`lib/tests/Python-Bootstrap.Tests.ps1` e `Tools/Test-ArchitectureStandard.ps1`; o BOM UTF-8
dos três foi conferido byte a byte, mas por leitura, não pelo gate.

### 2. Pester (bloqueia o merge)

```powershell
Invoke-Pester -Path .\lib\tests -CI
```

**Esperado:** verde.
**Por que importa:** `lib/tests/Python-Bootstrap.Tests.ps1` ganhou uma entrada nova
(`OBs Restricao Branco\extract_orb.py`), levando a trava de 5 para 6 scripts. As duas
asserções foram **simuladas fora do PowerShell** (normalização por remoção de whitespace,
igual ao `Get-NormalizedContent`) e passaram para os 6 — mas simulação não é execução.
**Se falhar:** a forma canônica do `extract_orb.py` diverge das outras cinco em algo que a
simulação não capturou. Não remova a entrada — investigue a divergência.

### 3. mypy e pylint (bloqueia o commit)

```powershell
pwsh -File Tools\Test-PythonGovernance.ps1 -RootPath .
```

**Esperado:** limpo.
**Por que importa:** é o mypy bloqueante do projeto (o do CI não é). Rodei `mypy --strict` e
`pylint` manualmente só nos arquivos alterados, com as flags que o script aplica; o passe
completo com o agrupamento por diretório que ele faz não foi exercido.

### 4. MT-02 contra o Oracle — **a única mudança de comportamento de produção**

```powershell
pwsh -File ".\Montagem de Terceirizados\run.ps1"
```

**O que mudou:** `Montagem de Terceirizados/extract_oracle.py` era o único dos 6 extratores
a sobrescrever `make_oracle_retry()` (`wait_initial=30.0`, `wait_max=120.0`,
`wait_jitter=0.0`). Agora usa os defaults, como as outras 5. O override era legado — MT-02 é
a automação mais antiga, escrita antes de `lib/python/oracle_retry.py` consolidar um perfil.

**O que observar no log:** eventos `retry.attempt`. O pior caso de espera entre tentativas
caiu de ~30s+60s+120s para ~0,1s+0,2s com teto de 5s e jitter de até 1s.

**Esperado:** ciclo completa normalmente. Sob rede saudável a diferença é invisível — o
retry só aparece quando há falha.

**CRITÉRIO DE ROLLBACK:** se o ciclo passar a **falhar em segundos** onde antes esperava
minutos (especialmente sob carga do Oracle, em horário de pico), o override existia por uma
razão real e deve voltar:

```python
_oracle_retry = make_oracle_retry(
    attempts=3, wait_initial=30.0, wait_max=120.0, wait_jitter=0.0
)
```

Se reverter, **registre a razão no call site** — foi justamente a ausência dela que motivou
a mudança. O `CircuitBreaker` externo (`fail_max=3`, `reset_timeout=60`) não foi alterado.

**Rodar mais de um ciclo**, de preferência incluindo um horário de pico. Um ciclo feliz não
exercita o caminho de retry.

### 5. OFST-06 — poda de state e a guarda nova

```powershell
pwsh -File ".\OBs Fluxo Sem Tingimento\run.ps1"
```

**O que mudou, em duas partes:**
- `extract_ofst.py` passa a gravar o state **podado** mesmo sem OB nova a notificar (antes,
  OB que saía da query nunca era removida se não coincidisse com uma OB nova no mesmo ciclo).
- Guarda nova: com `resumo.falhas` populado e `obs` vazio (linhas vieram e nenhuma sobreviveu
  à validação), aborta com `exit 1` **sem tocar no state**. Sem ela, o state ia a zero e todas
  as OBs já avisadas seriam re-anunciadas no grupo.

**O que conferir:** que `ofst_state.json` **encolhe** quando uma OB é montada e sai da query,
e que continua contendo as OBs ainda pendentes. Compare o arquivo antes e depois de um ciclo.

**A metade PowerShell não tem teste em nenhuma plataforma:** o `Move-Item $StateTmp $StateFile`
dentro do ramo `if ($pyResult.Idempotent)` do `run.ps1` é o que efetivamente commita o state
podado. Um teste Python lê o `.ps1` como texto e confirma que o bloco existe no ramo certo,
mas nada executa esse caminho. **Confira o `ofst_state.json` na mão neste primeiro ciclo.**

**Comparar com a irmã:** `OBs Restricao Branco` já tinha as duas coisas. Se OFST-06 se
comportar diferente de ORB-07 aqui, é regressão.

### 6. Frontend e E2E

```powershell
cd Dashboard; npm ci; npm run build; npm run test:coverage; cd ..
cd Orchestrator; ..\.venv\Scripts\pytest -m e2e -v; cd ..
```

**Por que importa:** nenhum rodou. O `Dashboard/` não foi alterado nesta revisão (só docs),
então o risco é baixo — mas os 28 testes E2E ficaram desselecionados o tempo todo e o
`Dashboard/dist/` precisa estar buildado para o FastAPI servir a SPA.

### 7. Pre-commit hook — confirmar que a mensagem voltou

`.githooks/pre-commit` tinha um bug: com `set -eu` (linha 7), o `if [ $? -ne 0 ]` após a
chamada ao `pwsh` era inalcançável. O commit já era bloqueado; só a mensagem
`[ERRO] Falha na validacao de Governanca. Commit abortado.` nunca aparecia.

**Como confirmar:** faça um commit que viole propositalmente alguma governança (ex.: um `.ps1`
salvo sem BOM, num branch descartável) e verifique que **a mensagem aparece** e o commit é
bloqueado. Depois desfaça.

---

## Checklist

- [ ] 1. `ValidarAutomacoes.ps1 -OnlyGovernance` — 15 checks
- [ ] 2. `Invoke-Pester -Path .\lib\tests -CI`
- [ ] 3. `Test-PythonGovernance.ps1` — mypy + pylint
- [ ] 4. MT-02 contra o Oracle (≥ 2 ciclos, um em horário de pico)
- [ ] 5. OFST-06 — conferir `ofst_state.json` antes/depois
- [ ] 6. Frontend (build + Vitest) e E2E Playwright
- [ ] 7. Pre-commit hook — mensagem de erro visível
- [ ] Suíte Python de novo na máquina Windows: `cd Orchestrator; ..\.venv\Scripts\pytest`

      **Esperado no Windows: `1088 passed, 0 skipped`** — e não os `1082 passed, 6 skipped` do
      Linux. Os 6 skips são todos condicionais a NÃO estar no Windows: 4 em `test_path_safety.py`
      (`os.name != "nt"`), 1 em `test_revisao_consenso_onda2.py` (`sys.platform != "win32"`) e 1
      em `test_scaffold_governance.py` (`pwsh` ausente do PATH). Na sua máquina os seis rodam
      de verdade — é a primeira vez que essas asserções serão exercidas nesta revisão.

      **Se algum dos 6 falhar em vez de passar, é achado real**, não ruído de ambiente: são
      exatamente os testes que o container Linux nunca conseguiu executar. O de
      `test_scaffold_governance.py` exercita `Tools/New-Automation.ps1` ponta a ponta; os de
      `test_path_safety.py` cobrem contenção de caminho, que é código de segurança.

## Achado conhecido, não corrigido

17 avisos de `# nosec B608` órfão em 13 linhas de `Produção Beneficimento/src`
(`contracts/_queries.py`, `_queries_common.py`, `detail.py`, `tingimento.py`,
`data/queries.py`, `sql_repository.py`) — `bandit` reporta
`nosec encountered (B608), but no failed test`. Mesma classe das entradas órfãs de allowlist
que esta revisão eliminou: supressão que não suprime nada hoje, mas suprimiria um finding
real amanhã. Não foi varrido porque o código monta SQL com f-string e a atribuição
linha-a-nó do bandit torna ambíguo se o finding real está em outra linha do mesmo statement.
Merece uma passada dedicada, não limpeza mecânica.
