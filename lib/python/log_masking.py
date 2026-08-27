"""Mascaramento de dados sensiveis em log (paridade com Protect-SensitiveData).

Fonte da paridade: lib/Lib-Logging.psm1 -> Protect-SensitiveData. As tres
implementacoes (PS, Python, Node) sao mantidas alinhadas por teste de contrato.
Defesa em profundidade: o runtime mascara antes de gravar; o Orchestrator
revalida na ingestao (sanitize_log_payload).
"""

from __future__ import annotations

import re

_EMAIL_RE = re.compile(
    r"([a-zA-Z0-9._%+-])[a-zA-Z0-9._%+-]+@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"
)
_SECRET_RE = re.compile(
    r"(token|key|password|pass|secret|credential|auth|apikey|client_secret)"
    r"([:= ]\s*)([a-zA-Z0-9._%+-]{4,})",
    re.IGNORECASE,
)
_ORACLE_HOST_RE = re.compile(
    r"(DESCRIPTION\s*=\s*\(ADDRESS\s*=\s*\(PROTOCOL\s*=\s*TCP\)\(HOST\s*=\s*)[^)]+"
)


def mask_sensitive(text: str) -> str:
    """Mascara e-mails, segredos rotulados e host de connect string Oracle."""
    if not text or not text.strip():
        return ""
    masked = _EMAIL_RE.sub(r"\g<1>***@\g<2>", text)
    masked = _SECRET_RE.sub(r"\g<1>\g<2>[REDACTED]", masked)
    masked = _ORACLE_HOST_RE.sub(r"\g<1>[HIDDEN]", masked)
    return masked
