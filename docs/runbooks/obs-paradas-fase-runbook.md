# Runbook — OBs Paradas Fase (OBP-04)

## Diagnóstico rápido

```powershell
# Ver últimos logs
Get-Content "OBs Paradas Fase\Logs\*.log" -Tail 50

# Verificar sessão WhatsApp
Test-Path "lib\.wwebjs_auth\session-hub-global\Default\Local Storage\leveldb\*.log"
```

## Falhas comuns

### ExitCode=21 — Sessão expirada
```
lib\Authenticate-WhatsApp.bat
```
Escaneie o QR code. Aguarde "Cliente pronto" antes de fechar.

### ExitCode=24 — Chrome não inicializa
Verificar processos zumbi:
```powershell
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
  Where-Object { $_.CommandLine -like "*wwebjs_auth*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```
Depois re-autenticar.

### ExitCode=3 — Oracle indisponível
Verificar conectividade Oracle (string em `ORACLE_CONNECT_STRING` no `.env`). Aguardar recovery automático (3 tentativas com backoff 30/60/120s).

### Resetar delivery_state.json (forçar reenvio de todas as fases)

Use quando o lote foi alterado externamente ou quando as fases precisam ser reenviadas independente do hash salvo:

```powershell
Remove-Item "OBs Paradas Fase\delivery_state.json" -Force -ErrorAction SilentlyContinue
Remove-Item "OBs Paradas Fase\obs_state.json"      -Force -ErrorAction SilentlyContinue
Remove-Item "OBs Paradas Fase\obs_state.json.tmp"  -Force -ErrorAction SilentlyContinue
```

Na próxima execução, o script tratará todas as fases como não entregues e realizará um novo envio completo.

### ExitCode=4 — Falha parcial de fases (algumas entregues, outras não)

Verificar quais fases falharam:
```powershell
Get-Content "OBs Paradas Fase\delivery_state.json" | ConvertFrom-Json | Select-Object -ExpandProperty phases
```

As fases com `success=false` serão reenviadas automaticamente na próxima execução agendada (sem intervenção). Para forçar reenvio imediato:
```powershell
# Opção 1: aguardar próximo cron (07:00 ou 14:00)
# Opção 2: acionar manualmente via Orchestrator API
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/automations/OBP-04/trigger" -Method POST -Headers @{"X-API-Key"="<api_key>"}
```

Para forçar reenvio de TODAS as fases (ignorar estado):
```powershell
Remove-Item "OBs Paradas Fase\delivery_state.json" -Force -ErrorAction SilentlyContinue
Remove-Item "OBs Paradas Fase\obs_state.json"      -Force -ErrorAction SilentlyContinue
```

### Mensagens na fila (ACK não confirmado)
Abrir Chrome virtual com sessão hub-global para drenar a fila:
```powershell
pwsh -File lib\Keep-WhatsApp-Open.ps1
```
