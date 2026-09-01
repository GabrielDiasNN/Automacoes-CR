---
name: run-tests
description: "Roda a suite de testes do Orchestrator filtrando por marcador (unitario | integracao | e2e). Uso: /run-tests <marcador>"
disable-model-invocation: true
---

Execute os testes do Orchestrator com o marcador informado em `args`.

Marcadores disponíveis: `unitario`, `integracao`, `e2e`.

Se `args` foi fornecido, rode:
```
cd Orchestrator && ..\.venv\Scripts\pytest -m {{args}} -v
```

Se nenhum marcador foi passado, rode a suíte padrão:
```
cd Orchestrator && ..\.venv\Scripts\pytest -v
```

Atenção: `Orchestrator/pytest.ini` carrega `addopts = ... -m "not e2e"`, então a suíte
padrão **não** inclui os testes Playwright — isso alinha o local ao CI. Para rodá-los,
`-m e2e` sobrescreve a exclusão e exige o Orchestrator no ar.

Relate ao usuário: quantos testes passaram, falharam e foram pulados, e qualquer falha com o nome do teste e a mensagem de erro resumida.
