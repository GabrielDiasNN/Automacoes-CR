# Baseline Operacional do Orchestrator

> **Versão:** v1.0.0 | **Atualizado:** 05/07/2026

## Resumo

Este documento formaliza o baseline operacional único do hub. A mesma régua é reutilizada em:

- `GET /api/system/baseline`
- `GET /api/system/diagnostics` em `operational_baseline`
- `GET /api/system/history` em `baseline_status`
- `Tools/Get-QualitySnapshot.ps1` quando a API local está disponível

O objetivo é eliminar interpretações diferentes entre API, histórico, scripts de operação e documentação.

## Status do Baseline

- `healthy`: sem sinais relevantes de degradação imediata.
- `attention`: há degradação monitorável, mas ainda sem evidência suficiente de incidente pleno.
- `incident`: há sinal operacional que exige ação estruturada imediata.

## Métricas e Thresholds

| Métrica | Attention | Incident | Ação típica |
|---|---|---|---|
| Heartbeat do worker | `>= 120s` sem ping recente | worker offline com fila ativa | `worker_recover` / `worker_wakeup` |
| Idade da fila pendente | `>= 15 min` | `>= 30 min` | `worker_wakeup` |
| Idade da execução mais antiga | `>= 60 min` | `>= 120 min` | `show_running` |
| Execuções acima do `max_runtime` | `>= 1` | `>= 3` | `show_running` |
| Ownership órfão em `RUNNING` | n/a | `>= 1` | `worker_recover` |
| Pressão do WAL | `>= 64 MB` | `>= 256 MB` | `checkpoint` |

## Regras Operacionais

- O baseline é **aditivo**: não substitui `findings`, `checks`, `slo_breaches` nem o catálogo governado.
- `incident` prevalece sobre `attention`; `attention` prevalece sobre `healthy`.
- A ação recomendada do baseline deve apontar para a primeira intervenção útil de menor custo operacional.
- Mudanças nos thresholds devem atualizar, na mesma frente, código, histórico, snapshot e documentação viva.

## Validação

- `pytest Orchestrator/tests/test_diagnostics.py Orchestrator/tests/test_system.py -q`
- `GET /api/system/baseline`
- `GET /api/system/diagnostics`
- `GET /api/system/history?hours=24`
- `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-OrchestratorIntegrity.ps1`
