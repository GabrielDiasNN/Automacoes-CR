# Runbook de Operação — Automacoes Hub

## Objetivo

Guia rápido para diagnóstico e resposta inicial a incidentes operacionais do hub.

---

## 1. Monitor sem heartbeat

### Sintomas

- `Monitor_Metrics.json` sem atualização recente.
- `dashboard-state.json` sem atualização recente.
- Dashboard parado.
- Ausência de novas linhas no log mensal do monitor.

### Verificações

1. Confirmar se `MonitorAutomacoes.ps1` está em execução.
2. Verificar timestamp dos artefatos de métricas e estado.
3. Ler o log consolidado do monitor.
4. Executar validação segura sem disparar tarefas:
   - `-RunOnce -SkipTaskExecution`
   - `-RunOnce -DryRun`

### Ação inicial

- Se o monitor estiver parado, reiniciar de forma controlada.
- Se houver erro de startup, inspecionar arquivo de erro e configuração.
- Se houver problema transitório de config, validar `config.json`.

### Rollback

- Reverter a última alteração em scripts/config.
- Restaurar versão anterior validada do monitor.

---

## 2. Excel travado ou workbook bloqueado

### Sintomas

- Execução excede o tempo esperado.
- Workbook abre em somente leitura.
- Processo `Excel.exe` fica preso após falha.
- Log retorna timeout de processamento ou workbook bloqueado.

### Verificações

1. Identificar qual automação disparou o problema.
2. Correlacionar pelo `ExecId`.
3. Verificar se existe processo órfão de Excel.
4. Verificar lock de arquivo e permissões.
5. Revisar log localizado da automação.

### Ação inicial

- Encerrar com segurança o processo órfão relacionado.
- Validar se o arquivo XLSM está acessível.
- Rodar novo teste controlado antes de reabrir agenda normal.

### Rollback

- Reverter mudança recente no runner.
- Restaurar fluxo anterior caso timeout/cleanup tenha introduzido regressão.

---

## 3. WhatsApp exige reautenticação

### Sintomas

- Exit code 21.
- Janela de PAIRING necessária.
- Sessão expirada.
- Falha de envio após bootstrap do Node.

### Verificações

1. Confirmar erro 21 no log.
2. Verificar presença e estado da sessão em `.wwebjs_auth`.
3. Validar `whatsapp-config.json`.
4. Confirmar se o bridge está em AUTO ou PAIRING.
5. Verificar se há lock `.sendwhatsapp.lock`.

### Ação inicial

- Abrir fluxo PAIRING.
- Realizar pareamento do QR Code.
- Reexecutar teste simples controlado.
- Confirmar que o lock foi liberado.
- Confirmar que a mensagem não caiu em cooldown ou bloqueio concorrente.

### Rollback

- Voltar à versão anterior do bridge se a regressão for recente.
- Manter envio por e-mail operacional enquanto o WhatsApp é estabilizado.

---

## 4. Falha por configuração inválida do WhatsApp

### Sintomas

- Exit code 22.
- Falha imediata antes do envio.
- Erro de validação de `whatsapp-config.json`.

### Verificações

1. Validar campos `target`, `message`, `runtime`, `retry`, `paths`, `idempotency`.
2. Confirmar existência dos caminhos configurados.
3. Confirmar anexo quando aplicável.

### Ação inicial

- Corrigir configuração.
- Executar novo teste controlado.
- Confirmar retorno 0.

---

## 5. Cooldown ou concorrência no bridge

### Sintomas

- Exit code 23 ou 40.
- Envio adiado ou ignorado.
- Lock ativo no bridge.

### Verificações

1. Confirmar `ExecId`.
2. Revisar estado de idempotência.
3. Revisar lock local.
4. Confirmar se outra execução silenciosa está ativa.

### Ação inicial

- Não forçar múltiplas execuções paralelas.
- Aguardar cooldown quando aplicável.
- Reexecutar apenas após liberação segura.

---

## 6. Ordem padrão de diagnóstico

1. Ler log consolidado.
2. Correlacionar `ExecId`.
3. Verificar artefatos de estado.
4. Verificar exit code.
5. Rodar validação segura.
6. Só então executar correção ou retry.

---

## 7. Checklist antes de fechar incidente

- causa provável identificada
- impacto operacional registrado
- evidência salva em log
- rollback conhecido
- teste controlado executado
- operação normal restabelecida
