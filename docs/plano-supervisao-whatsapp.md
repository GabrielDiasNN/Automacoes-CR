# Plano de Supervisão de Sessão WhatsApp
> Versão: 1.0 · Data: 12/07/2026  
> Contexto: motor `whatsapp-web.js` via `WhatsApp-Core.js` (não-oficial) — sem API oficial do WhatsApp Business.

---

## 1. Diagnóstico: O Que Existe Hoje

### 1.1 Stack de Comunicação

| Camada | Arquivo | Função |
|---|---|---|
| Motor Node.js | `lib/WhatsApp-Core.js` | Abre sessão Puppeteer/Chromium, envia mensagem, retorna exit code |
| Wrapper PowerShell | `lib/Send-WhatsApp.ps1` | Recebe parâmetros, executa limpeza de locks, invoca Node |
| Hub de Notificações | `Orchestrator/app/notifications.py` | Orquestra WhatsApp + e-mail com throttling e dispatch assíncrono |
| Agendador | `Orchestrator/app/services/scheduler_runtime.py` | APScheduler com jobs enterprise, auto-retry, snapshots |
| Health Schema | `Orchestrator/app/schemas/system.py` → `SystemHealth` | Exposto em `/api/system/health` |
| Health Builder | `Orchestrator/app/services/system_runtime.py` → `build_health_payload()` | Monta o payload de saúde |

### 1.2 Exit Codes do Motor (definidos em `constants.py`)

```python
EXIT_CODE_MAP = {
    0:  (SUCCESS,  None,                            NONE),
    2:  (SUCCESS,  None,                            NONE),
    3:  (SUCCESS,  None,                            NONE),
    21: (ERROR,    WHATSAPP_SESSION_EXPIRED,         REAUTHENTICATE_WHATSAPP_SESSION),
    24: (PARTIAL,  CHANNEL_DELIVERY_FAILED,          REVIEW_CHANNEL_STATE_BEFORE_REQUEUE),
}
```

O exit code `21` já está **semanticamente mapeado** no Orchestrator, mas **nenhum código reage a ele de forma proativa** — o `notifications.py` apenas loga `"WhatsApp retornou code %d"` e retorna `False`.

### 1.3 Jobs Enterprise Atuais (em `register_enterprise_jobs()`)

| Job ID | Intervalo | Função |
|---|---|---|
| `enterprise_wal_checkpoint` | 30 min | Checkpoint do WAL SQLite |
| `enterprise_daily_purge` | 03h00 cron | Purge de execuções antigas |
| `enterprise_snapshot_purge` | 03h30 cron | Purge de snapshots antigos |
| `enterprise_scheduler_heartbeat` | 15 min | Log de heartbeat do scheduler |
| `enterprise_auto_retry` | 3 min | Auto-retry de ERROR/TIMEOUT dentro do `max_retries` |
| `enterprise_system_health_snapshot` | 5 min | Captura snapshot + dispara alertas de infra |
| `enterprise_file_cleanup` | 02h00 cron | Limpeza de arquivos via PS1 |
| `beneficiamento_live_diario` | 90s | Refresh diário de beneficiamento |
| `beneficiamento_mensal_rollup` | 600s | Refresh mensal de beneficiamento |

**Lacuna:** nenhum job sonda a sessão WhatsApp.

### 1.4 Problemas Identificados

#### Problema A — Silêncio total na falha de sessão (`notifications.py`)
`send_whatsapp_alert()` retorna `False` silenciosamente quando a sessão expira. Não há fallback imediato para e-mail nem atualização de estado global. O operador só descobre a falha se olhar os logs manualmente.

**Localização exata:**
```python
# notifications.py → send_whatsapp_alert() — linhas do bloco subprocess.run
if result.returncode == 0:
    logger.info("Alerta WhatsApp enviado: %s", task_name)
    return True
logger.warning("WhatsApp retornou code %d", result.returncode)  # <- silêncio aqui
return False
```

