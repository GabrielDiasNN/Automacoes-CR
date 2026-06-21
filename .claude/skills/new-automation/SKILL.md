---
name: new-automation
description: Scaffold de nova automação com manifesto válido via New-Automation.ps1. Uso: /new-automation <Nome> <owner> <criticidade>. Criticidade válida: low | medium | high.
disable-model-invocation: true
---

Use os três argumentos passados (Nome, owner, criticidade) para executar:

```
pwsh -File Tools\New-Automation.ps1 -Name "<Nome>" -Owner "<owner>" -Criticidade "<criticidade>"
```

Após o scaffold:
1. Confirme que `automation.manifest.json` foi criado na pasta da nova automação.
2. Instrua o usuário a chamar `POST /api/automations/preflight` com o payload do manifesto para validação completa antes de registrar no Orchestrator.
3. Lembre que o entrypoint padrão é `run.ps1` e deve existir na raiz da pasta.
