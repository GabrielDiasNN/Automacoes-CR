from __future__ import annotations

# pylint: disable=wrong-import-position
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
# `lib/python` (oracle_session) é resolvido pelo próprio `beneficiamento.oracle`.
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from beneficiamento.runner import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
