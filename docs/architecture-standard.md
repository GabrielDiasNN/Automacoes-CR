# Padrão Arquitetural do Hub de Automações

> **Versão:** v1.0.0 | **Atualizado:** 07/10/2026

Este documento define o contrato arquitetural mínimo do Hub de Automações. Ele complementa `AGENTS.md`, `CONTEXT.md`, `SECURITY.md` e as skills canônicas em `.github/skills/`, sem substituir regras mais específicas desses artefatos.

## Camadas

O Hub mantém fronteiras explícitas entre apresentação, API, runtime, automações e governança:

- **Dashboard SPA:** consome contratos REST/WebSocket do Orchestrator e não contém regra de negócio, segredo ou chamada direta a banco externo.
- **FastAPI/Orchestrator:** expõe routers, schemas e serviços modulares; endpoints de leitura devem retornar dados sanitizados e não abrir integrações sensíveis quando houver contrato snapshot-first.
- **Runtime e Worker:** concentram execução de processos, ownership, fila, scheduler, recovery e subprocessos autorizados.
- **Automações governadas:** iniciam por `run.ps1`, declaram `automation.manifest.json`, runbook e smoke test antes de promoção recorrente.
- **Tools e lib:** mantêm validadores, scaffold, módulos PowerShell compartilhados e guardrails de qualidade.
- **Documentação viva e skills:** descrevem o estado real do Hub e devem evoluir junto de mudanças arquiteturais.

### Fronteiras de dados e código de apoio (07/10/2026)

| O quê | Onde mora | Dono / regra |
| --- | --- | --- |
| Regra de negócio do ciclo de vida de execuções e automações | `Orchestrator/app/services/` (`execution_runtime`, `automation_repository`); erro de regra em `services/domain_errors.DomainRuleError` | Routers só validam payload, traduzem `DomainRuleError` em `HTTPException`, persistem e auditam |
| Acervo de consultas SQL de referência (catálogo gerado, evidência de validação) | `docs/oracle-schema/consultas/` | Material de referência sobre o ERP, ao lado do catálogo do schema; só as consultas ✅ valem como referência canônica; promover a runtime é **mover**, nunca copiar |
| SQL de runtime do Beneficiamento | `Produção Beneficimento/sql/templates/` | Dono: o runner; `test_beneficiamento_sql_template_unit.py` falha se o caminho configurado em `settings.py` deixar de existir |
| Ferramentas Python de Oracle (catálogo, validação, medição, guard) | `Tools/oracle/` | `CONSULTAS_ROOT` em `validar_sql_oracle.py` é a fonte única do caminho do acervo; guard = `Tools/oracle/guard_sql.py` → guard canônico externo |
| Governança, scaffold e hooks | `Tools/*.ps1`, `Tools/log_event_validator.py` | Pre-commit executa `ValidarAutomacoes.ps1 -OnlyGovernance` |
| Documentação transversal | `docs/governanca/`, `docs/qualidade/`, `docs/operacao/`; ficam na raiz de `docs/` os arquivos cujo caminho é contrato de hook/validador | Referências por caminho completo; mover exige atualizar `Tools/Test-*.ps1` |

## Severidade

`Tools/Test-ArchitectureStandard.ps1` usa severidade gradual para permitir endurecimento sem bloquear melhorias legítimas:

- **critical:** regressão arquitetural que quebra fronteira de segurança, persistência, snapshot-first ou catálogo governado; falha o gate.
- **warning:** desvio que merece correção ou exceção documentada, mas não bloqueia o v1.
- **info:** observação futura sem impacto de gate.

No v1, o quality gate falha apenas quando existir ao menos um achado `critical`.

## Ruleset

As exceções e padrões operacionais versionados do validador vivem em `Tools/architecture-standard.rules.json`, mantendo o script focado em execução segura e relatório estruturado. O arquivo de regras define allowlists de runtime para `subprocess`, `sqlite3`, exclusões de automações e seções documentais obrigatórias.

Se o ruleset estiver ausente ou inválido, o validador deve retornar `RULESET_MISSING` ou `RULESET_LOAD_FAILED` como achado `critical`.

## Regras Governadas

