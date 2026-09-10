---
name: quality-gate
description: Roda o quality gate completo do projeto (ValidarAutomacoes.ps1) e reporta cada etapa com ✓/✗. Use antes de abrir PRs com mudanças em rotas FastAPI, Dashboard ou manifesto de automação.
disable-model-invocation: true
---

Execute o quality gate completo. Ele demora vários minutos e a `governanca_nativa` sozinha
passa de 4 min — rode em background e **cheque `$LASTEXITCODE` do arquivo de saída**, nunca
leia o exit code por um pipe (`| Select-Object`/`| Tee-Object` mascara a falha do `.ps1`):

```
pwsh -File Tools\ValidarAutomacoes.ps1 -BasePath . *> quality-gate.out.txt; $LASTEXITCODE | Out-File quality-gate.exit.txt
```

Depois leia `quality-gate.out.txt` e `quality-gate.exit.txt`. Exit `0` = tudo passou.

Relate cada etapa (`governanca_nativa`, `governanca_skills`, `governanca_dashboard_template`,
`pytest`, `e2e`) com ✓ (passou) ou ✗ (falhou + mensagem de erro resumida).
Se qualquer etapa falhar, liste explicitamente o que corrigir antes do PR.

Para só a governança (sem pytest/E2E, ~4 min): adicione `-OnlyGovernance`. Para checklist
de lint/encoding/governança Python mais rápido, use `/preflight` em vez desta skill.
