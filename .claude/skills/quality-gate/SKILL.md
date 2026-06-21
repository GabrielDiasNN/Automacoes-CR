---
name: quality-gate
description: Roda o quality gate completo do projeto (ValidarAutomacoes.ps1) e reporta cada etapa com ✓/✗. Use antes de abrir PRs com mudanças em rotas FastAPI, Dashboard ou manifesto de automação.
disable-model-invocation: true
---

Execute o quality gate completo:

```
pwsh -File Tools\ValidarAutomacoes.ps1 -BasePath .
```

Relate cada etapa com ✓ (passou) ou ✗ (falhou + mensagem de erro resumida).
Se qualquer etapa falhar, liste explicitamente o que corrigir antes do PR.
