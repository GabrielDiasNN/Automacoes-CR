# Runbook Operacional: Incidente e Rollback do Orchestrator

> **Escopo:** Incidentes de operação no Orchestrator (`/api/system/*`, fila, worker, scheduler e dashboard).
> **Última revisão:** 24/05/2026

## 1. Critérios de Abertura de Incidente

Abrir incidente quando qualquer condição abaixo ocorrer:

- `overall_status=unhealthy` em `/api/system/diagnostics`.
- Worker offline com fila ativa (`worker.is_alive=false` e `queue.active_count>0`).
- Execuções `RUNNING` acima de `max_runtime` em quantidade recorrente.
- Crescimento de WAL em faixa crítica (`wal_risk=critical`).
- Incompatibilidade de contrato front-back bloqueando ações operacionais.

## 2. Triagem Imediata (primeiros 5 minutos)

1. Coletar snapshot:
   - `GET /api/system/version`
   - `GET /api/system/overview`
   - `GET /api/system/diagnostics`
   - `GET /api/system/history?hours=24`
2. Registrar `correlation_id` exibido no dashboard para rastrear logs.
3. Confirmar escopo:
   - Fila (`queue.by_status`, `retry_pressure`, `timeouts_24h_by_group`)
   - Worker (`worker.is_alive`, `worker.instance_id`, `heartbeat.last_ping_age_seconds`)
   - Ownership (`queue.orphaned_running`, `oldest_running.worker_instance_id`, `oldest_running.worker_pid`)
   - Scheduler (`scheduler.running`, `scheduler.jobs_loaded`)

## 3. Contenção (sem rollback)

Executar nesta ordem:

1. `POST /api/system/worker/wakeup`
2. `POST /api/system/scheduler/reload`
3. `POST /api/system/checkpoint` (quando houver pressão de WAL)
4. Reavaliar `GET /api/system/diagnostics`
5. Se houver recorrência, comparar tendência em `trend_summary` e `history` antes de requeue manual.

Se o status voltar para `healthy`/`degraded` estável, encerrar incidente com monitoramento por 30 minutos.

## 4. Recuperação Forte

Quando contenção não resolver:

1. Executar `POST /api/system/worker/recover`.
2. Aguardar janela de recuperação do processo.
3. Revalidar:
   - `GET /api/system/health`
   - `GET /api/system/diagnostics`
   - `GET /api/system/history?hours=1`
4. Confirmar ausência de regressão na fila ativa e no scheduler.

## 5. Protocolo de Rollback

Acionar rollback quando houver regressão funcional após mudança recente.

1. **Congelar ações mutáveis** na operação (sem novos cadastros/reconfigurações).
2. **Isolar banco**:
   - `POST /api/system/checkpoint`
   - `POST /api/system/backup`
3. **Retornar versão estável** do código (último commit homologado).
4. **Subir serviço** e validar:
   - `GET /api/system/version`
   - `GET /api/system/diagnostics`
5. **Executar smoke E2E final** em `http://127.0.0.1:8000/dashboard/`.

## 6. Checklist de Encerramento

- Diagnóstico em estado controlado (`healthy` ou `degraded` sem achados críticos).
- Fila sem envelhecimento anômalo.
- Worker e scheduler estáveis.
- Ações de recovery registradas em auditoria.
- Evidência E2E final registrada.

## 7. Pós-Incidente

- Atualizar `CHANGELOG.md` quando houver mudança de comportamento.
- Atualizar `CONTEXT.md` se houver novo padrão operacional.
- Abrir item de hardening quando a causa raiz não for eliminada.
