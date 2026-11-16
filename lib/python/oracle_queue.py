"""Cliente da fila Oracle via SMB, atendida pelo worker no TSplus.

As automações locais (na estação) executam consultas no Oracle PRD através do
worker VBScript (oracle_worker.vbs) que roda no TSplus (10.62.0.3), a máquina
com rota para o banco (10.62.0.2:1521).

Método único: `execute_query(sql)`. A resposta do worker é um CSV tipado
(nomes, tipos, dados invariantes ao idioma, linha final `#fim`), convertido aqui
para os mesmos tipos do driver nativo: int/float, datetime, bool, str e None.
Escolhido por medição: com 100 mil linhas, ~28% mais rápido de ponta a ponta
que a alternativa em JSON.
"""

from __future__ import annotations

import contextlib
import csv
import io
import json
import math
import os
import re
import socket
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

DEFAULT_QUEUE_DIR = (
    r"\\192.168.62.1\Dados\Planilhas_Conexao\5-Automacoes_Fila\_fila\pedidos"
)
DEFAULT_TIMEOUT_SECONDS = 120.0
# Extrações de domínio (fetch_all): prazo padrão seguro alinhado a automações
# com max_runtime_minutes ~ 15 min (sobescrevível via ORACLE_QUEUE_TIMEOUT_SECONDS).
DEFAULT_EXTRACTION_TIMEOUT_SECONDS = 180.0
QUEUE_TIMEOUT_ENV = "ORACLE_QUEUE_TIMEOUT_SECONDS"
# Tempo máximo esperando o worker reivindicar req_<id>.sql (-> .proc) quando a
# consulta inteira tem prazo maior que isso. Evita ficar preso por horas se o worker caiu.
DEFAULT_CLAIM_TIMEOUT_SECONDS = 90.0
QUEUE_CLAIM_TIMEOUT_ENV = "ORACLE_QUEUE_CLAIM_TIMEOUT_SECONDS"
# Uma resposta é consumida em ~0,1 s depois de publicada. `res_` / `req_` mais velha
# que isto ficou órfã (o cliente desistiu por prazo antes de o worker responder).
# Folga para pedidos longos e para diferença de relógio entre estação e servidor SMB.
ORPHAN_MAX_AGE_SECONDS = 3600.0
# A varredura lista a pasta inteira: no máximo uma por processo e pasta neste intervalo.
SWEEP_INTERVAL_SECONDS = 300.0
_last_sweep: dict[str, float] = {}
CLOCK_SKEW_TTL_SECONDS = 600.0
_clock_skew_cache: dict[str, tuple[float, float]] = {}
LIVENESS_CACHE_SECONDS = 15.0
_liveness_cache: dict[str, tuple[float, dict[str, Any]]] = {}
# Tempo seguido sem conseguir listar a pasta, durante a espera da resposta, a partir
# do qual o share é dado como fora do ar (falha transitória).
SMB_OUTAGE_GRACE_SECONDS = 30.0
POLL_INTERVAL_MIN_SECONDS = 0.05
POLL_INTERVAL_MAX_SECONDS = 0.1
WORKER_HEARTBEAT_FILENAME = "_worker_heartbeat.json"
HEARTBEAT_MAX_AGE_SECONDS = 45.0
BUSY_HEARTBEAT_MAX_AGE_SECONDS = 240.0
_UNC_CONNECT_TIMEOUT_SECONDS = 1.5

_OLE_EPOCH = datetime(1899, 12, 30)
_MS_PER_DAY = 86_400_000
_UNC_RE = re.compile(r"^\\\\([^\\]+)\\")

_TIMEOUT_MSG = (
    "Tempo limite excedido ({timeout}s) aguardando resposta do worker Oracle. "
    "Certifique-se de que o worker (INICIAR_WORKER.bat) esteja rodando no servidor TSplus."
)


