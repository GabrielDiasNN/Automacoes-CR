---
name: automacao-monitor
description: Use esta skill para gerenciar o MonitorAutomacoes.ps1 e o arquivo de configuração de agendamentos config.json.
---

# Gestão do Monitor de Automações

## Objetivo
Operar o sistema central de agendamento, garantindo que as tarefas rodem nos horários previstos e que novos scripts sejam integrados corretamente sem conflitos.

## Arquivos Chave
| Arquivo | Descrição |
|---|---|
| `MonitorAutomacoes.ps1` (v3.5) | Core do monitor — Hot Reload, Mutex, gestão de processos |
| `config.json` | Definição de tarefas e horários (codificação: UTF-8) |
| `Logs/YYYY-MM_Monitor.log` | Log central do monitor |
| `Startup_Error.txt` | Criado automaticamente em erros críticos de inicialização |

## Procedimentos Comuns

### Adicionar Nova Tarefa
1. Certifique-se de que o `Trigger_Automation.vbs` da automação funciona **manualmente** antes de cadastrá-la.
2. Adicione o bloco no `config.json` seguindo o schema:
   ```json
   {
     "name": "Nome Amigável",
     "scriptPath": "C:\\Automacoes\\NomePasta\\Trigger_Automation.vbs",
     "enabled": true,
     "preventOverlap": true,
     "waitForExit": false,
     "schedule": {
       "daysOfWeek": [1, 2, 3, 4, 5],
       "hours": [8, 14],
       "minutes": [0]
     }
   }
   ```
3. O monitor detecta a mudança automaticamente (**Hot Reload** ativo — sem reinício necessário).

### Parâmetros do `config.json`
| Campo | Descrição |
|---|---|
| `enabled` | `false` para desabilitar sem remover |
| `preventOverlap` | `true` = não inicia nova execução se a anterior ainda roda |
| `waitForExit` | `true` = monitor aguarda o fim do processo (síncrono) |
| `hours: []` | Array vazio = nunca dispara por hora (somente por `minutes`) |

## Troubleshooting do Monitor
- **Monitor não inicia**: Verifique o `Startup_Error.txt` na raiz. Geralmente JSON malformado.
- **Tarefa não disparou em UTC**: O monitor usa o relógio do sistema Windows (hora local). Verifique se o `config.json` está em hora local, não UTC.
- **Sobreposição ignorada**: Se `preventOverlap=true` e o processo anterior ainda está rodando (PID ativo), o disparo é suprimido e registrado como `WARN` no log.
- **Hot Reload não funcionou**: Verifique se o `config.json` foi salvo em **UTF-8** (sem BOM problemático).

## Regras
- **Mutex**: Apenas uma instância do monitor por vez (`Global\MonitorAutomacoesMutex`).
- **UTF-8**: O `config.json` deve ser salvo com codificação UTF-8.
- **Caminhos**: Sempre use caminhos absolutos começando com `C:\Automacoes\`.
- **Heartbeat**: O monitor registra sua saúde a cada 1 hora no log — use para confirmar que está ativo.