#### Problema B — `send_infra_alert()` sofre delay de 60s quando sessão está morta
O timeout do subprocess é de `60s`. Como a sessão morta faz o processo falhar só no timeout, alertas críticos de `worker_offline` e `wal_critical` chegam com **1 minuto de atraso** via e-mail.

**Localização exata:**
```python
# notifications.py → send_infra_alert()
result = subprocess.run([...], capture_output=True, timeout=60, check=False)
# Se sessão morta: espera 60s antes de tentar o e-mail
```

#### Problema C — Sem enterprise job de sondagem de sessão (`scheduler_runtime.py`)
`register_enterprise_jobs()` não inclui nenhum job que verifique proativamente se a sessão WhatsApp está viva. O estado só é descoberto na hora de enviar uma mensagem.

#### Problema D — `SystemHealth` não expõe estado da sessão WA (`schemas/system.py`)
```python
class SystemHealth(BaseModel):
    status: str
    timestamp: Any
    database: str
    scheduler: str
    worker: WorkerStatus
    # <- campo whatsapp_session ausente
    pending_tasks: int = 0
    ...
```
O frontend e monitores externos não têm visibilidade do estado da sessão.

#### Problema E — `Keep-WhatsApp-Open.ps1` é interativo, sem supervisão automática
O script foi projetado para uso manual: exibe prompt `"Continuar mesmo assim? (s/N)"` e encerra quando o operador fecha a janela. Não há mecanismo para o Orchestrator reativar a sessão automaticamente após expiração noturna.

---

## 2. Arquitetura da Solução

```
┌─────────────────────────────────────────────────────────────────┐
│                    APScheduler (enterprise jobs)                 │
│                                                                  │
│  enterprise_whatsapp_session_probe (15 min)  ◄── NOVO           │
│     │                                                            │
│     ├─ probe_whatsapp_session() → Send-WhatsApp.ps1 -Mode PROBE │
│     │        │                                                   │
│     │        ├─ exit 0  → _mark_wa_session_alive()              │
│     │        └─ exit 21 → _mark_wa_session_dead()               │
│     │                   → tenta Renew-WhatsApp-Session.ps1      │
│     │                   → se falhar: send_email_alert()         │
│     │                                                            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    notifications.py                              │
│                                                                  │
│  _wa_session_alive: bool  (estado global thread-safe)  ◄── NOVO │
│                                                                  │
│  send_whatsapp_alert()                                           │
│     ├─ sucesso → _mark_wa_session_alive()                        │
│     └─ exit 21 → _mark_wa_session_dead() + fallback e-mail      │
│                                                                  │
│  send_infra_alert()                                              │
│     ├─ is_wa_session_alive() == False → e-mail direto (sem 60s) │
│     └─ is_wa_session_alive() == True  → tenta WA, fallback mail │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  /api/system/health → SystemHealth                              │
│     whatsapp_session: "alive" | "dead" | "unknown"  ◄── NOVO   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Plano de Implementação

### Tarefa 1 — Estado Global de Sessão em `notifications.py`

**Arquivo:** `Orchestrator/app/notifications.py`

Adicionar logo após o bloco de constantes de throttling existente:

```python
# ---------------------------------------------------------------------------
# Estado de sessão WhatsApp (thread-safe)
# ---------------------------------------------------------------------------
# Exit codes do WhatsApp-Core.js que indicam sessão expirada/inválida.
# Mapeados em constants.py: 21 = WHATSAPP_SESSION_EXPIRED
_WA_SESSION_DEAD_CODES = {21}

_wa_session_alive: bool | None = None  # None = ainda não sondado
_wa_session_lock = threading.Lock()


def _mark_wa_session_dead() -> None:
    global _wa_session_alive
    with _wa_session_lock:
        if _wa_session_alive is not False:
            logger.warning("Sessão WhatsApp marcada como MORTA.")
        _wa_session_alive = False


