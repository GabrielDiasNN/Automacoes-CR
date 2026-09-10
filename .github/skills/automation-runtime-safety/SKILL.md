---
name: automation-runtime-safety
description: Use when enforcing Zero-Trust, secret handling, structured logging, portable paths, and the recoverable-versus-terminal failure policy across PowerShell, Python, Node.js, the Orchestrator and automation entrypoints.
---

## Purpose
Centralizar os guardrails operacionais do hub que não pertencem a um runtime único: segredo, Zero-Trust, log estruturado, portabilidade de caminho e a fronteira entre falha recuperável e terminal. Regra transversal com fonte única em outro artefato é apenas delegada aqui, nunca reescrita.

## When to Use
- Ao alterar fluxo que lê `.env`, manipula credencial ou fala com Oracle, SQLite, SMTP/Outlook ou WhatsApp.
- Ao criar ou revisar linha de log em `lib/`, `Infrastructure/`, `Orchestrator/` ou nas pastas de automação.
- Ao decidir se um erro deve ser repetido (recuperável) ou abortar o fluxo (terminal).
- Ao introduzir diretório novo com `.py` executável e precisar saber se ele entra nos gates de lint.
- Ao mexer em round-trip de texto PT-BR entre PowerShell, Python e Node.js.

## Do Not Use When
- Para propagação de `ExecId` / `trace_id`, idempotência, ordem de persistência de estado ou o contrato de entrypoint `run.ps1`: use `enterprise-orchestration-contract`.
- Para sintaxe PowerShell, `.ps1` vs `.psm1`, approved verbs ou `try/catch` tipado: use `powershell-automation-monitor`.
- Para tipagem estática, layout de pacote Python ou o padrão dos extratores Oracle: use `python-enterprise-standard`.
- Para o canal WhatsApp headless e o bootstrap Node: use `nodejs-communications`.
- Para contraste, tema e acessibilidade do HTML de saída: use `html-css-enterprise-standard`.

## Related Skills
- `enterprise-orchestration-contract` — o fluxo onde esses guardrails se aplicam e a origem do `ExecId` / `trace_id`.
- `powershell-automation-monitor` — como aplicar Zero-Trust e log em script e módulo PowerShell.
- `python-enterprise-standard` — os mesmos guardrails no lado Python e os limites de tipagem.
- `nodejs-communications` — guardrails quando o canal de risco é WhatsApp / headless.
- `ai-native-development-standard` — registrar a decisão de risco na documentação viva.

