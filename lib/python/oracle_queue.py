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
import math
import os
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

DEFAULT_QUEUE_DIR = (
    r"\\192.168.62.1\Dados\Planilhas_Conexao\5-Automacoes_Fila\_fila\pedidos"
)
DEFAULT_TIMEOUT_SECONDS = 120.0
# Extrações de domínio (fetch_all) não tinham teto no driver nativo; na fila o
# prazo de espera vem de ORACLE_QUEUE_TIMEOUT_SECONDS, com este padrão folgado.
DEFAULT_EXTRACTION_TIMEOUT_SECONDS = 1800.0
QUEUE_TIMEOUT_ENV = "ORACLE_QUEUE_TIMEOUT_SECONDS"
# Uma resposta é consumida em ~0,1 s depois de publicada. `res_` mais velha que
# isto ficou órfã (o cliente desistiu por prazo antes de o worker responder).
# Folga larga por causa da diferença de relógio entre o TSplus e a estação.
ORPHAN_MAX_AGE_SECONDS = 3600.0
# A varredura lista a pasta compartilhada inteira: no máximo uma por processo e
# pasta neste intervalo, não uma por consulta.
SWEEP_INTERVAL_SECONDS = 300.0
_last_sweep: dict[str, float] = {}
# Tempo seguido sem conseguir listar a pasta, durante a espera da resposta, a partir
# do qual o share é dado como fora do ar (falha transitória).
SMB_OUTAGE_GRACE_SECONDS = 30.0
POLL_INTERVAL_MIN_SECONDS = 0.02
POLL_INTERVAL_MAX_SECONDS = 0.1

_OLE_EPOCH = datetime(1899, 12, 30)
_MS_PER_DAY = 86_400_000

_TIMEOUT_MSG = (
    "Tempo limite excedido ({timeout}s) aguardando resposta do worker Oracle. "
    "Certifique-se de que o worker (INICIAR_WORKER.bat) esteja rodando no servidor TSplus."
)


class OracleQueueError(RuntimeError):
    """Erro da fila. `kind`: request | blocked | oracle | worker | config | smb."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(f"Erro Oracle reportado pelo worker ({kind}): {message}")
        self.kind = kind
        self.message = message


class OracleQueueBlockedError(OracleQueueError):
    """A consulta foi recusada pelo validador de somente leitura do worker."""


class OracleQueueTransientError(OracleQueueError):
    """Falha de transporte que vale nova tentativa: share SMB inalcançável ou resposta
    truncada (sem `#fim`, contagem de linhas divergente). Erro reportado pelo worker
    (`oracle`, `request`, `worker`), bloqueio, resposta malformada e pasta inexistente
    num share alcançável (`config`) não são transitórios. Prazo esgotado (TimeoutError) também não: a
    consulta pode seguir rodando no Oracle, e repetir dobraria a carga."""


def get_queue_timeout(default: float = DEFAULT_EXTRACTION_TIMEOUT_SECONDS) -> float:
    """Prazo de espera da resposta (ORACLE_QUEUE_TIMEOUT_SECONDS). Inválido levanta ValueError."""
    raw = (os.environ.get(QUEUE_TIMEOUT_ENV) or "").strip()
    if not raw:
        return default
    value = float(raw)
    if value <= 0:
        raise ValueError(f"{QUEUE_TIMEOUT_ENV} deve ser positivo: {raw!r}")
    return value


@dataclass
class QueueResult:
    """Resultado de `execute_query`."""

    columns: list[str]
    types: list[str]
    rows: list[tuple[Any, ...]]
    row_count: int
    elapsed_ms: int | None = None
    worker: str | None = None
    raw_meta: dict[str, Any] = field(default_factory=dict)


def get_queue_dir() -> str:
    """Retorna o diretório da fila configurado via ambiente ou padrão."""
    # Vazio conta como ausente, igual ao Lib-Logging.psm1 (`ORACLE_QUEUE_DIR=` no .env).
    return (os.environ.get("ORACLE_QUEUE_DIR") or "").strip() or DEFAULT_QUEUE_DIR


def is_queue_available() -> bool:
    """Verifica se a pasta da fila está acessível para leitura e escrita."""
    q_dir = get_queue_dir()
    try:
        return os.path.isdir(q_dir) and os.access(q_dir, os.W_OK)
    except OSError:
        return False


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
        row_count=row_count,
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
    if not key or not set(key) <= _BIND_NAME_CHARS:
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


def _sweep_orphans(
    base_dir: str, max_age_seconds: float = ORPHAN_MAX_AGE_SECONDS
) -> None:
    """Apaga `res_*.csv` órfãs: respostas que o worker publicou depois de o cliente
    desistir por prazo. Sem isso elas se acumulam e encarecem a listagem de todos."""
    agora = time.monotonic()
    ultima = _last_sweep.get(base_dir)
    if ultima is not None and agora - ultima < SWEEP_INTERVAL_SECONDS:
        return
    _last_sweep[base_dir] = agora
    limite = time.time() - max_age_seconds
    try:
        with os.scandir(base_dir) as entries:
            velhas = [
                e.path
                for e in entries
                if e.name.startswith("res_") and e.stat().st_mtime < limite
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
    """Esperas crescentes (20 ms -> 100 ms) até o prazo: baixa latência sem martelar o SMB."""
    deadline = time.monotonic() + timeout_seconds
    delay = POLL_INTERVAL_MIN_SECONDS
    while time.monotonic() < deadline:
        yield
        time.sleep(delay)
        delay = min(delay * 1.5, POLL_INTERVAL_MAX_SECONDS)


def execute_query(
    sql: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    queue_dir: str | None = None,
    params: Mapping[str, Any] | None = None,
) -> QueueResult:
    """Executa `sql` (somente leitura) no Oracle PRD pela fila e devolve o resultado tipado.

    `params` são bind variables (`:NOME` no SQL): int, float, Decimal, bool, str,
    date/datetime ou None. Os valores viajam à parte e o worker os passa ao Oracle
    como parâmetros; nunca são colados no texto do SQL.

    Levanta:
        OracleQueueBlockedError: consulta recusada pelo validador (não chegou ao banco).
        OracleQueueTransientError: share SMB inalcançável ou resposta truncada (vale nova
            tentativa).
        OracleQueueError: erro do Oracle, da requisição, do worker ou de configuração.
        TimeoutError: o worker não respondeu dentro de `timeout_seconds`. A consulta
            não é cancelada no Oracle; a resposta tardia é limpa por `_sweep_orphans`.
    """
    base_dir = _resolve_dir(queue_dir)
    _sweep_orphans(base_dir)
    req_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    if params:
        sql = f"{_encode_params(params)}\n{sql}"
    final_req_path = _submit(base_dir, req_id, sql)
    res_path = os.path.join(base_dir, f"res_{req_id}.csv")
    falha_desde: float | None = None
    try:
        for _ in _poll(timeout_seconds):
            try:
                data = _try_take(res_path)
            except OSError as e:
                # Soluço de rede não derruba a espera (repetir reexecutaria a consulta);
                # share fora do ar além da tolerância vira falha transitória, em vez de
                # girar até o prazo e acabar num TimeoutError que ninguém repete.
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
                return _parse_response(data)
        raise TimeoutError(_TIMEOUT_MSG.format(timeout=timeout_seconds))
    finally:
        # Requisição que o worker nem chegou a pegar
        if os.path.exists(final_req_path):
            _remove_quietly(final_req_path)