def _mark_wa_session_alive() -> None:
    global _wa_session_alive
    with _wa_session_lock:
        if _wa_session_alive is not True:
            logger.info("Sessão WhatsApp marcada como VIVA.")
        _wa_session_alive = True


def is_wa_session_alive() -> bool | None:
    """Retorna True se viva, False se morta, None se ainda não sondada."""
    with _wa_session_lock:
        return _wa_session_alive
```

**Modificação em `send_whatsapp_alert()`** — substituir o bloco de retorno após `subprocess.run`:

```python
# ANTES:
if result.returncode == 0:
    logger.info("Alerta WhatsApp enviado: %s", task_name)
    return True
logger.warning("WhatsApp retornou code %d", result.returncode)
return False

# DEPOIS:
if result.returncode == 0:
    _mark_wa_session_alive()
    logger.info("Alerta WhatsApp enviado: %s", task_name)
    return True
if result.returncode in _WA_SESSION_DEAD_CODES:
    _mark_wa_session_dead()
    logger.error(
        "Sessão WhatsApp expirou (code %d) ao enviar alerta de '%s'. "
        "Ativando fallback de e-mail.",
        result.returncode, task_name,
    )
    # Fallback imediato para e-mail quando sessão morta
    return send_email_alert(task_name, exec_id, error_msg)
logger.warning("WhatsApp retornou code %d para '%s'.", result.returncode, task_name)
return False
```

**Modificação em `send_infra_alert()`** — adicionar guarda de sessão antes do subprocess:

```python
# No início de send_infra_alert(), logo após a checagem de throttle:
wa_script = os.path.join(PROJECT_ROOT, "lib", "Send-WhatsApp.ps1")
session_known_dead = is_wa_session_alive() is False

whatsapp_sent = False
# Só tenta WhatsApp se a sessão não está confirmadamente morta.
# Isso evita o delay de 60s (timeout do subprocess) em alertas críticos de infra.
if not session_known_dead and os.path.exists(wa_script):
    try:
        result = subprocess.run([...], capture_output=True, timeout=60, check=False)
        if result.returncode == 0:
            _mark_wa_session_alive()
            whatsapp_sent = True
        elif result.returncode in _WA_SESSION_DEAD_CODES:
            _mark_wa_session_dead()
    except subprocess.TimeoutExpired:
        logger.error("Timeout ao enviar alerta de infraestrutura via WhatsApp: %s", component)
    except Exception as e:
        logger.error("Erro ao enviar alerta de infraestrutura via WhatsApp: %s", e)

# E-mail: obrigatório se WA falhou OU sessão estava morta
email_sent = False
if not whatsapp_sent:
    # ... bloco de e-mail existente (sem alteração) ...
```

**Nova função `probe_whatsapp_session()`** — adicionar ao final de `notifications.py`:

```python
def probe_whatsapp_session() -> None:
    """Sonda a sessão WhatsApp via LIST_GROUPS com timeout curto.

    Invocado pelo enterprise job 'enterprise_whatsapp_session_probe' a cada 15 min.
    Se a sessão estiver morta, tenta renovação silenciosa via Renew-WhatsApp-Session.ps1.
    Se a renovação falhar (QR necessário), envia e-mail ao operador.
    """
    wa_script = os.path.join(PROJECT_ROOT, "lib", "Send-WhatsApp.ps1")
    if not os.path.exists(wa_script):
        logger.warning("Probe WA: Send-WhatsApp.ps1 não encontrado.")
        return

    try:
        result = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", wa_script,
                "-Mode", "LIST_GROUPS",
                "-Phone", "probe-check",      # valor dummy; LIST_GROUPS não envia msg
                "-ExecId", "WA_PROBE",
            ],
            capture_output=True,
            timeout=45,   # timeout menor que o de envio — probe deve ser rápido
            check=False,
        )
        if result.returncode == 0:
            _mark_wa_session_alive()
            logger.debug("Probe WA: sessão VIVA.")
            return

        if result.returncode in _WA_SESSION_DEAD_CODES:
            _mark_wa_session_dead()
            logger.warning("Probe WA: sessão MORTA (code %d). Tentando renovação.", result.returncode)
            _try_renew_whatsapp_session()
            return

        logger.warning("Probe WA: exit code inesperado %d.", result.returncode)

    except subprocess.TimeoutExpired:
        logger.warning("Probe WA: timeout (45s). Sessão possivelmente instável.")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Probe WA: erro inesperado: %s", exc)