## Non-Negotiable Rules
- Nenhum segredo, token, senha ou API key em código ou JSON versionado. Fonte única de config sensível é `.env` (lido por `lib/Lib-Config.psm1` em PowerShell, `python-dotenv` em Python). `Tools/Test-ZeroTrust.ps1` bloqueia atribuição literal de `password` / `token` / `secret` / `api_key`.
- Encoding NÃO é redefinido nem resumido aqui: a fonte única é `AGENTS.md § Regras de Encoding`, aplicada pelo hook `Assert-FileEncoding.ps1` a cada Edit/Write e por `Tools/Test-SourceEncoding.ps1` no pre-commit. Consulte lá o contrato por extensão; qualquer cópia parcial em outro arquivo é drift.
- Todo log operacional relevante carrega `trace_id` (Python) ou `ExecId` (PowerShell) e severidade explícita `INFO` / `WARN` / `ERROR`. Evento fora de `docs/log-event.schema.json` reprova em `Tools/Test-LogEventSchema.ps1`. Não esconda falha operacional em mensagem neutra de `INFO`.
- Classifique como recuperável apenas o erro que pode ser repetido sem risco de duplicidade, perda de rastreabilidade ou vazamento; o resto é terminal e aborta o fluxo. Envio de e-mail ou WhatsApp já confirmado nunca é recuperável — reenviar duplica.
- Caminho absoluto (`C:\`, `D:\`) é proibido; use `$PSScriptRoot`, caminho relativo à raiz ou função de config. `Tools/Test-PortablePaths.ps1` bloqueia.
- Limites de mypy / pylint e o contrato de `catch` tipado NÃO ficam aqui: consulte `docs/governance-contracts.md § Contrato Python — pylint` e `§ Contrato PowerShell — catch tipado`. O escopo de diretórios em `ruff` / `bandit` bloqueante do CI está na skill `ci-gates`.

## Repo-Specific Constraints
- `.env` na raiz é a única fonte de credencial; scripts Python e `lib/Lib-Config.psm1` consomem esse contexto sem duplicar valor. Para DSN Oracle fixo, `resolve_oracle_credentials(force_dsn="dbprd")` em `lib/python/oracle_extract.py`.
- A API Key do Dashboard vive só em `sessionStorage` (há teste dedicado proibindo `localStorage` para a credencial); preferência de UI benigna (ex.: densidade de tabela em `Dashboard/src/context/TableDensityContext.tsx`) pode usar `localStorage` — não migre isso para `sessionStorage` ao "corrigir" a regra.
- Log compatível com `lib/Lib-Logging.psm1` e `lib/Lib-LogEvent.psm1`; destino `Logs/` (domínio) e `Orchestrator/Logs/` (motor), ambos gitignored.
- Contrato vivo de Zero-Trust e resiliência: `Tools/Test-ZeroTrust.ps1`, `Tools/Test-PortablePaths.ps1`, `Tools/Test-LogConformidade.ps1`, `Tools/Test-EncodingResilience.ps1`. Rode-os antes do push, não só no pre-commit.
- Segredo exposto apenas em histórico local (`.jsonl`), nunca em commit, é risco aceito neste repo — antes de recomendar rotação, confirme presença em commit real com `git log -p -S '<trecho do segredo>'`.
- Diretório novo com `.py` executável precisa entrar em `ruff` / `bandit`: veja o histórico de inclusão na skill `ci-gates` antes de assumir que já está coberto (`.claude/skills` entrou em 03/08/2026).
- Acesso remoto do Orchestrator é `tailscale serve` sobre o uvicorn em `127.0.0.1` — não troque o bind nem exponha porta para facilitar debug.

## Validation
- `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-ZeroTrust.ps1 -RootPath .`.
- `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-PortablePaths.ps1 -RootPath .`.
- `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-LogConformidade.ps1 -RootPath . -All`.
- `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-EncodingResilience.ps1` quando a mudança afetar round-trip de texto, API ou escrita de log.
- `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-SourceEncoding.ps1` e `Tools/Test-LogEventSchema.ps1 -RootPath .` para encoding de fonte e schema de evento.
- Lint Python do CI: `.venv\Scripts\python -m ruff check` (escopo em `ci-gates`); limites mypy / pylint via `pwsh -File Tools\Test-PythonGovernance.ps1 -RootPath .`.

## Troubleshooting
- `Test-ZeroTrust` falha: procure primeiro atribuição literal de `password` / `token` / `secret` / `api_key` e string de conexão com senha embutida.
- `Test-PortablePaths` falha: troque o caminho absoluto por `$PSScriptRoot`, caminho relativo ou função de config; cheque também string em `.json` versionado.
- Acentuação corrompida ou ASCII-ficada (mojibake, cedilha ou acento sumido em Markdown PT-BR): valide o encoding gravado contra `AGENTS.md § Regras de Encoding` antes de investigar lógica de negócio; o hook `Assert-FileEncoding.ps1` deveria ter barrado.
- Log difícil de correlacionar: confirme que `trace_id` / `ExecId` chega antes de a linha ser escrita e que o campo de severidade existe.
- `Test-LogEventSchema` reprova: campo extra ou ausente frente a `docs/log-event.schema.json`; ajuste o emissor, não o schema, salvo decisão registrada.
- Dúvida se o erro é recuperável: se repetir puder reenviar notificação já confirmada, é terminal.

## Pre-Delivery Checklist
- Nenhum segredo novo em código ou JSON versionado; `Test-ZeroTrust` verde.
- Encoding do arquivo alterado bate com `AGENTS.md § Regras de Encoding`; sem mojibake em Markdown PT-BR.
- Todo log novo tem severidade e `trace_id` / `ExecId`; passa `Tools/Test-LogEventSchema.ps1`.
- Falha recuperável e terminal diferenciadas de forma defensável; canal já confirmado tratado como terminal.
- Nenhum caminho absoluto; `Test-PortablePaths` verde.
- Limites mypy / pylint conferidos em `docs/governance-contracts.md § Contrato Python — pylint`, não reescritos aqui.