class OracleQueueError(RuntimeError):
    """Erro da fila. `kind`: request | blocked | oracle | worker | worker_offline | config | smb."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(f"Erro Oracle reportado pelo worker ({kind}): {message}")
        self.kind = kind
        self.message = message


class OracleQueueBlockedError(OracleQueueError):
    """A consulta foi recusada pelo validador de somente leitura do worker."""


class OracleQueueWorkerOfflineError(OracleQueueError):
    """Worker Oracle no TSplus aparenta estar offline ou não reivindicou a requisição."""


class OracleQueueTransientError(OracleQueueError):
    """Falha de transporte que vale nova tentativa: share SMB inalcançável ou resposta
    truncada (sem `#fim`, contagem de linhas divergente). Erro reportado pelo worker
    (`oracle`, `request`, `worker`), worker offline, bloqueio, resposta malformada e pasta
    inexistente num share alcançável (`config`) não são transitórios. Prazo esgotado
    (TimeoutError) também não: a consulta pode seguir rodando no Oracle, e repetir dobraria a carga.
    """


class OracleQueueTimeoutError(TimeoutError):
    """Prazo total esgotado com o worker vivo (não é worker offline; não é transitória)."""


def _parse_positive_env_seconds(env_name: str, default: float) -> float:
    raw = (os.environ.get(env_name) or "").strip()
    if not raw:
        return default
    value = float(raw)
    if value <= 0 or not math.isfinite(value):
        raise ValueError(f"{env_name} deve ser positivo: {raw!r}")
    return value


def apply_queue_deadline(seconds: float) -> float:
    """Limita `seconds` ao prazo global (ORACLE_QUEUE_DEADLINE_EPOCH).

    Sem a variável, ou com valor inválido/não finito, devolve `seconds` como está.
    Prazo vencido levanta OracleQueueTimeoutError (exit 7); prazo futuro devolve o menor entre
    `seconds` e o restante (com piso de 0,5 s).
    """
    raw_deadline = (os.environ.get("ORACLE_QUEUE_DEADLINE_EPOCH") or "").strip()
    if raw_deadline:
        try:
            remaining = float(raw_deadline) - time.time()
        except ValueError:
            remaining = math.nan
        if math.isfinite(remaining):
            if remaining <= 0:
                raise OracleQueueTimeoutError(
                    "Prazo global de execução (ORACLE_QUEUE_DEADLINE_EPOCH) já atingido."
                )
            return min(seconds, max(0.5, remaining))
    return seconds


def get_queue_timeout(default: float = DEFAULT_EXTRACTION_TIMEOUT_SECONDS) -> float:
    """Prazo de espera da resposta (ORACLE_QUEUE_TIMEOUT_SECONDS). Inválido levanta ValueError."""
    return apply_queue_deadline(_parse_positive_env_seconds(QUEUE_TIMEOUT_ENV, default))


def get_claim_timeout(default: float = DEFAULT_CLAIM_TIMEOUT_SECONDS) -> float:
    """Prazo máximo aguardando reivindicação inicial (.sql -> .proc)."""
    return _parse_positive_env_seconds(QUEUE_CLAIM_TIMEOUT_ENV, default)


@dataclass
class QueueResult:
    """Resultado de `execute_query`."""

    columns: list[str]
    types: list[str]
    rows: list[tuple[Any, ...]]
    elapsed_ms: int | None = None
    worker: str | None = None
    raw_meta: dict[str, Any] = field(default_factory=dict)
    # Id da requisição (nome de req_<id>.sql / res_<id>.csv), preenchido por execute_query.
    req_id: str | None = None

    @property
    def row_count(self) -> int:
        """Linhas da resposta. Derivado de `rows`: `_parse_response` já rejeita
        resposta cujo contador do `#fim` difere das linhas recebidas, então guardar
        o número à parte só duplicaria estado."""
        return len(self.rows)


QUEUE_ACTIONS = frozenset({"query", "explain"})


@dataclass(frozen=True)
class QueueRequestOptions:
    """Opções do pedido à fila: viram os cabeçalhos `--#action`, `--#ttl`,
    `--#timeout`, `--#meta` e `--#max_rows`, mais o pré-processamento do SQL.

    `action` é normalizada (minúsculas, sem espaços) e validada na construção.
    """

    action: str = "query"
    ttl_seconds: int | None = None
    command_timeout_seconds: int | None = None
    meta: str | None = None
    strip_comments: bool = False
    max_rows: int | None = None

    def __post_init__(self) -> None:
        action_clean = self.action.strip().lower()
        if action_clean not in QUEUE_ACTIONS:
            raise ValueError(f"Ação inválida para fila Oracle: {self.action!r}")
        object.__setattr__(self, "action", action_clean)


def get_queue_dir() -> str:
    """Retorna o diretório da fila configurado via ambiente ou padrão."""
    # Vazio conta como ausente, igual ao Lib-Logging.psm1 (`ORACLE_QUEUE_DIR=` no .env).
    return (os.environ.get("ORACLE_QUEUE_DIR") or "").strip() or DEFAULT_QUEUE_DIR


def is_queue_available() -> bool:
    """Verifica se a pasta da fila está acessível para leitura e escrita."""
    q_dir = get_queue_dir()
    if not _check_unc_port_reachable(q_dir):
        return False
    try:
        return os.path.isdir(q_dir) and os.access(q_dir, os.W_OK)
    except OSError:
        return False


def _ensure_csv_field_limit() -> None:
    target = 10 * 1024 * 1024
    if csv.field_size_limit() < target:
        csv.field_size_limit(target)


def _check_unc_port_reachable(path: str) -> bool:
    """Falha rápido (1,5s) se o host UNC SMB (445) estiver fora do ar."""
    match = _UNC_RE.match(path)
    if not match:
        return True
    host = match.group(1)
    try:
        with socket.create_connection(
            (host, 445), timeout=_UNC_CONNECT_TIMEOUT_SECONDS
        ):
            return True
    except OSError:
        return False


def _medir_skew_relogio(base_dir: str) -> float | None:
    """Skew `relógio local - relógio do servidor SMB` por arquivo de sonda (None se falhar)."""
    probe = os.path.join(base_dir, f"_clock_probe_{os.getpid()}_{uuid.uuid4().hex[:8]}.tmp")
    try:
        with open(probe, "wb"):
            pass
        mtime = os.stat(probe).st_mtime
    except OSError:
        return None
    finally:
        _remove_quietly(probe)
    return time.time() - mtime


def _server_now(base_dir: str) -> float:
    """Agora na escala de relógio do servidor SMB da pasta (cache do skew por `base_dir`)."""
    agora_mono = time.monotonic()
    em_cache = _clock_skew_cache.get(base_dir)
    if em_cache is not None and agora_mono - em_cache[0] < CLOCK_SKEW_TTL_SECONDS:
        return time.time() - em_cache[1]
    skew = _medir_skew_relogio(base_dir)
    if skew is None:  # falha não é cacheada: skew anterior (mesmo expirado) ou 0.0
        return time.time() - (em_cache[1] if em_cache is not None else 0.0)
    _clock_skew_cache[base_dir] = (agora_mono, skew)
    return time.time() - skew


def _apply_heartbeat_entry(
    base_dir: str,
    hb_entry: os.DirEntry[str],
    max_age_seconds: float,
    procs: int,
    result: dict[str, Any],
) -> bool:
    """Preenche `result` pelo heartbeat. False só se o `stat()` falhar; JSON ilegível
    (regravação em curso) usa só a idade pelo mtime, com `state` None."""
    try:
        st = hb_entry.stat()
    except OSError:
        return False
    age = max(0.0, _server_now(base_dir) - st.st_mtime)
    result["age_seconds"] = round(age, 1)
    try:
        raw = Path(hb_entry.path).read_text(encoding="cp1252", errors="replace")
        payload: Any = json.loads(raw) if raw.strip() else {}
    except (OSError, ValueError):
        payload = {}
    if isinstance(payload, dict):
        result["state"] = payload.get("state")
        result["oracle_ok"] = payload.get("oracle_ok")
        result["version"] = payload.get("version")
        result["machine"] = payload.get("machine")
        result["req_id"] = payload.get("req_id") or None
    state = str(result["state"] or "").lower()
    limit = (
        BUSY_HEARTBEAT_MAX_AGE_SECONDS
        if (state == "busy" or procs > 0)
        else max_age_seconds
    )
    result["source"] = "heartbeat"
    result["alive"] = age <= limit
    return True


def _reset_liveness_cache() -> None:
    _liveness_cache.clear()


def _liveness_cached(base_dir: str) -> dict[str, Any]:
    """`check_worker_liveness` com cache de 15 s, só para resultado vivo."""
    agora = time.monotonic()
    em_cache = _liveness_cache.get(base_dir)
    if em_cache is not None and agora - em_cache[0] < LIVENESS_CACHE_SECONDS:
        return em_cache[1]
    info = check_worker_liveness(base_dir)
    if info.get("alive"):
        _liveness_cache[base_dir] = (agora, info)
    else:
        _liveness_cache.pop(base_dir, None)
    return info


def _probe_signal_liveness(
    base_dir: str, before: list[str], probe_signal_seconds: float
) -> bool:
    deadline = time.monotonic() + probe_signal_seconds
    while time.monotonic() < deadline:
        time.sleep(0.05)
        try:
            now_names = sorted(
                e.name
                for e in os.scandir(base_dir)
                if e.name in ("_worker_sinal_a.txt", "_worker_sinal_b.txt")
            )
        except OSError:
            return False
        if now_names and now_names != before:
            return True
    return False


def check_worker_liveness(
    queue_dir: str | None = None,
    *,
    max_age_seconds: float = HEARTBEAT_MAX_AGE_SECONDS,
    probe_signal_seconds: float = 0.0,
) -> dict[str, Any]:
    """Inspeciona vivacidade do worker Oracle na fila via `_worker_heartbeat.json`,
    `.proc` ativos e fallback nos arquivos de sinalização `_worker_sinal_{a,b}.txt`.

    Nunca bloqueia em disco remoto offline (sonda TCP 445 antes).
    """
    base_dir = (queue_dir or "").strip() or get_queue_dir()
    result: dict[str, Any] = {
        "alive": False,
        "reachable": False,
        "source": "none",
        "age_seconds": None,
        "state": None,
        "oracle_ok": None,
        "version": None,
        "machine": None,
        "req_id": None,
        "pending_requests": 0,
        "active_procs": 0,
    }
    if not _check_unc_port_reachable(base_dir) or not os.path.isdir(base_dir):
        return result
    result["reachable"] = True

    try:
        entries = list(os.scandir(base_dir))
    except OSError:
        return result

    result["pending_requests"] = sum(
        1 for e in entries if e.name.startswith("req_") and e.name.endswith(".sql")
    )
    procs = sum(
        1 for e in entries if e.name.startswith("req_") and e.name.endswith(".proc")
    )
    result["active_procs"] = procs

    hb_entry = next((e for e in entries if e.name == WORKER_HEARTBEAT_FILENAME), None)
    if hb_entry is not None and _apply_heartbeat_entry(
        base_dir, hb_entry, max_age_seconds, procs, result
    ):
        return result

    if procs > 0:
        result["alive"] = True
        result["source"] = "proc"
        return result

    signal_entries = [
        e for e in entries if e.name in ("_worker_sinal_a.txt", "_worker_sinal_b.txt")
    ]
    if signal_entries:
        result["source"] = "signal"
        result["alive"] = probe_signal_seconds > 0 and _probe_signal_liveness(
            base_dir, sorted(e.name for e in signal_entries), probe_signal_seconds
        )
    return result


def collect_worker_health_snapshot() -> dict[str, Any]:
    """Snapshot padrão de saúde da fila Oracle para diagnóstico e recovery do Orchestrator."""
    mode = os.environ.get("ORACLE_DRIVER_MODE", "").strip().lower()
    if mode != "queue":
        return {
            "enabled": False,
            "alive": None,
            "reachable": None,
            "source": "disabled",
        }
    try:
        info = check_worker_liveness(probe_signal_seconds=0.0)
        info["enabled"] = True
        return info
    # `check_worker_liveness` já trata as falhas de leitura da fila; aqui sobram as de
    # rede/disco (OSError) e host UNC malformado (UnicodeError na resolução, ValueError).
    except (OSError, ValueError) as exc:
        return {
            "enabled": True,
            "alive": False,
            "reachable": False,
            "source": "error",
            "error": str(exc)[:180],
        }


def cleanup_requests_for_exec_id(exec_id: str, queue_dir: str | None = None) -> int:
    """Remove pedidos `req_*.sql` órfãos cujo `--#meta:` contenha `exec_id=<exec_id>`."""
    exec_id_clean = (exec_id or "").strip()
    if not exec_id_clean:
        return 0
    base_dir = (queue_dir or "").strip() or get_queue_dir()
    if not _check_unc_port_reachable(base_dir) or not os.path.isdir(base_dir):
        return 0
    pattern = re.compile(
        rf"(?:^|[:;\s])exec_id={re.escape(exec_id_clean)}(?:$|[;\r\n])"
    )
    removed = 0
    try:
        with os.scandir(base_dir) as entries:
            for entry in entries:
                if not (entry.name.startswith("req_") and entry.name.endswith(".sql")):
                    continue
                try:
                    head = (
                        Path(entry.path)
                        .read_bytes()[:1024]
                        .decode("cp1252", errors="ignore")
                    )
                    if pattern.search(head):
                        _remove_quietly(entry.path)
                        removed += 1
                except OSError:
                    continue
    except OSError:
        return removed
    return removed


# ---------------------------------------------------------------- conversões


def _to_str(v: str) -> str | None:
    return v if v != "" else None


def _to_number(v: str) -> int | float | None:
    if v == "":
        return None
    if "." in v or "E" in v or "e" in v:
        return float(v)
    return int(v)


def _to_datetime(v: str) -> datetime | None:
    if v == "":
        return None
    # Serial OLE: parte inteira = dia (truncada para zero), |fração| = hora do dia,
    # também quando negativo (antes de 30/12/1899: -1,25 = 29/12/1899 06:00).
    # Arredonda ao milissegundo (o texto tem ~10 µs de resolução).
    serial = float(v)
    dias = math.trunc(serial)
    hora_ms = round(abs(serial - dias) * _MS_PER_DAY)
    return _OLE_EPOCH + timedelta(days=dias, milliseconds=hora_ms)


def _ole_serial(value: datetime) -> float:
    """Inverso de `_to_datetime`: dia com sinal mais a hora do dia sempre positiva."""
    dias = (value.date() - _OLE_EPOCH.date()).days
    hora = (value - datetime.combine(value.date(), datetime.min.time())) / timedelta(
        days=1
    )
    return dias - hora if dias < 0 else dias + hora


def _to_bool(v: str) -> bool | None:
    return None if v == "" else v == "1"


_CONVERTERS: dict[str, Callable[[str], Any]] = {
    "number": _to_number,
    "datetime": _to_datetime,
    "boolean": _to_bool,
    "string": _to_str,
}


def _convert_rows(types: list[str], body: list[list[str]]) -> list[tuple[Any, ...]]:
    """Converte por coluna (map com a função do tipo) e remonta as linhas."""
    if not body:
        return []
    converters = [_CONVERTERS.get(t, _to_str) for t in types]
    try:
        columns_data = [
            list(map(conv, col))
            for conv, col in zip(converters, zip(*body, strict=True), strict=True)
        ]
        return list(zip(*columns_data, strict=True))
    except ValueError as e:
        # Malformada (valor que não converte) é determinística: repetir não ajuda.
        raise OracleQueueError("worker", f"Resposta malformada do worker: {e}") from e


def _parse_response(data: bytes) -> QueueResult:
    """Converte o `res_<id>.csv` do worker em QueueResult (ou levanta o erro reportado)."""
    _ensure_csv_field_limit()
    text = data.decode("cp1252", errors="replace")
    if text.startswith("#ERRO"):
        rec = next(csv.reader(io.StringIO(text, newline="")), [])
        kind = rec[1] if len(rec) > 1 else "worker"
        message = rec[2] if len(rec) > 2 else text.strip()
        if kind == "blocked":
            raise OracleQueueBlockedError(kind, message)
        # Erro reportado pelo worker não é repetido: ele não distingue falha interna
        # passageira de determinística (ex.: tipo de coluna que não sabe formatar), e
        # cada tentativa reexecutaria a consulta inteira no Oracle.
        raise OracleQueueError(kind, message)

    records = list(csv.reader(io.StringIO(text, newline="")))
    trailer = records[-1] if records else []
    if len(records) < 3 or not trailer or trailer[0] != "#fim":
        raise OracleQueueTransientError(
            "worker", "Resposta incompleta do worker (sem a linha #fim)."
        )
    columns, types, body = records[0], records[1], records[2:-1]
    try:
        row_count = int(trailer[1])
    except (IndexError, ValueError) as e:
        raise OracleQueueTransientError(
            "worker", f"Linha #fim malformada: {trailer}"
        ) from e
    if row_count != len(body):
        raise OracleQueueTransientError(
            "worker", f"Resposta incompleta: {len(body)} de {row_count} linhas."
        )

    rows = _convert_rows(types, body)

    def _int_or_none(i: int) -> int | None:
        try:
            return int(trailer[i])
        except (IndexError, ValueError):
            return None

    return QueueResult(
        columns=columns,
        types=types,
        rows=rows,
        elapsed_ms=_int_or_none(2),
        worker=trailer[5] if len(trailer) > 5 else None,
        raw_meta={"db_ms": _int_or_none(3), "format_ms": _int_or_none(4)},
    )


# ---------------------------------------------------------------- parâmetros (bind variables)

_BIND_NAME_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$#")
_SAFE_TEXT = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 _-."
)


def _escape_text(value: str) -> str:
    """Codifica como o Unescape do VBScript lê: %uXXXX para tudo fora do conjunto seguro."""
    out = []
    for ch in value:
        if ch in _SAFE_TEXT:
            out.append(ch)
            continue
        raw = ch.encode("utf-16-be")  # fora do BMP vira par de surrogates (2 unidades)
        out.extend(f"%u{raw[i : i + 2].hex().upper()}" for i in range(0, len(raw), 2))
    return "".join(out)


def _bind_key(name: str) -> str:
    key = str(name).lstrip(":").upper()
    if (
        not key
        or not (key[0].isascii() and key[0].isalpha())
        or not set(key) <= _BIND_NAME_CHARS
    ):
        raise ValueError(f"Nome de parâmetro inválido: {name!r}")
    return key


def _encode_params(params: Mapping[str, Any]) -> str:
    """Cabeçalho `--#param:` do pedido. Nomes que só diferem na caixa colidem no
    Oracle (binds são maiúsculos) e são recusados em vez de um sobrescrever o outro."""
    keys = [_bind_key(k) for k in params]
    duplicados = sorted({k for k in keys if keys.count(k) > 1})
    if duplicados:
        raise ValueError(f"Parâmetros repetidos (ignorando a caixa): {duplicados}")
    return "\n".join(_encode_param(k, v) for k, v in params.items())


def _encode_param(name: str, value: Any) -> str:
    """Linha `--#param:` do pedido (o valor nunca entra no texto do SQL)."""
    key = _bind_key(name)
    if value is None:
        enc = "z:"
    elif isinstance(value, bool):
        enc = f"n:{int(value)}"
    elif isinstance(value, (int, Decimal)):
        enc = f"n:{value}"
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Valor float não finito no parâmetro :{key}: {value!r}")
        enc = f"n:{value!r}"
    elif isinstance(value, datetime):
        if value.tzinfo is not None:
            # O serial OLE não carrega fuso; converter em silêncio mudaria o instante.
            raise TypeError(
                f"datetime com fuso não suportado na fila: {name}={value!r}"
            )
        enc = f"d:{_ole_serial(value)!r}"
    elif isinstance(value, date):
        enc = f"d:{(datetime(value.year, value.month, value.day) - _OLE_EPOCH).days}"
    elif isinstance(value, str):
        enc = f"s:{_escape_text(value)}"
    else:
        raise TypeError(
            f"Tipo de parâmetro não suportado na fila: {name}={type(value).__name__}"
        )
    return f"--#param:{key}={enc}"


# ---------------------------------------------------------------- fila


def _resolve_dir(queue_dir: str | None) -> str:
    """Pasta da fila. Raiz alcançável sem a pasta = erro de configuração (não repete);
    raiz inalcançável (share SMB fora do ar) = falha transitória."""
    base_dir = (queue_dir or "").strip() or get_queue_dir()
    if not _check_unc_port_reachable(base_dir):
        raise OracleQueueTransientError(
            "smb",
            f"Servidor SMB da fila Oracle inacessível (porta 445): {base_dir}.",
        )
    if os.path.isdir(base_dir):
        return base_dir
    drive, _ = os.path.splitdrive(base_dir)
    if drive and os.path.isdir(drive + os.sep):
        raise OracleQueueError(
            "config",
            f"Pasta da fila Oracle não existe: {base_dir}. Confira ORACLE_QUEUE_DIR.",
        )
    raise OracleQueueTransientError(
        "smb",
        f"Pasta da fila Oracle não acessível: {base_dir}. Verifique a conexão de rede.",
    )


def _remove_quietly(path: str) -> None:
    with contextlib.suppress(OSError):
        os.remove(path)


def _submit(base_dir: str, req_id: str, sql: str) -> str:
    """Grava `req_<id>.tmp` e renomeia para `.sql` (o worker só vê o arquivo pronto)."""
    tmp_req_path = os.path.join(base_dir, f"req_{req_id}.tmp")
    final_req_path = os.path.join(base_dir, f"req_{req_id}.sql")
    # Estrito: um caractere fora do cp1252 trocado por "?" mudaria o SQL em silêncio.
    # Valores com esses caracteres vão como bind (escapados em %uXXXX).
    try:
        payload = sql.encode("cp1252")
    except UnicodeEncodeError as e:
        raise OracleQueueError(
            "request",
            f"SQL com caractere fora do cp1252 ({sql[e.start:e.end]!r}); passe o valor como bind.",
        ) from e
    try:
        with open(tmp_req_path, "wb") as f:
            f.write(payload)
        os.replace(tmp_req_path, final_req_path)
    except OSError as e:
        _remove_quietly(tmp_req_path)
        raise OracleQueueTransientError(
            "smb", f"Falha ao enviar requisição para a fila Oracle: {e}"
        ) from e
    return final_req_path


_Q_CLOSERS = {"[": "]", "{": "}", "(": ")", "<": ">"}


def _q_quote_end(sql: str, i: int) -> int | None:
    """Índice logo após literal alternativo Oracle `q'<delim>...<delim>'` / `nq'...'`, ou None."""
    if i > 0 and (sql[i - 1].isalnum() or sql[i - 1] in "_$#\"'"):
        return None
    start = i
    if sql[start] in "nN" and start + 1 < len(sql) and sql[start + 1] in "qQ":
        start += 1
    if sql[start] not in "qQ" or not sql.startswith("'", start + 1):
        return None
    delim_pos = start + 2
    n = len(sql)
    if delim_pos >= n:
        return n
    delim = sql[delim_pos]
    if delim.isspace():
        return None
    closer = _Q_CLOSERS.get(delim, delim) + "'"
    end = sql.find(closer, delim_pos + 1)
    return n if end == -1 else end + len(closer)


def strip_sql_comments(sql: str) -> str:
    """Remove comentários `--` e `/* */` fora de strings, `q'...'` e identificadores `"..."`.

    Útil para enviar consultas do catálogo de documentação (que podem conter Unicode fora
    do cp1252 em comentários) sem modificar literais nem alterar a semântica do SQL.
    """
    out: list[str] = []
    n = len(sql)
    i = 0
    while i < n:
        ch = sql[i]
        q_end = _q_quote_end(sql, i) if ch in "qQnN" else None
        if q_end is not None:
            out.append(sql[i:q_end])
            i = q_end
            continue
        nxt = sql[i : i + 2]
        if nxt == "--":
            nl = sql.find("\n", i)
            if nl == -1:
                break
            out.append("\n")
            i = nl + 1
        elif nxt == "/*" and sql[i : i + 3] != "/*+":
            end = sql.find("*/", i + 2)
            if end == -1:
                out.append(sql[i:])
                break
            out.append(" ")
            i = end + 2
        elif ch == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            out.append(sql[i:j])
            i = j
        elif ch == '"':
            end = sql.find('"', i + 1)
            j = n if end == -1 else end + 1
            out.append(sql[i:j])
            i = j
        else:
            out.append(ch)
            i += 1
    return "".join(out).strip()


def _sweep_orphans(
    base_dir: str, max_age_seconds: float = ORPHAN_MAX_AGE_SECONDS
) -> None:
    """Apaga `res_*.csv`/`.tmp` e `req_*.sql`/`.tmp` órfãos para manter a fila enxuta."""
    agora = time.monotonic()
    ultima = _last_sweep.get(base_dir)
    if ultima is not None and agora - ultima < SWEEP_INTERVAL_SECONDS:
        return
    _last_sweep[base_dir] = agora
    limite = _server_now(base_dir) - max_age_seconds
    try:
        with os.scandir(base_dir) as entries:
            velhas = [
                e.path
                for e in entries
                if (
                    e.name.startswith("res_")
                    or (e.name.startswith("req_") and e.name.endswith((".sql", ".tmp")))
                )
                and e.stat().st_mtime < limite
            ]
    except OSError:
        return
    for path in velhas:
        _remove_quietly(path)


def _try_take(path: str) -> bytes | None:
    """Lê e apaga a resposta, se já publicada; None se ainda não está pronta.

    Procura o nome numa listagem da pasta (os.scandir) antes de abrir. Abrir direto
    um nome que ainda não existe faz o cliente SMB do Windows guardar "não existe"
    por 5 s (FileNotFoundCacheLifetime): medido, cada consulta ficava ~5,1 s parada
    mesmo com a resposta pronta em ~0,1 s. Com a listagem: ~0,3 s.
    PermissionError = o worker está concluindo o rename; tenta de novo no próximo ciclo.
    Falha ao listar a pasta (OSError) sobe para `execute_query`, que decide se o
    share caiu de vez.
    """
    name = os.path.basename(path)
    with os.scandir(os.path.dirname(path)) as entries:
        if not any(entry.name == name for entry in entries):
            return None
    try:
        with open(path, "rb") as f:
            data = f.read()
    except (FileNotFoundError, PermissionError):
        return None
    _remove_quietly(path)
    return data


def _poll(timeout_seconds: float) -> Iterator[None]:
    """Esperas crescentes (50 ms -> 100 ms) até o prazo: baixa latência sem martelar o SMB."""
    deadline = time.monotonic() + timeout_seconds
    delay = POLL_INTERVAL_MIN_SECONDS
    while time.monotonic() < deadline:
        yield
        time.sleep(delay)
        delay = min(delay * 1.5, POLL_INTERVAL_MAX_SECONDS)


def _sanitize_meta(meta: str | None) -> str:
    if meta is not None:
        raw = meta
    else:
        exec_id = (
            os.environ.get("HUB_EXEC_ID") or os.environ.get("EXEC_ID") or ""
        ).strip()
        autom = (os.environ.get("HUB_AUTOMATION") or "").strip()
        parts: list[str] = []
        if exec_id:
            parts.append(f"exec_id={exec_id}")
        if autom:
            parts.append(f"automation={autom}")
        raw = ";".join(parts)
    if not raw:
        return ""
    safe = raw.replace("\r", " ").replace("\n", " ").strip()
    return safe.encode("cp1252", errors="replace").decode("cp1252")[:120]


def _worker_vivo(base_dir: str) -> bool:
    return bool(check_worker_liveness(base_dir).get("alive"))


def _ensure_worker_alive_or_raise(base_dir: str) -> None:
    liveness = _liveness_cached(base_dir)
    if liveness.get("source") == "heartbeat" and not liveness.get("alive"):
        age = liveness.get("age_seconds")
        raise OracleQueueWorkerOfflineError(
            "worker_offline",
            f"Worker Oracle no TSplus aparenta estar offline "
            f"(heartbeat parado há {age}s). Execute INICIAR_WORKER.bat no TSplus.",
        )


def build_queue_payload(
    sql: str,
    timeout_seconds: float,
    params: Mapping[str, Any] | None = None,
    options: QueueRequestOptions | None = None,
) -> str:
    """Monta o texto do `req_<id>.sql`: cabeçalhos `--#...` seguidos do SQL."""
    opts = options or QueueRequestOptions()
    body_sql = strip_sql_comments(sql) if opts.strip_comments else sql
    if not body_sql.strip():
        return body_sql

    header_lines: list[str] = []
    meta_str = _sanitize_meta(opts.meta)
    if meta_str:
        header_lines.append(f"--#meta:{meta_str}")
    if opts.action != "query":
        header_lines.append(f"--#action:{opts.action}")
    effective_ttl = (
        int(opts.ttl_seconds)
        if opts.ttl_seconds is not None
        else max(1, min(900, int(round(timeout_seconds))))
    )
    header_lines.append(f"--#ttl:{effective_ttl}")
    if opts.command_timeout_seconds is not None:
        header_lines.append(
            f"--#timeout:{max(1, min(120, int(opts.command_timeout_seconds)))}"
        )
    if opts.max_rows is not None and opts.max_rows > 0:
        header_lines.append(f"--#max_rows:{int(opts.max_rows)}")
    if params and opts.action != "explain":
        header_lines.append(_encode_params(params))
    return "\n".join(header_lines) + "\n" + body_sql


def _await_queue_response(
    base_dir: str,
    final_req_path: str,
    res_path: str,
    timeout_seconds: float,
    effective_claim: float,
) -> bytes:
    """Espera o `res_<id>.csv`. Worker vivo e ocupado não é offline: no prazo de
    reivindicação só falha se morto; no fim do prazo, WorkerOffline se morto, Timeout se vivo."""
    claim_deadline = (
        time.monotonic() + effective_claim
        if 0 < effective_claim < timeout_seconds
        else None
    )
    falha_desde: float | None = None
    for _ in _poll(timeout_seconds):
        try:
            data = _try_take(res_path)
        except OSError as e:
            # Soluço de rede não derruba a espera (repetir reexecutaria a consulta);
            # share fora do ar além da tolerância vira falha transitória.
            agora = time.monotonic()
            if falha_desde is None:
                falha_desde = agora
            if agora - falha_desde >= SMB_OUTAGE_GRACE_SECONDS:
                raise OracleQueueTransientError(
                    "smb",
                    f"Pasta da fila Oracle inacessível há {agora - falha_desde:.0f}s "
                    f"durante a espera da resposta: {e}",
                ) from e
            continue
        falha_desde = None
        if data is not None:
            return data
        if claim_deadline is not None and time.monotonic() >= claim_deadline:
            claim_deadline = None
            if os.path.exists(final_req_path) and not _worker_vivo(base_dir):
                raise OracleQueueWorkerOfflineError(
                    "worker_offline",
                    f"Pedido não foi reivindicado pelo worker Oracle em "
                    f"{effective_claim:.0f}s (TSplus Worker possivelmente parado).",
                )
    if os.path.exists(final_req_path) and not _worker_vivo(base_dir):
        raise OracleQueueWorkerOfflineError(
            "worker_offline",
            f"Pedido não foi reivindicado pelo worker Oracle em "
            f"{timeout_seconds:g}s (TSplus Worker possivelmente parado).",
        )
    raise OracleQueueTimeoutError(_TIMEOUT_MSG.format(timeout=timeout_seconds))


def execute_query(
    sql: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    queue_dir: str | None = None,
    params: Mapping[str, Any] | None = None,
    *,
    options: QueueRequestOptions | None = None,
) -> QueueResult:
    """Executa `sql` (somente leitura) no Oracle PRD pela fila e devolve o resultado tipado.

    `params` são bind variables (`:NOME` no SQL): int, float, Decimal, bool, str,
    date/datetime ou None. Os valores viajam à parte e o worker os passa ao Oracle
    como parâmetros; nunca são colados no texto do SQL. `options` ajusta os
    cabeçalhos do pedido (ação, TTL, meta, limite de linhas).

    Levanta:
        OracleQueueBlockedError: consulta recusada pelo validador (não chegou ao banco).
        OracleQueueWorkerOfflineError: worker offline (heartbeat expirado ou não reivindicado).
        OracleQueueTransientError: share SMB inalcançável ou resposta truncada (vale nova
            tentativa).
        OracleQueueError: erro do Oracle, da requisição, do worker ou de configuração.
        OracleQueueTimeoutError: worker vivo sem resposta em `timeout_seconds`.
    """
    base_dir = _resolve_dir(queue_dir)
    _sweep_orphans(base_dir)
    _ensure_worker_alive_or_raise(base_dir)

    req_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    payload_sql = build_queue_payload(sql, timeout_seconds, params, options)
    final_req_path = _submit(base_dir, req_id, payload_sql)
    res_path = os.path.join(base_dir, f"res_{req_id}.csv")
    try:
        data = _await_queue_response(
            base_dir, final_req_path, res_path, timeout_seconds, get_claim_timeout()
        )
        resultado = _parse_response(data)
        # Identifica a requisição (res_<req_id>.csv) para quem precisa conferir a fila.
        resultado.req_id = req_id
        return resultado
    finally:
        # Requisição que o worker nem chegou a pegar
        if os.path.exists(final_req_path):
            _remove_quietly(final_req_path)