def _try_renew_whatsapp_session() -> None:
    """Tenta renovar a sessão WA silenciosamente via Renew-WhatsApp-Session.ps1.

    Se a renovação falhar (QR necessário), envia e-mail ao operador com instrução.
    """
    renew_script = os.path.join(PROJECT_ROOT, "lib", "Renew-WhatsApp-Session.ps1")
    if not os.path.exists(renew_script):
        logger.warning("Renew WA: Renew-WhatsApp-Session.ps1 não encontrado. Pulando renovação.")
        _notify_operator_wa_session_expired()
        return

    try:
        result = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", renew_script,
            ],
            capture_output=True,
            timeout=90,
            check=False,
        )
        if result.returncode == 0:
            _mark_wa_session_alive()
            logger.info("Renew WA: sessão renovada com sucesso.")
        else:
            logger.warning("Renew WA: falhou (code %d). QR provavelmente necessário.", result.returncode)
            _notify_operator_wa_session_expired()
    except subprocess.TimeoutExpired:
        logger.warning("Renew WA: timeout (90s). Notificando operador.")
        _notify_operator_wa_session_expired()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Renew WA: erro inesperado: %s", exc)
        _notify_operator_wa_session_expired()


def _notify_operator_wa_session_expired() -> None:
    """Envia e-mail ao operador informando que o QR precisa ser escaneado."""
    alert_email = os.environ.get("AUTOMACAO_ALERT_EMAIL", "")
    if not alert_email:
        logger.warning("AUTOMACAO_ALERT_EMAIL não configurado. Operador não notificado sobre sessão WA expirada.")
        return

    lib_email = os.path.join(PROJECT_ROOT, "lib", "Lib-Email.psm1")
    if not os.path.exists(lib_email):
        logger.warning("Lib-Email.psm1 não encontrada. Operador não notificado sobre sessão WA expirada.")
        return

    agora = get_now_local().strftime("%d/%m/%Y %H:%M:%S")
    subject = f"[AÇÃO NECESSÁRIA] Sessão WhatsApp expirada — {agora}"
    html_body = (
        f"<p><b>A sessão do WhatsApp expirou e não foi possível renová-la automaticamente.</b></p>"
        f"<p>Horário da detecção: {agora}</p>"
        f"<p><b>Ação necessária:</b> Execute o script abaixo no servidor para escanear o QR Code:</p>"
        f"<pre>pwsh -File lib\\Keep-WhatsApp-Open.ps1</pre>"
        f"<p>Enquanto a sessão estiver inativa, os alertas de automações serão entregues apenas por e-mail.</p>"
    )
    ps_command = (
        f"Import-Module '{lib_email}' -Force; "
        f"Send-OutlookEmail -To $env:ALERT_TO "
        f"-Subject $env:ALERT_SUBJECT "
        f"-HtmlBody $env:ALERT_HTML_BODY "
        f"-ExecId 'WA_SESSION_EXPIRED' -LogPath 'ALERT'"
    )
    env = os.environ.copy()
    env["ALERT_TO"] = alert_email
    env["ALERT_SUBJECT"] = subject
    env["ALERT_HTML_BODY"] = html_body
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_command],
            env=env, capture_output=True, timeout=30, check=False,
        )
        if result.returncode == 0:
            logger.info("Operador notificado sobre sessão WA expirada via e-mail.")
        else:
            logger.warning("Falha ao notificar operador sobre sessão WA (e-mail code %d).", result.returncode)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Erro ao notificar operador sobre sessão WA: %s", exc)
