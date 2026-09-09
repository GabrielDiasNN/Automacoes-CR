# Regra de Workspace: Produção Beneficiamento

Aplica-se ao desenvolvimento e manutenção em `Produção Beneficimento/`.

## Arquitetura Orientada a Snapshots

- **Sem `run.ps1`**: Ao contrário das outras automações de domínio registradas com manifesto, esta automação é orientada a snapshot periódico e não possui `run.ps1`.
- **Consumo Desacoplado**: A API FastAPI **nunca** consulta o Oracle diretamente; ela consome exclusivamente os arquivos serializados em `Produção Beneficimento/snapshots/latest/`.

## Estrutura de Módulos (`src/beneficiamento/`)

- `oracle.py`: Único ponto de contato com o banco de dados Oracle. Nenhuma conexão com Oracle deve ser aberta fora deste arquivo.
- `runner.py`: Orquestra a captura dos dados do Oracle para o histórico em SQLite, sob orçamento de tempo (`WALL_CLOCK_BUDGET_SECONDS` em `settings.py` — valor canônico lá, não reproduzido aqui — ajustável por `BENEFICIAMENTO_WALL_CLOCK_SECONDS`).
- `snapshot_store.py`: Responsável pela leitura e escrita em disco dos snapshots (`snapshots/latest/`).
- `contracts/`: Implementações canônicas de agregação (`overview.py`, `detail.py`, `tingimento.py`).
  - O código SQL deve permanecer estritamente isolado nos módulos privados `_queries.py`, `_queries_common.py`, `_queries_overview.py` e `_queries_detail.py`.
