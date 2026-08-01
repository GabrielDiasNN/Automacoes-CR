# pylint: disable=broad-exception-caught
from collections.abc import Callable

import oracledb


def init_oracle_thick_mode(
    client_lib: str, tns_admin: str | None, log_fn: Callable[..., None]
) -> None:
    """Initializes Oracle Thick Mode client.

    log_fn signature: (message: str, level: str = "INFO") -> None
    Swallows AlreadyInitialized warnings (safe to call multiple times).
    """
    try:
        oracledb.init_oracle_client(lib_dir=client_lib, config_dir=tns_admin)
        log_fn("Thick Mode ativado.")
    except Exception as e:
        log_fn(f"Aviso Thick client: {e}", "WARN")