```

---

### Tarefa 2 — Enterprise Job de Probe em `scheduler_runtime.py`

**Arquivo:** `Orchestrator/app/services/scheduler_runtime.py`

**Adicionar import** no bloco de imports de `notifications`:
```python
# Já existe: from .. import models, notifications, schemas
# Nenhuma alteração de import necessária — probe_whatsapp_session está em notifications
```

**Modificar `register_enterprise_jobs()`** — adicionar o novo job antes de `register_beneficiamento_live_jobs()`:

```python
def register_enterprise_jobs(retention_days: int) -> None:
    # ... jobs existentes (sem alteração) ...

    scheduler.add_job(
        notifications.probe_whatsapp_session,
        "interval",
        minutes=15,
        id="enterprise_whatsapp_session_probe",
        replace_existing=True,
        misfire_grace_time=120,
    )

    register_beneficiamento_live_jobs()  # já existia — mantido no final
```

**Atualizar `list_scheduled_jobs()`** — o job `enterprise_whatsapp_session_probe` já será exibido automaticamente pelo bloco `elif job.id.startswith("enterprise_")`, que formata o nome como `"System: Whatsapp Session Probe"`. Nenhuma alteração necessária.

---

### Tarefa 3 — Campo `whatsapp_session` em `SystemHealth`

**Arquivo:** `Orchestrator/app/schemas/system.py`

```python
# ANTES:
class SystemHealth(BaseModel):
    status: str
    timestamp: Any
    database: str
    scheduler: str
    worker: WorkerStatus
    pending_tasks: int = 0
    disk_usage_mb: float | None = None
    wal_size_mb: float | None = None
    cpu_usage: float | None = None
    ram_usage_percent: float | None = None

# DEPOIS:
class SystemHealth(BaseModel):
    status: str
    timestamp: Any
    database: str
    scheduler: str
    worker: WorkerStatus
    whatsapp_session: str = "unknown"  # "alive" | "dead" | "unknown"
    pending_tasks: int = 0
    disk_usage_mb: float | None = None
    wal_size_mb: float | None = None
    cpu_usage: float | None = None
    ram_usage_percent: float | None = None
```

---

### Tarefa 4 — Popular `whatsapp_session` em `build_health_payload()`

**Arquivo:** `Orchestrator/app/services/system_runtime.py`

```python
# Adicionar import no topo do arquivo:
from .. import notifications as notif_module

# Modificar build_health_payload():
def build_health_payload(
    db: Session, worker_status: schemas.WorkerStatus
) -> schemas.SystemHealth:
    # ... lógica existente (sem alteração) ...

    # Resolver estado da sessão WA
    wa_alive = notif_module.is_wa_session_alive()
    if wa_alive is True:
        wa_session_str = "alive"
    elif wa_alive is False:
        wa_session_str = "dead"
    else:
        wa_session_str = "unknown"

    return schemas.SystemHealth(
        status=overall,
        timestamp=get_now_local(),
        database=db_status,
        scheduler=sched_status,
        worker=worker_status,
        whatsapp_session=wa_session_str,   # <- novo campo
        pending_tasks=pending,
        disk_usage_mb=get_db_size_mb(),
        wal_size_mb=get_wal_size_mb(),
        cpu_usage=psutil.cpu_percent(),
        ram_usage_percent=psutil.virtual_memory().percent,
    )
