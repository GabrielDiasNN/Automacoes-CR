---
name: new-automation
description: "Scaffold de nova automação com manifesto válido via New-Automation.ps1. Uso: /new-automation <Nome> <owner> <criticidade>. Criticidade válida: low | medium | high."
disable-model-invocation: true
---

Use os três argumentos passados (Nome, owner, criticidade) para executar:

```
pwsh -File Tools\New-Automation.ps1 -Name "<Nome>" -Owner "<owner>" -Criticidade "<criticidade>"
```

O script copia de `_Template/` e gera o `automation.manifest.json` a partir dele — este é o
caminho canônico e sempre produz manifesto válido.

Após o scaffold:
1. Confirme que `automation.manifest.json` foi criado na pasta da nova automação. Desde
   31/07/2026 o manifesto **ausente** gera `incident` e bloqueia `create/update` no Orchestrator.
2. Confirme que `run.ps1` existe na raiz da pasta (entrypoint padrão das automações
   registradas — a única exceção é `Produção Beneficimento/`, orientada a snapshot).
3. Instrua o usuário a chamar `POST /api/automations/preflight` com o payload do manifesto
   para validação completa (manifesto + docs obrigatórias + smoke tests) antes de registrar.
4. O campo do manifesto é **`criticality`** (inglês), não `criticidade`. Formato completo e
   campos obrigatórios em `docs/governance-contracts.md § Contrato — Manifesto de Automação`.
5. Se a automação tiver `.py` executável, lembre que diretório novo precisa entrar em
   ruff/bandit bloqueantes do CI — ver skill `ci-gates`.
