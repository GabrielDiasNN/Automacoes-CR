# Infrastructure — Scripts de Operação do Orchestrator

Scripts PowerShell de suporte ao ciclo de vida do Orchestrator (API + Worker). São executados manualmente pelo operador ou via Tarefa Agendada do Windows — não são chamados pelo código da aplicação.

| Script | Propósito | Como rodar |
| --- | --- | --- |
| `Start-Orchestrator.ps1` | Sobe API e Worker do Orchestrator, garantindo diretório de logs. | `./Infrastructure/Start-Orchestrator.ps1` |
| `Diagnose-Orchestrator.ps1` | Diagnóstico rápido: porta (via `.env`), processos ativos e saúde da API. | `./Infrastructure/Diagnose-Orchestrator.ps1` |
| `Recover-Orchestrator.ps1` | Recuperação forçada: encerra processos Python/PowerShell das automações e reinicia o serviço. | `./Infrastructure/Recover-Orchestrator.ps1` |
| `Install-OrchestratorTask.ps1` | Registra o Orchestrator como Tarefa Agendada do Windows (inicialização automática). | `./Infrastructure/Install-OrchestratorTask.ps1` (PowerShell elevado) |
| `MonitorAutomacoes.ps1` | Monitor independente das automações (watchdog operacional). | `./Infrastructure/MonitorAutomacoes.ps1` |

## Notas

- Todos assumem execução a partir da raiz do repositório e leem configuração do `.env` central.
- `Recover-Orchestrator.ps1` é destrutivo (mata processos): usar apenas quando o diagnóstico indicar travamento.