```

---

### Tarefa 5 — Novo Script `Renew-WhatsApp-Session.ps1`

**Arquivo:** `lib/Renew-WhatsApp-Session.ps1` *(novo)*

```powershell
# ==============================================================================
# ARQUIVO: Renew-WhatsApp-Session.ps1
# VERSAO : 1.0
# DESCRICAO: Tenta renovar a sessão WhatsApp de forma silenciosa e não-interativa.
#            Invocado automaticamente pelo enterprise_whatsapp_session_probe quando
#            a sessão é detectada como morta.
#            Se o QR Code for necessário (exit 21), retorna exit 21 para que o
#            chamador notifique o operador via e-mail.
# USO INTERNO: Não invocar manualmente. Use Keep-WhatsApp-Open.ps1 para QR manual.
# ==============================================================================
[CmdletBinding()]
param(
    [string]$ClientId       = "hub-global",
    [int]   $TimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"
$LibDir    = $PSScriptRoot
$NodeScript = Join-Path $LibDir "open-whatsapp-session.js"

if (-not (Test-Path $NodeScript)) {
    Write-Error "open-whatsapp-session.js nao encontrado em: $NodeScript"
    exit 1
}

$NodeExe = "node"
if (-not (Get-Command $NodeExe -ErrorAction SilentlyContinue)) {
    $progFiles = [Environment]::GetFolderPath("ProgramFiles")
    $NodeExe   = Join-Path $progFiles "nodejs\node.exe"
    if (-not (Test-Path $NodeExe)) {
        Write-Error "Node.js nao encontrado."
        exit 1
    }
}

$env:NODE_PATH = Join-Path $LibDir "node_modules"

Write-Host "[Renew-WA] Tentando renovação silenciosa da sessão (ClientId: $ClientId)..." -ForegroundColor Gray

$proc = Start-Process `
    -FilePath   $NodeExe `
    -ArgumentList "`"$NodeScript`" `"$ClientId`"" `
    -NoNewWindow `
    -PassThru

$completed = $proc.WaitForExit($TimeoutSeconds * 1000)

if (-not $completed) {
    Write-Host "[Renew-WA] Timeout de ${TimeoutSeconds}s atingido. Encerrando processo." -ForegroundColor Yellow
    try { $proc.Kill() } catch {}
    exit 21
}

if ($proc.ExitCode -eq 0) {
    Write-Host "[Renew-WA] Sessao renovada com sucesso." -ForegroundColor Green
} else {
    Write-Host "[Renew-WA] Falha na renovacao (ExitCode: $($proc.ExitCode)). QR provavelmente necessario." -ForegroundColor Yellow
}

exit $proc.ExitCode
```

---

### Tarefa 6 — Adicionar Modo `LIST_GROUPS` como Probe em `Send-WhatsApp.ps1`

**Arquivo:** `lib/Send-WhatsApp.ps1`

O script já aceita `-Mode` como parâmetro livre e passa para o Node. O único ajuste necessário é remover a validação que exige `$finalPhone` não-vazio quando o modo é `LIST_GROUPS` (probe não usa destino):

```powershell
# ANTES:
if ([string]::IsNullOrWhiteSpace($finalPhone)) { Write-Error "Telefone/ChatId de destino ausente."; exit 1 }

# DEPOIS:
$isProbeMode = $Mode -eq "LIST_GROUPS"
if (-not $isProbeMode -and [string]::IsNullOrWhiteSpace($finalPhone)) {
    Write-Error "Telefone/ChatId de destino ausente."
    exit 1
}
```

E no bloco de construção de `$nodeArgs`, garantir que em modo `LIST_GROUPS` o `$finalPhone` seja passado vazio (o motor já trata esse caso):

```powershell
$nodeArgs = if ($isBatchMode) {
    # ... sem alteração ...
} elseif ($isProbeMode) {
    @(
        "`"$NodeScript`"",
        "`"$ExecId`"",
        "`"LIST_GROUPS`"",
        "`"$finalClientId`"",
        '""',   # phone vazio — LIST_GROUPS não precisa de destino
        '""',   # attachment vazio
        '""',   # message vazia
        "`"$LogFile`""
    )
} else {
    # ... bloco existente sem alteração ...
}
```

---

## 4. Mapa Completo de Alterações

| # | Arquivo | Tipo | Linhas estimadas |
|---|---|---|---|
| 1 | `Orchestrator/app/notifications.py` | Modificação | ~100 linhas |
| 2 | `Orchestrator/app/services/scheduler_runtime.py` | Modificação | ~8 linhas |
| 3 | `Orchestrator/app/schemas/system.py` | Modificação | ~2 linhas |
| 4 | `Orchestrator/app/services/system_runtime.py` | Modificação | ~12 linhas |
| 5 | `lib/Send-WhatsApp.ps1` | Modificação | ~10 linhas |
| 6 | `lib/Renew-WhatsApp-Session.ps1` | **Novo arquivo** | ~45 linhas |

**Arquivos não alterados:** `WhatsApp-Core.js`, `Keep-WhatsApp-Open.ps1`, `models.py`, `constants.py`, `execution_runtime.py`.

---

## 5. Fluxo Completo de Eventos Pós-Implementação

### Cenário A — Sessão expira durante a madrugada

```
03:15  enterprise_whatsapp_session_probe dispara
       └─ probe_whatsapp_session() → Send-WhatsApp.ps1 -Mode LIST_GROUPS
          └─ exit 21
             ├─ _mark_wa_session_dead()
             └─ _try_renew_whatsapp_session() → Renew-WhatsApp-Session.ps1
                └─ exit 21 (QR necessário)
                   └─ _notify_operator_wa_session_expired()
                      └─ e-mail: "Execute pwsh -File lib\Keep-WhatsApp-Open.ps1"

