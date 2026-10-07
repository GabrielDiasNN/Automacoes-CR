# Mapa das violações de ruff fora do gate (07/10/2026)

Inventário das violações dos diretórios que o `ruff` e o `bandit` bloqueantes do CI **não** cobrem (ver skill `ci-gates` e o comentário em `.github/workflows/governanca.yml`). Gerado com `ruff check <diretórios> --output-format json`, regras `E W F I UP B C4 SIM` de `pyproject.toml`. Objetivo: dimensionar a correção antes de ampliar o escopo do gate.

**Total: 72 violações, 42 com autofix seguro.** (O comentário do workflow dizia 70: duas entradas novas em arquivos de teste desde a última contagem.) Nenhuma está em arquivo novo desta sessão. O bandit (`-ll`) acha 1 achado Medium: `B608` em `Orchestrator/tests/test_gerar_catalogo_sql_unit.py:66`, uma f-string em fixture de teste.

## Por diretório

| Diretório | Violações | Autofix seguro |
|---|---:|---:|
| `Orchestrator/tests` | 61 | 35 |
| `Orchestrator/migrations` | 7 | 5 |
| `Produção Beneficimento/snapshots` | 2 | 2 |
| `Produção Beneficimento/analise_producao_diaria_beneficiamento.py` | 2 | 2 |

## Por regra, com dificuldade

| Dificuldade | Regra | Qtde | Onde | O que fazer |
|---|---|---:|---|---|
| **Trivial** (autofix seguro) | `B010` set-attr com constante | 11 | `conftest.py` ×9, `test_diagnostics.py` ×2 | `setattr(o, "x", v)` → `o.x = v` |
| | `UP037` anotação entre aspas | 10 | `test_worker_core_unit.py` ×5, `test_env_admin_coverage.py` ×4, `test_revisao_consenso_onda3.py` | remover aspas (`from __future__ import annotations` já presente) |
| | `B009` get-attr com constante | 6 | `test_conftest_coverage.py` ×3, `conftest.py` ×2, `test_diagnostics.py` | `getattr(o, "x")` → `o.x` |
| | `UP035` / `UP007` / `UP017` | 4 / 3 / 1 | migração `a5b212d4418f` (4), `conftest.py`, `test_e2e_dashboard.py`, `test_worker_loop.py`, `test_timezone_contract.py` | tipos modernos (`X \| None`, `datetime.UTC`) |
| | `I001`, `F401`, `C420` | 4, 1, 1 | `analise_producao_diaria_beneficiamento.py` ×2, `populate_mock_historico.py` ×2, `conftest.py`, `test_beneficiamento_sql_seguranca.py` | ordenar imports, remover import, trocar compreensão por `dict.fromkeys` |
| **Fácil** (manual, local) | `SIM117` with aninhado | 4 (1 com autofix) | `test_receitas_bloqueadas.py`, `test_revisao_consenso_cobertura.py`, `test_scheduler_runtime_unit.py`, `test_worker_loop.py` | juntar os `with` |
| | `SIM105` try/except/pass | 3 | `conftest.py`, `test_e2e_dashboard.py`, `test_scheduler_runtime_unit.py` | `contextlib.suppress(...)` |
| | `SIM103` retorno booleano | 2 | `test_receitas_bloqueadas.py` | `return <condição>` |
| | `SIM115` `open()` sem contexto | 2 | `test_e2e_dashboard.py` | `with open(...)`; olhar o ciclo de vida do handle antes |
| | `B017` `raises(Exception)` | 1 | `test_montagem_terceirizados.py` | trocar pela exceção específica (exige saber qual) |
| **Decisão de política** | `E402` import fora do topo | 19 | `conftest.py` ×10, `migrations/env.py` ×3, `test_montagem_terceirizados.py` ×3, `test_e2e_dashboard.py`, `test_receitas_bloqueadas.py`, `test_receitas_emitidas.py` | ver abaixo |

## Onde está a dificuldade real