- Routers FastAPI não devem abrir Oracle diretamente; contratos como Beneficiamento permanecem snapshot-first para endpoints `GET`.
- Uso direto de `sqlite3` deve ficar restrito à camada de banco/runtime autorizada, diagnóstico local ou leitura histórica SQLite do Beneficiamento.
- Novos usos de `subprocess` fora da allowlist de runtime geram aviso para evitar ownership opaco de processos; testes automatizados não são tratados como runtime operacional. Exceções de CLI standalone (24/09/2026): `Tools\oracle\gerar_core_graph.py` (chama `git ls-files`), `Tools\oracle\auditar_acervo_sql.py` (chama `medir_sql_oracle.py` por consulta), `Tools\oracle\validar_sql_oracle.py` e `Tools\oracle\validar_partes_oracle.py` (chamam o wrapper versionado `Tools\oracle\guard_sql.py`, que delega ao `guard_sql.py` canônico da skill `oracle-sql`; este **não** está no repositório: é uma skill externa instalada no perfil do usuário. `ORACLE_SQL_GUARD` substitui a cadeia inteira; sem o wrapper ou sem o canônico o validador aborta como erro de ferramenta) — processos curtos e síncronos, com saída capturada, disparados manualmente fora do runtime do Hub; nenhum processo sobrevive ao script.
- Diretórios operacionais com `run.ps1` devem possuir manifesto governado, runbook e smoke test declarados.
- Caminhos informados via `-Paths` devem resolver dentro de `RootPath`; entradas fora da raiz são bloqueadas sem leitura do arquivo externo.
- Documentos centrais devem apontar para este padrão para manter discovery consistente entre Codex, Gemini CLI e Antigravity.
- `ORM_QUERY_IN_API_ROUTER` cobre **leitura** via ORM (`db.query(...)` / `session.query(...)`) em `Orchestrator/app/routers/`, não escrita — ver "Leitura vs. Escrita ORM nos Routers" abaixo.

## Leitura vs. Escrita ORM nos Routers

A regra `ORM_QUERY_IN_API_ROUTER` (`Tools/Test-ArchitectureStandard.ps1`, allowlist vazia em `Tools/architecture-standard.rules.json → router_orm_query_allowlist`) detecta apenas o literal `db.query(`/`session.query(`. Escrita ORM (`db.add`, `db.commit`, `db.refresh`, `db.delete`) continua nos routers e **não é falha de detecção**: é uma exceção arquitetural deliberada, registrada aqui na revisão de 08/09/2026 após auditoria das 33 ocorrências em `Orchestrator/app/routers/*.py` (31 desde 07/10/2026, ver abaixo).

**Escrita fina é aceita no router** quando o router apenas persiste um payload já validado por uma camada de service/schema (preflight de automação, `env_admin`, `system_runtime`, um schema Pydantic) e grava o log de auditoria — por exemplo `create_automation`, `update_automation`, `pause_automation`/`resume_automation`, `clone_automation`, `set_*_test_mode`, `manual_backup`, `manual_checkpoint`, `manual_purge`, `update_env_content`, `update_automation_config`, `update_automation_script`, `requeue_execution` (a lógica de retry vive em `prepare_requeue`, o router só persiste). Não é necessário mover esses `db.add`/`db.commit`/`db.refresh`/`db.delete` para um `*_repository.py`.

**Lógica de negócio real dentro do router segue proibida.** A auditoria de 08/09/2026 encontrou 8 ocorrências (de 33) que a continham, em 5 endpoints. **Resolvido em 07/10/2026**: a regra foi para services e o router só traduz `DomainRuleError` em `HTTPException`, persiste e grava a auditoria.

| Endpoint | Onde a regra vive agora |
| --- | --- |
| `delete_automation` | `automation_repository.ensure_deletable` (bloqueio de remoção com execução ativa, 409) |
| `start_automation` | `execution_runtime.prepare_manual_start` (execução ativa, grupo operacional e cooldown) + `commit_or_conflict` (corrida no índice único parcial vira 409) |
| `stop_execution` | `execution_runtime.terminate_execution` (transição para TERMINATED, duração e linha `[STOP]`) |
| `telemetry_start` | `execution_runtime.build_telemetry_execution` + `commit_or_conflict` |
| `telemetry_end` | `execution_runtime.finish_telemetry_execution` (somente status terminais, 422; duração e truncagem de log) |

`execution_runtime.compute_duration_seconds` é o cálculo único de duração desses fluxos. O erro de regra é `services/domain_errors.DomainRuleError(status_code, detail)`; `RequeueValidationError` herda dele.

