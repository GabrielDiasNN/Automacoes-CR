---
name: run-tests
description: "Roda a suite de testes do Orchestrator filtrando por marcador (unitario | integracao | e2e | benchmark). Uso: /run-tests <marcador>"
disable-model-invocation: true
---

Execute os testes do Orchestrator com o marcador informado em `args`, sempre com o Python do
projeto (`..\.venv\Scripts\pytest` — o `.venv` fica na **raiz** do repo, não em `Orchestrator/`;
o Python do sistema tem versões defasadas do lock).

Marcadores disponíveis: `unitario`, `integracao`, `e2e`, `benchmark`.

Se `args` foi fornecido:
```
cd Orchestrator && ..\.venv\Scripts\pytest -m {{args}} -v
```

Se nenhum marcador foi passado, rode a suíte padrão (a mesma do CI):
```
cd Orchestrator && ..\.venv\Scripts\pytest
```

Atenção:
- `Orchestrator/pytest.ini` carrega `addopts = ... -m "not e2e"` e `pythonpath = .`. A suíte
  padrão **não** inclui os testes Playwright — isso alinha o local ao CI. `-m e2e` sobrescreve
  a exclusão e exige o Orchestrator no ar + `Dashboard/dist/` buildado (`npm run build`).
- Se `pytest` falhar com `ModuleNotFoundError: No module named 'app'`, confira se
  `pytest.ini` ainda tem `pythonpath = .`.

Relate ao usuário: quantos testes passaram, falharam e foram pulados, e qualquer falha com o
nome do teste e a mensagem de erro resumida. O gate de cobertura do CI é `--cov-fail-under=84`
(mais `diff-cover --fail-under=85` nas linhas do PR) — ele não roda por padrão aqui; adicione
`--cov=app --cov=worker --cov-fail-under=84` para reproduzi-lo.