- **`E402` (19, 26% do total, sem autofix)** não é um defeito de código: nasce de `sys.path.insert(...)` antes do import (testes que carregam as automações de domínio por caminho) e do idioma do Alembic em `env.py`. Corrigir de verdade exige reestruturar o carregamento. A saída barata é `per-file-ignores` em `pyproject.toml` (`Orchestrator/tests/**` e `Orchestrator/migrations/env.py`), já que o repositório usa o mesmo recurso para `worker.py`. É a única decisão que muda o resultado: com ela, o resíduo cai para 53.
- **Migração `a5b212d4418f` (4 violações de tipo)**: o autofix é só anotação e não muda comportamento, mas é arquivo de migração já aplicado. A alternativa é um `per-file-ignores` para `migrations/versions/**` e não editar migração antiga.
- **`conftest.py` concentra 24 violações** (E402 ×10, B010 ×9, B009 ×2, SIM105, F401, UP035). Mexer nele afeta todos os testes: o autofix é seguro, mas a suíte inteira precisa rodar depois.
- **`test_e2e_dashboard.py` (6)**: só roda com Playwright (`-m e2e`, fora do `pytest` padrão), então um erro de correção só aparece no job E2E.

## Estimativa

| Etapa | Violações | Esforço | Risco |
|---|---:|---|---|
| `ruff --fix` seguro nos 4 diretórios | 42 | minutos, mais uma rodada da suíte | baixo |
| Correção manual (SIM117 ×3, SIM105, SIM103, SIM115, B017, mais o B608 do bandit) | 11 + 1 | cerca de 1 hora | baixo a médio (SIM115 e B017 pedem entender o teste) |
| `E402` por `per-file-ignores` | 19 | minutos, mas é decisão de política | nenhum no código |
| `E402` corrigido de fato | 19 | meio dia a 1 dia, com E2E | médio |

Caminho recomendado: autofix seguro + correção manual + `per-file-ignores` para `E402`/migrações, depois incluir os diretórios no ruff e no bandit do workflow e atualizar `ci-gates`.

## Correções aplicadas (07/10/2026)

Executado: `ruff --fix` seguro em `Orchestrator/tests` e `Produção Beneficimento/` (43 corrigidas), `SIM117` via unsafe-fix onde aplicável (1), e `SIM105` ×3 trocado por `contextlib.suppress` à mão. Migrações **não** foram tocadas (ver acima). Suíte padrão: 1358 passed, 3 skipped; `Test-PythonGovernance.ps1` verde; `test_e2e_dashboard.py` só checado por `py_compile` (o job E2E é que valida).

**Armadilhas do autofix (revertidas):**
- `B009`/`B010` em `SessionLocal` e `get_wal_size_mb` quebram o `mypy --strict` (`attr-defined`: atributo não reexportado), e `cliente.post = ...` dá `method-assign`. O `getattr`/`setattr` era proposital: o nome do atributo agora fica numa constante (`_SESSION_ATTR` em `conftest.py`, `_WAL_ATTR` em `test_diagnostics.py`), e os `setattr` de método levam `# noqa: B010`.
- O `F401` removeu `from app import models` do `conftest.py`, um import de efeito colateral (registra as tabelas no `Base.metadata`). Ele voltou com `# noqa: F401`. Ao ampliar o gate, não confiar no `--fix` cego nesses dois casos.

## Gate ampliado (07/10/2026)

Resíduo de 31 zerado e os quatro diretórios entraram no `ruff` e no `bandit` do `governanca.yml` (skill `ci-gates` atualizada):

| Item | Como |
|---|---|
| `E402` ×19 | `per-file-ignores` em `pyproject.toml`: `Orchestrator/tests/**` e `Orchestrator/migrations/env.py` |
| `UP007`/`UP035` ×4 (migração `a5b212d4418f`) | `per-file-ignores` em `Orchestrator/migrations/versions/**`; migração intocada |
| `SIM117` ×3 | `with` com múltiplos contextos entre parênteses |
| `SIM103` ×2 | `return <condição>` em `test_receitas_bloqueadas.py` |
| `SIM115` ×2 | `# noqa: SIM115`: handles do uvicorn no E2E são fechados no teardown |
| `B017` ×1 | `# noqa: B017`: o teste aceita `DatabaseError` ou `CircuitBreakerError` de propósito |
| `B608` (bandit) | corpo `SELECT` separado da f-string do cabeçalho na fixture |

Verificado: comandos `ruff` e `bandit` do workflow exit 0, black/isort limpos, `Test-PythonGovernance.ps1` verde, pytest padrão verde.
