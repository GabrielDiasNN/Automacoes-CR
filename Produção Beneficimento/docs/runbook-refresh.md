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

## Recarga do Histórico v2

Após atualizar uma base com schema anterior ao v2, execute a carga retroativa no intervalo operacional necessário:

```powershell
.\Tools\CargarHistoricoBeneficiamento.ps1 -DataInicio 2026-01-01 -DataFim 2026-06-12
```

A recriação é intencional: evita manter colunas tipadas parcialmente preenchidas a partir do blob legado. Só promova a mudança depois de confirmar `total_linhas_salvas`, ausência de erros por fatia e paridade dos KPIs principais.

## Regras Operacionais

- Não executar múltiplos refreshes do mesmo período em paralelo.
- Não servir snapshot parcial: a escrita deve ser atômica.
- Em falha, preservar o último snapshot válido.
- Tratar `timeout_applied=false` como atenção operacional, mesmo quando a consulta terminar rápido.
- Não registrar credenciais Oracle, DSN completo com segredo, `.env` ou payload sensível em logs.

## Validação Pós-Refresh

1. Verificar saída JSON do runner com `status=ok`, `attention` ou `partial_failure` e checar `snapshot.historico_write_status`.
2. Confirmar que `snapshots/latest/<period>.analytics.json` e `<period>.profile.json` foram atualizados.
3. Abrir `/api/beneficiamento/health` e conferir `status`, `reason_code`, `recommended_action`, `issues`, idade do snapshot e metadados Oracle.
4. Abrir `/api/beneficiamento/overview` sem parâmetros e confirmar que a janela efetiva termina em `MAX(DATA_FIM)` do SQLite.
5. Validar que `/overview` retorna `health.source=sqlite_historico`, KPIs preenchidos, `turnos` populados com `TURNO 1/2/3` e `tingimento.summary` coerente.
6. Validar que `filter_options` inclui máquina, fase, turno e alternativo disponíveis no recorte.
7. Abrir `/api/beneficiamento/detail?target_type=produto&alternativo=<ALT>` e conferir resumo, lista curada, rastreabilidade por OB e paginação sem erro.
8. Abrir `/api/beneficiamento/historico?ob=<OB>` para conferir rastreabilidade compacta de uma ordem do recorte.
9. Se o status ficar `attention`, usar `reason_code` e `issues[0].action_hint` para decidir a próxima ação sem depender de interpretação manual do payload.
10. Se o status ficar `attention` apenas por `oracle_timeout_unapplied`, validar se o tempo ficou abaixo de 19 segundos e registrar o achado.
11. Em diagnóstico de performance, confirmar via `EXPLAIN QUERY PLAN` que o recorte principal do overview usa `idx_producao_data` e não volta a depender de `date(DATA_FIM)` no `WHERE`.

## Guardrail de Dashboard

Nenhum `GET` consumido pelo Dashboard deve executar runner, template SQL ou refresh Oracle. Refresh continua sendo ação operacional separada e controlada; a aba Beneficiamento lê somente o SQLite histórico e snapshots locais.
