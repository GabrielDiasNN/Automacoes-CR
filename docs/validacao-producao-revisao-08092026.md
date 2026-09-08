# Validação em produção — revisão completa [1.3.81]

> **Status:** EXECUTADO em 08/09/2026, 16:00-16:15, na maquina Windows de producao.
> Os 7 passos rodaram. Resultado por item no checklist; achados na secao
> "Resultado da execucao".
> **Branch:** `claude/orchestrated-quality-loop-revision-kbi7b7` (15 commits)
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

- [x] 1. `ValidarAutomacoes.ps1 -OnlyGovernance` — 15 checks. **Reprovou na primeira vez**
      (Achado 1); passou depois da correção.
- [x] 2. `Invoke-Pester -Path .\lib\tests -CI` — 200 passed, 0 failed.
- [x] 3. `Test-PythonGovernance.ps1` — reprovou junto com o item 1; limpo após a correção.
- [x] 4. MT-02 — 2 ciclos, ambos `ExitCode=0`, 99 registros, nenhuma notificação.
      **Zero `retry.attempt`**: a mudança não foi exercida (Achado 5).
- [x] 5. OFST-06 — validado com dado real: o state **encolheu de 1 OB para 0**.
- [x] 6. Frontend: `npm ci` + build + coverage OK (76,09% stmts). E2E: 28 passed.
- [x] 7. Pre-commit hook — mensagem apareceu e o commit foi bloqueado. Ressalva no Achado 2.
- [x] Suíte Python de novo na máquina Windows: `cd Orchestrator; ..\.venv\Scripts\pytest`

      **Esperado no Windows: `1088 passed, 0 skipped`** — e não os `1082 passed, 6 skipped` do
      Linux. Os 6 skips são todos condicionais a NÃO estar no Windows: 4 em `test_path_safety.py`
      (`os.name != "nt"`), 1 em `test_revisao_consenso_onda2.py` (`sys.platform != "win32"`) e 1
      em `test_scaffold_governance.py` (`pwsh` ausente do PATH). Na sua máquina os seis rodam
      de verdade — é a primeira vez que essas asserções serão exercidas nesta revisão.

      **Se algum dos 6 falhar em vez de passar, é achado real**, não ruído de ambiente: são
      exatamente os testes que o container Linux nunca conseguiu executar. O de
      `test_scaffold_governance.py` exercita `Tools/New-Automation.ps1` ponta a ponta; os de
      `test_path_safety.py` cobrem contenção de caminho, que é código de segurança.

## Resultado da execução (08/09/2026)

Executado a partir de um worktree, com `powershell.exe` (5.1) e não `pwsh` — o runbook
pedia `pwsh`, mas o runtime de produção é o 5.1 deliberadamente, e validar em `pwsh`
validaria um runtime que não é o desta máquina.

**Resumo:** passos 1 e 3 reprovaram e foram corrigidos; 2, 6 e 7 passaram; 5 foi validado
com dado real de produção; 4 rodou sem regressão mas **não exerceu** a mudança que deveria
validar. Suíte Python no Windows: 1088 passed, 0 skipped, como previsto.

### Achado 1 — o branch não commitava (CORRIGIDO)

`Orchestrator/tests/test_ofst.py:751`, introduzido por esta própria revisão, reprovava o
gate do pre-commit em dois pontos: o mock `_fetch_obs_todas_rejeitadas` declarava `-> list`
(`type-arg` ausente sob `mypy --strict`) e tinha dois argumentos não usados (`W0613`).
Como o container Linux não tinha `pwsh`, nem o passo 1 nem o passo 3 rodaram lá — que é
exatamente a razão de este runbook existir.

### Achado 2 — core.hooksPath é absoluto (CORRIGÍVEL POR COMANDO, não por código)

`core.hooksPath` aponta para o `.githooks` do repositório principal, por caminho absoluto.
Worktrees rodam o hook da `main`, não o do branch em revisão — foi preciso forçar
`git -c core.hooksPath=...` para exercer o hook corrigido. Consequências: a correção do
`set -eu` só passa a valer após o merge, e todo branch que altere o hook não testa o
próprio hook por padrão.

**Não é um defeito do repositório, e sim drift da configuração local:** o script canônico
`Tools/Install-Hooks.ps1` já configura o valor RELATIVO (`.githooks`) e é idempotente. A
máquina ficou com o valor absoluto por configuração manual antiga. Correção:

```powershell
pwsh -File Tools\Install-Hooks.ps1
```

Nada a alterar em código — por isso este achado não aparece no diff.

### Achado 3 — run.ps1 não resolve o venv da raiz (CORRIGIDO)

O preflight do MT-02 falhou com `Path inacessivel: python.exe` ao rodar do worktree: o
`run.ps1` procura o venv relativo à raiz da própria árvore. É a mesma classe de problema
que o PR #56 resolveu para `Tools/`, mas os 6 `run.ps1` ficaram de fora. Contornado com
uma junction para o venv real, e depois **corrigido**: `Resolve-HubPythonExe`, em
`lib/Lib-Process.psm1`, replica a cadeia de `Get-PythonTool` do PR #56 — venv local
primeiro, senão o venv do repositório principal descoberto por
`git rev-parse --git-common-dir`. Os 6 `run.ps1` passaram a consumi-la.

