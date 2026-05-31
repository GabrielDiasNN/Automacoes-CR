# Produção Beneficimento

Domínio dedicado para a API de produção e os snapshots analíticos de Beneficiamento.

## Contrato

- A API do Orchestrator é `snapshot-first`: requisições `GET` leem arquivos locais em `snapshots/latest/` e não abrem conexão Oracle.
- O Oracle só deve ser acessado por refresh controlado via `analise_producao_diaria_beneficiamento.py` ou módulos em `src/beneficiamento/`.
- O orçamento operacional é rígido: `BENEFICIAMENTO_ORACLE_TIMEOUT_MS=18000` e corte externo de 19 segundos, abaixo do limite de 20 segundos aplicado pelo DBA.
- Se o `call_timeout` do Oracle Client não for aplicado, o snapshot continua utilizável, mas a API marca o período como `attention`.

## Estrutura

- `src/beneficiamento/`: código Python modular do domínio.
- `sql/templates/`: SQLs operacionais com binds `:dt_inicio` e `:dt_fim`.
- `sql/reference/`: views de referência preservadas para auditoria técnica.
- `snapshots/latest/`: última versão aprovada dos arquivos `*.analytics.json` e `*.profile.json`.
- `docs/`: arquitetura, baseline e runbook operacional.

## Refresh manual

```powershell
.\.venv\Scripts\python.exe '.\Produção Beneficimento\analise_producao_diaria_beneficiamento.py' --period diario
```

Períodos válidos: `diario`, `semanal`, `mensal`, `anual`.
