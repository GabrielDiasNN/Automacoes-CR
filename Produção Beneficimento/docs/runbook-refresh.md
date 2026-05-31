# Runbook de Refresh do Beneficiamento

## Política Inicial

- Diário: a cada 30 minutos.
- Semanal: 2 vezes ao dia.
- Mensal: 2 vezes ao dia.
- Anual: 1 vez ao dia.
- Refresh manual permitido para investigação ou fechamento operacional.

## Comando

```powershell
.\.venv\Scripts\python.exe '.\Produção Beneficimento\analise_producao_diaria_beneficiamento.py' --period diario
```

Troque `diario` por `semanal`, `mensal` ou `anual`.

## Regras Operacionais

- Não executar múltiplos refreshes do mesmo período em paralelo.
- Não servir snapshot parcial: a escrita deve ser atômica.
- Em falha, preservar o último snapshot válido.
- Tratar `timeout_applied=false` como atenção operacional, mesmo quando a consulta terminar rápido.
- Não registrar credenciais Oracle, DSN completo com segredo, `.env` ou payload sensível em logs.

## Validação Pós-Refresh

1. Verificar saída JSON do runner com `status=ok`.
2. Confirmar que `snapshots/latest/<period>.analytics.json` e `<period>.profile.json` foram atualizados.
3. Abrir `/api/beneficiamento/health` e conferir `status`, idade do snapshot e metadados Oracle.
4. Se o status ficar `attention` apenas por `call_timeout Oracle nao aplicado`, validar se o tempo ficou abaixo de 19 segundos e registrar o achado.