Restam 31 escritas ORM nos routers, todas "escrita fina" sobre payload/estado já validado (a exceção documentada acima): `automation_config.py:107`; `automation_ide.py:107`; `automations.py` (create/update/pause/resume/clone/test-mode e a persistência de `delete_automation` e `start_automation`); `executions.py` (`requeue_execution` e a persistência de `stop_execution`, `telemetry_start` e `telemetry_end`); `system.py` (backup, checkpoint, purge, env). Quem acrescentar uma 32ª escrita precisa revisar se é fina ou se pertence a um service, e atualizar este número junto com `tests/test_router_orm_write_exception_unit.py`.

## Allowlist `python_sqlite_allowlist`

Auditoria de 08/09/2026 encontrou 3 entradas órfãs em `Tools/architecture-standard.rules.json → python_sqlite_allowlist` (isenta caminhos da regra `SQLITE_DIRECT_ACCESS_OUTSIDE_DB_LAYER`, que dispara em `import sqlite3`): `Produção Beneficimento\src\beneficiamento\historico_db.py` e `overview_v1.py` tinham `grep -c "import sqlite3\|sqlite3\." == 0` e nenhum histórico (`git log -S "import sqlite3"`) — são shims de compatibilidade puros (reexportam de `beneficiamento.data`/`beneficiamento.contracts`, já cobertos por outras entradas da mesma allowlist) e nunca usaram `sqlite3` diretamente. Removidas.

`Orchestrator\app\database.py` também deu `grep -c` zero e não tem histórico de `import sqlite3`, mas foi **mantida** na allowlist: é a camada canônica de banco do Orchestrator (`session_scope`, engine SQLAlchemy) e já manipula a conexão SQLite raw por baixo do ORM — o listener `set_sqlite_pragma` (`@event.listens_for(engine, "connect")`) recebe o `dbapi_connection` (uma instância real de `sqlite3.Connection`, só que via SQLAlchemy, não via `import sqlite3` literal) e roda `cursor.execute("PRAGMA ...")` diretamente nela para WAL/synchronous/foreign_keys/busy_timeout/cache_size/temp_store. É o lugar correto, por design, para qualquer futuro uso de `sqlite3` mais direto nesta camada (ex.: uma migração ad-hoc ou introspecção de schema que precise do driver bruto) — isentá-lo antecipadamente evita que o gate barre um uso legítimo da própria camada de banco. Como `rules.json` é JSON e não aceita comentário, a justificativa fica registrada aqui.

`Tools\oracle\build_oracle_catalog.py` e `Tools\oracle\oracle_catalog.py` (14/09/2026) também estão na allowlist, por um motivo diferente: `docs/oracle-schema/schema.db` **não é dado de aplicação do Orchestrator** — é um catálogo local, gitignored e reconstruível, do dicionário de dados do Oracle SGTPRD (3.608 tabelas), usado só para consulta de schema por ferramentas de linha de comando fora do runtime do Hub. Não há `session_scope` nem engine SQLAlchemy para essa base porque ela nunca é lida ou escrita pelo Orchestrator — só por scripts standalone: o builder, o CLI de consulta e `Tools\oracle\gerar_core_graph.py` (24/09/2026), que abre a base em modo somente leitura (`mode=ro`) para regenerar `docs/oracle-schema/core-graph.json`.

## Canal WhatsApp — Sessão Única e Concorrência

Todas as automações que enviam WhatsApp (`Receitas Bloqueadas`, `OBs Paradas Fase`, `OBs Fluxo Sem Tingimento` e a ORB-07 ativa `OBs Restricao Branco`) e o alerta de falhas do Orchestrator (`Orchestrator/app/notifications.py`) compartilham a mesma sessão autenticada `hub-global`, acionada através do motor único `lib/WhatsApp-Core.js` (invocado sempre via `lib/Send-WhatsApp.ps1`).

