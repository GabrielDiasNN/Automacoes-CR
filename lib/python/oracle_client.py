"""Conexão Oracle adaptativa: Thin Mode primeiro, Thick Mode só quando o servidor exigir.

Política, controlada pela variável `ORACLE_DRIVER_MODE`:

- `auto` (padrão): abre a conexão em Thin Mode nativo. Se o servidor oferecer
  só o verificador de senha legado (DPY-3015, `oracledb.NotSupportedError`),
  ativa o Thick Mode via `oracledb.init_oracle_client()` e reconecta. Qualquer
  outro erro é propagado, sem fallback.
- `thick`: ativa o Thick Mode antes da primeira conexão. Serve de rollback sem
  deploy, caso o Thin Mode apresente problema.

Uma tentativa thin que falha não trava o modo do driver: o gerenciador do
python-oracledb só registra o modo quando o bloco de conexão termina sem
exceção. Por isso o fallback funciona enquanto nenhuma conexão thin tiver
sido concluída no processo. Depois da primeira conexão thin bem-sucedida,
o modo fica fixo em Thin, e um DPY-3015 posterior é propagado (reinicie o
processo para trocar de modo).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import oracledb

LogFn = Callable[..., None]

DRIVER_MODE_ENV = "ORACLE_DRIVER_MODE"
DRIVER_MODE_AUTO = "auto"
DRIVER_MODE_THICK = "thick"

# Verificador de senha que o Thin Mode não suporta (ex.: 0x939, legado).
LEGACY_VERIFIER_MARKER = "DPY-3015"

# Estado do processo: `thin_consolidado` vira True após a primeira conexão Thin
# concluída, quando o modo do driver fica fixado em Thin.
_ESTADO: dict[str, bool] = {"thin_consolidado": False}

# Prazos de rede aplicados a toda conexão. `expire_time` é em minutos;
# os demais são em segundos. Sem `retry_count` no driver: com o banco fora do ar,
# 3 retries de 15 s levariam o connect a ~1 min, acima do prazo do Orchestrator,
# e o retry de quem chama (`make_oracle_retry`) nunca chegaria a agir.
CONNECT_PARAMS: dict[str, Any] = {
    "tcp_connect_timeout": 15.0,
    "expire_time": 2,
}


@dataclass(frozen=True)
class DriverMode:
    """Modo ativo do driver. `client_version` só existe em Thick Mode."""

    mode: str
    label: str
    client_version: tuple[int, ...] | None


def get_driver_mode() -> str:
    """Modo pedido pelo ambiente. Valor inválido levanta ValueError (falha alta)."""
    value = (os.environ.get(DRIVER_MODE_ENV) or DRIVER_MODE_AUTO).strip().lower()
    if value not in (DRIVER_MODE_AUTO, DRIVER_MODE_THICK):
        raise ValueError(
            f"{DRIVER_MODE_ENV} inválido: {value!r} (use 'auto' ou 'thick')."
        )
    return value


def describe_driver_mode() -> DriverMode:
    """Descreve o modo ativo do driver, para logs e para o diagnóstico."""
    if oracledb.is_thin_mode():
        return DriverMode(
            mode="thin",
            label=f"Thin Mode (python-oracledb {oracledb.__version__}, sem Oracle Client)",
            client_version=None,
        )
    version = tuple(int(part) for part in oracledb.clientversion())
    text = ".".join(str(part) for part in version)
    return DriverMode(
        mode="thick",
        label=f"Thick Mode (Oracle Client {text})",
        client_version=version,
    )


def init_oracle_thick_mode(
    client_lib: str | None, tns_admin: str | None, log_fn: LogFn
) -> None:
    """Ativa o Thick Mode. Idempotente: não faz nada se o Thick Mode já estiver ativo.

    Falhas reais (biblioteca ausente, versão incompatível) são propagadas. No
    fallback, engolir o erro faria a reconexão falhar sem causa clara.
    """
    if not oracledb.is_thin_mode():
        return
    try:
        # Caminho vazio vira None: "" não é um diretório e mascararia o DPY-3015.
        oracledb.init_oracle_client(lib_dir=client_lib or None, config_dir=tns_admin)
    except oracledb.ProgrammingError as exc:
        # ERR_LIBRARY_ALREADY_INITIALIZED: init repetido com outros argumentos
        # (corrida entre threads, ex.: connect_within). O cliente já está ativo.
        if "already called" not in str(exc):
            raise
        log_fn("Oracle Client já inicializado neste processo; reutilizando.", "WARN")
        return
    log_fn(f"Thick Mode ativado via '{client_lib}'.")


def _connect_once(
    user: str, password: str, dsn: str, config_dir: str | None
) -> oracledb.Connection:
    extra: dict[str, Any] = {}
    # `config_dir` é aceito pelo Thin Mode. No Thick Mode o diretório vai para
    # `init_oracle_client`, então não é repassado aqui.
    if config_dir and oracledb.is_thin_mode():
        extra["config_dir"] = config_dir
    return oracledb.connect(
        user=user, password=password, dsn=dsn, **CONNECT_PARAMS, **extra
    )


def connect_adaptive(  # pylint: disable=too-many-arguments
    *,
    user: str,
    password: str,
    dsn: str,
    client_lib: str | None,
    tns_admin: str | None,
    log_fn: LogFn,
) -> oracledb.Connection:
    """Abre uma conexão no modo adaptativo (ver a docstring do módulo)."""
    if get_driver_mode() == DRIVER_MODE_THICK:
        init_oracle_thick_mode(client_lib, tns_admin, log_fn)
    try:
        conexao = _connect_once(user, password, dsn, tns_admin)
    except oracledb.NotSupportedError as exc:
        if LEGACY_VERIFIER_MARKER not in str(exc) or not oracledb.is_thin_mode():
            raise
        if _ESTADO["thin_consolidado"]:
            # Modo já fixado em Thin neste processo: sem reinício não há como trocar.
            # Propaga a causa original em vez de falhar no init com outra mensagem.
            raise oracledb.NotSupportedError(
                f"{exc} Este processo já concluiu uma conexão Thin, então o modo ficou "
                "fixo em Thin. Reinicie o processo para usar o Thick Mode."
            ) from exc
    else:
        _ESTADO["thin_consolidado"] = oracledb.is_thin_mode()
        return conexao
    log_fn(
        "Servidor ofereceu verificador de senha legado (DPY-3015): "
        "ativando Thick Mode e reconectando.",
        "WARN",
    )
    init_oracle_thick_mode(client_lib, tns_admin, log_fn)
    return _connect_once(user, password, dsn, tns_admin)
