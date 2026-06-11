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
