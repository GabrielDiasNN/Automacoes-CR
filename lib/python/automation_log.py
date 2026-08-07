import sys
from collections.abc import Callable
from datetime import datetime


def ensure_utf8_streams() -> None:
    """Reconfigura stdout/stderr para UTF-8 quando o objeto suportar.

    `hasattr(..., "reconfigure")` é a guarda correta: verifica exatamente o
    método que será chamado, ao contrário de checar `.encoding != "utf-8"`,
    que ainda lança ``AttributeError`` se o stream não tiver `.encoding`.
    Chamar antes de qualquer escrita em stdout/stderr, para interoperar com o
    encaminhamento Base64 dos wrappers PowerShell.
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


def make_logger(tag: str) -> Callable[[str, str, str], None]:
    """Returns a log(message, level, exec_id) function that writes to stderr with the given tag."""

    def log(message: str, level: str = "INFO", exec_id: str = "manual") -> None:
        ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        sys.stderr.write(f"[{ts}] [{tag}] [{level}] [ExecId:{exec_id}] {message}\n")
        sys.stderr.flush()

    return log