03:20  Operador vê o e-mail, escaneia o QR
03:30  enterprise_whatsapp_session_probe dispara novamente
       └─ exit 0 → _mark_wa_session_alive()
```

### Cenário B — Automação falha enquanto sessão está morta

```
09:00  Automação "OBs Paradas" retorna ERROR
       └─ dispatch_alerts_async() → send_whatsapp_alert()
          └─ exit 21
             ├─ _mark_wa_session_dead()
             └─ fallback: send_email_alert("OBs Paradas", exec_id)
                └─ e-mail entregue IMEDIATAMENTE (sem esperar timeout de 60s)
```

### Cenário C — Alerta de infra com sessão morta

```
worker_offline detectado em enterprise_system_health_snapshot
└─ send_infra_alert("worker_offline", ...)
   └─ is_wa_session_alive() == False
      └─ PULA subprocess WA (sem delay de 60s)
         └─ e-mail direto: [INCIDENTE INFRA] worker_offline
```

### Cenário D — Dashboard mostrando estado da sessão

```
GET /api/system/health
└─ build_health_payload()
   └─ is_wa_session_alive() == False
      └─ SystemHealth.whatsapp_session = "dead"
         └─ frontend pode exibir badge de alerta na UI
```

---

## 6. O Que NÃO Muda

- `WhatsApp-Core.js` — motor robusto, sem necessidade de alteração
- `Keep-WhatsApp-Open.ps1` — mantido como ferramenta manual do operador
- `constants.py` — `EXIT_CODE_MAP` e `FAILURE_REASON_WHATSAPP_SESSION_EXPIRED` já estão corretos
- Lógica de throttling em `notifications.py` — preservada integralmente
- `dispatch_alerts_async()` — sem alteração, o fallback acontece dentro de `send_whatsapp_alert()`

---

## 7. Ordem de Implementação Recomendada

1. **Tarefa 1** (`notifications.py`) — base de tudo; as demais dependem do estado global `_wa_session_alive`
2. **Tarefa 6** (`Renew-WhatsApp-Session.ps1`) — necessário para que a Tarefa 1 não quebre ao chamar o renew
3. **Tarefa 5** (`Send-WhatsApp.ps1`) — necessário para que o probe funcione em modo `LIST_GROUPS`
4. **Tarefa 2** (`scheduler_runtime.py`) — registra o job de probe
5. **Tarefa 3** (`schemas/system.py`) — campo no schema
6. **Tarefa 4** (`system_runtime.py`) — popula o campo no health payload
