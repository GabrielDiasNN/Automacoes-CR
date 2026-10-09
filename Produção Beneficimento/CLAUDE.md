# Produção Beneficiamento — contexto de módulo

Carregado apenas ao trabalhar em `Produção Beneficimento/`. As regras universais (encoding, caminhos, banco, Zero-Trust, commits, E2E, manifesto) estão no `CLAUDE.md` da raiz.

Automação orientada a snapshot: não tem `run.ps1`, ao contrário das seis automações registradas com manifesto.

## Módulos (`src/beneficiamento/`)

- `contracts/` — implementação histórica canônica (`overview.py`, `detail.py`, `tingimento.py` — agregação da fase real de tingimento consumida por `GET /api/beneficiamento/tingimento`); o SQL do histórico fica isolado nos módulos privados `_queries_common.py`, `_queries_overview.py` e `_queries_detail.py` (o `_queries.py` só reexporta os builders; o SQL de `tingimento.py` é inline no próprio módulo).
- `oracle.py` — única interface com Oracle; nunca abre conexão fora deste arquivo.
- `runner.py` — orquestra snapshot Oracle → SQLite histórico; orçamento de 20 s.
- `snapshot_store.py` — lê/escreve `Produção Beneficimento/snapshots/latest/`. A API **nunca** consulta Oracle diretamente; consome apenas esses snapshots.
