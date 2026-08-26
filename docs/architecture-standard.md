# Padrão Arquitetural do Hub de Automações

> **Versão:** v1.0.0 | **Atualizado:** 07/06/2026

Este documento define o contrato arquitetural mínimo do Hub de Automações. Ele complementa `AGENTS.md`, `CONTEXT.md`, `SECURITY.md` e as skills canônicas em `.github/skills/`, sem substituir regras mais específicas desses artefatos.

## Camadas

O Hub mantém fronteiras explícitas entre apresentação, API, runtime, automações e governança:

- **Dashboard SPA:** consome contratos REST/WebSocket do Orchestrator e não contém regra de negócio, segredo ou chamada direta a banco externo.
- **FastAPI/Orchestrator:** expõe routers, schemas e serviços modulares; endpoints de leitura devem retornar dados sanitizados e não abrir integrações sensíveis quando houver contrato snapshot-first.
- **Runtime e Worker:** concentram execução de processos, ownership, fila, scheduler, recovery e subprocessos autorizados.
- **Automações governadas:** iniciam por `run.ps1`, declaram `automation.manifest.json`, runbook e smoke test antes de promoção recorrente.
- **Tools e lib:** mantêm validadores, scaffold, módulos PowerShell compartilhados e guardrails de qualidade.
- **Documentação viva e skills:** descrevem o estado real do Hub e devem evoluir junto de mudanças arquiteturais.

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
- Novos usos de `subprocess` fora da allowlist de runtime geram aviso para evitar ownership opaco de processos; testes automatizados não são tratados como runtime operacional.
- Diretórios operacionais com `run.ps1` devem possuir manifesto governado, runbook e smoke test declarados.
- Caminhos informados via `-Paths` devem resolver dentro de `RootPath`; entradas fora da raiz são bloqueadas sem leitura do arquivo externo.
- Documentos centrais devem apontar para este padrão para manter discovery consistente entre Codex, Gemini CLI e Antigravity.

## Canal WhatsApp — Sessão Única e Concorrência

Todas as automações que enviam WhatsApp (`Receitas Bloqueadas`, `OBs Paradas Fase`, `OBs Fluxo Sem Tingimento` e a ORB-07 ativa `OBs Restricao Branco`) e o alerta de falhas do Orchestrator (`Orchestrator/app/notifications.py`) compartilham a mesma sessão autenticada `hub-global`, acionada através do motor único `lib/WhatsApp-Core.js` (invocado sempre via `lib/Send-WhatsApp.ps1`).

- **Sessão fora da árvore do repositório:** o diretório `LocalAuth` vive em `%LOCALAPPDATA%\Automacoes\wwebjs_auth\session-hub-global\` (override: `WHATSAPP_AUTH_PATH`). Ele contém credenciais de sessão do WhatsApp Web — quem copiar o diretório assume a conta sem QR code. Manter fora do repositório impede que zip, backup ou sync da pasta do projeto carregue a sessão junto. Resolução canônica: `lib/whatsapp-auth-path.js` (Node) e `Get-WhatsAppAuthPath` em `lib/Lib-Process.psm1` (PowerShell) — nunca reconstruir o caminho manualmente.
- **Sessão única por design:** não há pool de sessões nem fila dedicada; a concorrência entre chamadores é resolvida por lock de arquivo no perfil da sessão.
- **Exit code `40` (lock ativo)** e **exit code `23` (cooldown)** são **comportamento normal de serialização**, não falha da automação — o chamador deve reprocessar no próximo ciclo agendado, não escalar como incidente.
- **Exit code `21`** (sessão expirada) exige reautenticação manual via `lib\Authenticate-WhatsApp.bat`; nenhuma automação deve tentar reautenticar sozinha.
- Novos consumidores do canal WhatsApp devem invocar exclusivamente `lib/Send-WhatsApp.ps1` (nunca `lib/WhatsApp-Core.js` diretamente), para herdar a limpeza de locks/processos zumbis e a resolução de `NODE_PATH` centralizadas no wrapper.

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

Empacotar `lib/python` e instalar com `pip install -e .` foi avaliado e **recusado**: tornaria os scripts não executáveis diretamente (`python extract_oracle.py`, como se depura hoje) sem instalação prévia no interpretador, e uma instalação ausente falharia silenciosamente no próximo cron de automações de produção. `lib/tests/Python-Bootstrap.Tests.ps1` garante que as cinco ocorrências permaneçam idênticas — o risco real aqui é o drift entre elas, não a existência da linha.

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

Para mudanças de UI, rotas consumidas pela UI ou contratos front-back, a validação Playwright E2E continua sendo a última etapa obrigatória, conforme `docs/playwright-e2e-standard.md`.