- **Sessão fora da árvore do repositório:** o diretório `LocalAuth` vive em `%LOCALAPPDATA%\Automacoes\wwebjs_auth\session-hub-global\` (override: `WHATSAPP_AUTH_PATH`). Ele contém credenciais de sessão do WhatsApp Web — quem copiar o diretório assume a conta sem QR code. Manter fora do repositório impede que zip, backup ou sync da pasta do projeto carregue a sessão junto. Resolução canônica: `lib/whatsapp-auth-path.js` (Node) e `Get-WhatsAppAuthPath` em `lib/Lib-Process.psm1` (PowerShell) — nunca reconstruir o caminho manualmente.
- **Sessão única por design:** não há pool de sessões nem fila dedicada; a concorrência entre chamadores é resolvida por lock de arquivo no perfil da sessão.
- **Exit code `40` (lock ativo)** e **exit code `23` (cooldown)** são **comportamento normal de serialização**, não falha da automação — o chamador deve reprocessar no próximo ciclo agendado, não escalar como incidente.
- **Exit code `21`** (sessão expirada) exige reautenticação manual via `lib\Authenticate-WhatsApp.bat`; nenhuma automação deve tentar reautenticar sozinha.
- Novos consumidores do canal WhatsApp devem invocar exclusivamente `lib/Send-WhatsApp.ps1` (nunca `lib/WhatsApp-Core.js` diretamente), para herdar a limpeza de locks/processos zumbis e a resolução de `NODE_PATH` centralizadas no wrapper.
- A confirmação de despacho do motor é independente do exit code isolado: `waitUntilMsgSent` é solicitado e o ID é obtido do retorno ou de `message_create`. Na versão instalada do `whatsapp-web.js`, `_serialized` pode faltar e o identificador interno `$1` deve ser aceito; sem ambos, o consumidor falha sem consolidar idempotência.

## Idempotência de Entrega e Bootstrap Python das Automações

Duas decisões registradas na revisão arquitetural de 26/07/2026 (`CHANGELOG.md` [1.3.0]).

**Idempotência por canal é da `lib/Lib-Idempotency.psm1`.** Automação que suprime reenvio por hash de conteúdo (`Receitas Bloqueadas`, `Receitas Emitidas`, `Montagem de Terceirizados`) consome `Get-LastContentHash`, `Read-DeliveryState`, `Update-DeliveryStateHash`, `Test-DeliveryPending`, `Set-DeliverySuccess` e `Save-DeliveryState` — nunca reimplementa a leitura/escrita de `delivery_state.json`. `lib/tests/Lib-Idempotency.Tests.ps1` trava esse contrato.

Três exceções deliberadas, por usarem modelo estruturalmente diferente: `OBs Paradas Fase` é idempotente **por fase** (array `phases` de tamanho variável por execução) e reaproveita `Get-LastContentHash`; `OBs Fluxo Sem Tingimento` e `OBs Restricao Branco` resolvem idempotência por ciclo da OB dentro do Python, sem `delivery_state`. Encaixá-las no contrato por canal seria abstração errada.

Na ORB-07, a consulta de estoque mantém uma linha por reduzido mesmo quando há
peças nas finalidades 3 e 4: `COUNT(DISTINCT IDPECASPRODUTO)` decide o saldo e
as contagens por finalidade servem apenas à auditoria da mensagem. O artigo e
a cor programada são normalizados na camada de apresentação (3 e 2 dígitos,
respectivamente), sem alterar o dado Oracle usado na decisão.

**Bootstrap do `lib/python` fica no script, em forma única.** Cada script de extração declara exatamente uma linha:

```python
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "python")
)
```

Empacotar `lib/python` e instalar com `pip install -e .` foi avaliado e **recusado**: tornaria os scripts não executáveis diretamente (`python extract_oracle.py`, como se depura hoje) sem instalação prévia no interpretador, e uma instalação ausente falharia silenciosamente no próximo cron de automações de produção. `lib/tests/Python-Bootstrap.Tests.ps1` garante que as seis ocorrências permaneçam idênticas — o risco real aqui é o drift entre elas, não a existência da linha. **`OBs Restricao Branco/extract_orb.py` (ORB-07, adicionada em 26/08/2026) declara a mesma linha canônica e entrou na lista `$ScriptsComBootstrap` do teste em 08/09/2026** — as 6 automações com a forma canônica estão travadas contra drift.

## Validação (Validacao)

Execute o validador diretamente quando alterar arquitetura, runtime, automações governadas ou documentação central:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-ArchitectureStandard.ps1 -RootPath .
pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-ArchitectureStandard.ps1 -RootPath . -AsJson
```

O validador também roda dentro do gate agregado:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance
```

Para mudanças de UI, rotas consumidas pela UI ou contratos front-back, a validação Playwright E2E continua sendo a última etapa obrigatória, conforme `docs/qualidade/playwright-e2e-standard.md`.
