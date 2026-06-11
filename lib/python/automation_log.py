from typing import Callable
import sys
from datetime import datetime


def make_logger(tag: str) -> Callable[[str, str, str], None]:
    """Returns a log(message, level, exec_id) function that writes to stderr with the given tag."""
    def log(message: str, level: str = "INFO", exec_id: str = "manual") -> None:
        ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        sys.stderr.write(f"[{ts}] [{tag}] [{level}] [ExecId:{exec_id}] {message}\n")
        sys.stderr.flush()
    return log
