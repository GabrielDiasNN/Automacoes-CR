---
name: python-enterprise-standard
description: Use when developing or reviewing Python code, including FastAPI, Pandas, Pydantic, strict typing with Mypy, Pylint and Bandit quality checks, and ensuring adherence to the repository's Python governance and UTF-8 encoding.
---

## Purpose
Padronizar o desenvolvimento Python no hub, garantindo que regras de negócio, endpoints FastAPI, processamento de dados (Pandas) e validações estruturais sigam o mesmo nível de tipagem estrita (Mypy `--strict`), qualidade (Pylint, Bandit) e segurança exigidos pelo repositório.

## When to Use
- Use ao alterar módulos Python em `Orchestrator/app/` ou scripts em `.py` como `worker.py`, `extract_oracle.py`, e `processar_receitas.py`.
- Use ao refatorar schemas Pydantic ou integrações com o banco SQLite/Oracle.
- Use ao escrever ou revisar testes com `pytest`.
- Use ao introduzir manipulação de dados utilizando bibliotecas externas, garantindo abordagens vetorizadas (Pandas).

## Do Not Use When
- Nao use para decidir o fluxo completo da orquestração ou handoffs entre PowerShell e Python; nesses casos use `enterprise-orchestration-contract`.
- Nao use para diretrizes operacionais universais de infraestrutura ou falhas de logs; nesses casos use `automation-runtime-safety`.
- Nao use para monitoramentos em PowerShell; use `powershell-automation-monitor`.

## Related Skills
- `enterprise-orchestration-contract` para o papel do código Python no pipeline corporativo de execuções.
- `automation-runtime-safety` para as regras de log, Zero Trust, encoding e classificação de severidade que o Python deve adotar.
- `ai-native-development-standard` para alinhar as documentações quando o backend for estruturalmente alterado.

## Non-Negotiable Rules
- Todo código Python deve passar nas validações estritas do Mypy (`--strict`).
- Todo código deve passar no check de qualidade do Pylint conforme configuração local.
- Todo código em `Orchestrator/app/` e `Orchestrator/worker.py` deve passar no lint bloqueante do CI: `python -m ruff check Orchestrator/app Orchestrator/worker.py`.
- Utilize abordagens vetorizadas no Pandas (sem loops `iterrows`) para scripts de alta volumetria.
- Encoding de `.py` segue o contrato único definido em `automation-runtime-safety` (UTF-8 sem BOM); não redefina aqui, apenas valide com `Test-SourceEncoding.ps1`.
- A aplicação deve modularizar contratos (ex: schemas Pydantic separados por domínio) ao invés de usar monolitos.

## Repo-Specific Constraints
- Utilize a `venv` oficial do repositório, garantindo que o ambiente isolado seja mantido (`.venv/`).
- Importações devem respeitar namespaces explícitos e usar os módulos comuns configurados em `Orchestrator/app/`.
- Migrações de schema do banco do Orchestrator são feitas exclusivamente via Alembic (`alembic upgrade head`); não altere schema manualmente.
- Sessões SQLAlchemy fora do contexto FastAPI devem usar `session_scope` (não `SessionLocal()` diretamente), conforme `Tools/Test-ArchitectureStandard.ps1`.
- Scripts de negócio em Python (como `.env` binding e caminhos) devem se valer da estratégia robusta descrita no `GEMINI.md`.
- Consulte `docs/governance-contracts.md` para os limites exatos de Mypy/Pylint e formato de contratos exigidos pelo pre-commit hook antes de escrever código novo.

## Validation
- Rode `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-PythonGovernance.ps1 -RootPath .`
- Rode `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-SourceEncoding.ps1 -RootPath .` para garantir a ausência de BOM.
- Rode `python -m ruff check Orchestrator/app Orchestrator/worker.py` para reproduzir localmente o gate bloqueante do CI.
- Execute os testes automatizados da suíte: `pytest` no diretório raiz do `Orchestrator/`.

## Troubleshooting
- Se o Mypy rejeitar tipagem, verifique explicitamente retornos de funções `Optional`, `Union` e evite o uso de `Any`.
- Se o código falhar por problemas de encoding, revise as ferramentas de gravação do agente garantindo gravação UTF-8 sem BOM.
- Se o script apresentar gargalos, certifique-se de não estar utilizando iterações escalares no Pandas ou requisições `N+1` no SQLAlchemy.

## Pre-Delivery Checklist
- Confirme que o código passa no `Test-PythonGovernance.ps1`.
- Confirme que schemas e endpoints obedecem à divisão modular do domínio.
- Confirme que abordagens vetorizadas foram priorizadas.
- Confirme que o arquivo foi salvo em UTF-8 sem BOM.