Verificado sem o contorno: com a junction REMOVIDA, o pré-flight do MT-02 reporta
`OK: Path: python.exe`. Travado por `test_run_ps1_bootstrap_unit.py`, que também pegou uma
segunda ocorrência que a correção manual tinha deixado passar (`$venvActivate` em
`Receitas Bloqueadas/run.ps1`, atribuído e nunca usado — removido).

### Achado 4 — falha de preflight do MT-02 deixava execução órfã RUNNING (CORRIGIDO)

O ciclo que falhou no preflight (Achado 3) registrou `execution.start` na telemetria e, ao
abortar, **nunca registrou o fim**. A execução ficou `RUNNING` indefinidamente no
Orchestrator e passou a rejeitar a telemetria dos ciclos seguintes com
`conflict: já existe uma execução ativa para esta automação`. Os dois ciclos de MT-02
seguintes rodaram e concluíram, mas **sem telemetria registrada**.

**Correção do diagnóstico inicial:** eu havia descrito isto como valendo para as 6
automações. Vale só para o MT-02. As outras 5 saem por `Exit-WithCode`, que encaminha
para `Exit-AutomationWithCode` (lib/Lib-Logging.psm1) e fecha a telemetria antes do
`exit`. O MT-02 é o único que usa `exit` cru — por ter múltiplos pontos de saída, ele
trocou o helper por um `Write-Fim` local, que só emite o log estruturado e não fecha a
API.

**CORRIGIDO:** o ramo de abort do pré-flight passou a chamar `Close-ExecutionTelemetry`
com status `ERROR` antes do `exit 9`. Continua valendo para qualquer falha de pré-flight
em produção (Oracle fora, disco cheio, path quebrado), não só no worktree.

Travado por dois testes em `test_run_ps1_bootstrap_unit.py`: um específico do ramo do
MT-02, outro que exige das 6 que quem abre telemetria a feche.

### Achado 5 — o caminho de retry do MT-02 não era exercido (COBERTO POR TESTE)

A mudança de comportamento de produção desta revisão é o perfil de retry do MT-02, e ela
**não foi validada**. Os dois ciclos passaram sem nenhuma falha de rede, e `retry.attempt`
só é emitido quando há falha. Os ciclos provam que o caminho feliz não regrediu; não dizem
nada sobre o novo perfil de espera.

**COBERTO POR TESTE** em `test_montagem_terceirizados.py`, que é o que o ciclo contra o
Oracle real não substituía: `time.sleep` é interceptado, três `DatabaseError` são
forçadas e a espera acumulada é medida. Perfil atual: **1,67s**. Perfil legado
(30/120/0): **90,00s** — o teste é discriminante, não decorativo. Um segundo teste trava
o call site contra a reintrodução do override.

**O que o teste ainda não substitui:** ele mede a espera, não o comportamento do Oracle
sob carga real. O critério de rollback da seção 4 continua valendo — se o ciclo passar a
falhar em segundos onde antes esperava minutos, em horário de pico, o override existia
por uma razão. Isso só aparece observando produção ao longo de dias.

### Sobre o passo 5, que é onde a revisão se prova

O `ofst_state.json` de produção continha uma única OB, `186052`, notificada em
**05/09 05:00** — presa havia três dias. Partindo desse mesmo state, o ciclo com o código
novo emitiu `State reconciliado sem necessidade de envio` no step `commit` e gravou
`notified` vazio com `updated_at` do ciclo. A OB saiu da query (`Linhas retornadas: 0`) e o
state encolheu para vazio. No código antigo ela permaneceria indefinidamente, porque não
havia OB nova no mesmo ciclo para disparar a gravação. Nenhum `.tmp` residual foi deixado,
e o state de produção não foi tocado pelo ciclo do worktree.

### Achado 6 — o gate full-scan e o gate de diff discordaram (NÃO EXPLICADO)

`Orchestrator/tests/test_ofst_orb_parity_unit.py:177` tinha o mesmo defeito do Achado 1
(dois argumentos não usados num mock, `W0613`). O **hook de pre-commit**, que roda
`Test-PythonGovernance.ps1` apenas sobre os arquivos do diff, reprovou. O **full scan**
(`ValidarAutomacoes.ps1 -OnlyGovernance`) passou verde no mesmo commit, quatro execuções
seguidas, com o defeito presente.

O defeito foi corrigido, mas **a causa da discordância não foi determinada**. Nenhum dos
dois arquivos tem `# pylint: disable` de `unused-argument` no cabeçalho, e o full scan
havia pegado o defeito equivalente em `test_ofst.py:751` na primeira execução — ou seja,
não é que ele ignore a regra.

Enquanto isso não for explicado, **o full scan verde não é evidência suficiente**: rode
também um commit real (ou o hook) antes de considerar o gate satisfeito. Vale investigar
como `Test-PythonGovernance.ps1` agrupa os alvos nos dois modos.

## Achado conhecido, não corrigido

17 avisos de `# nosec B608` órfão em 13 linhas de `Produção Beneficimento/src`
(`contracts/_queries.py`, `_queries_common.py`, `detail.py`, `tingimento.py`,
`data/queries.py`, `sql_repository.py`) — `bandit` reporta
`nosec encountered (B608), but no failed test`. Mesma classe das entradas órfãs de allowlist
que esta revisão eliminou: supressão que não suprime nada hoje, mas suprimiria um finding
real amanhã. Não foi varrido porque o código monta SQL com f-string e a atribuição
linha-a-nó do bandit torna ambíguo se o finding real está em outra linha do mesmo statement.
Merece uma passada dedicada, não limpeza mecânica.
