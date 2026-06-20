---
name: run-tests
description: Roda a suite de testes do Orchestrator filtrando por marcador (unitario | integracao | e2e). Uso: /run-tests <marcador>
disable-model-invocation: true
---

Execute os testes do Orchestrator com o marcador informado em `args`.

Marcadores disponíveis: `unitario`, `integracao`, `e2e`.

Se `args` foi fornecido, rode:
```
cd Orchestrator && .venv\Scripts\pytest -m {{args}} -v
```

Se nenhum marcador foi passado, rode todos os testes:
```
cd Orchestrator && .venv\Scripts\pytest -v
```

Relate ao usuário: quantos testes passaram, falharam e foram pulados, e qualquer falha com o nome do teste e a mensagem de erro resumida.
