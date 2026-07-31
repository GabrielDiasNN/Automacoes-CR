"""Fonte única do ambiente mínimo entregue a subprocessos (D3/1.5).

O worker já montava um ambiente por allowlist para os scripts PowerShell das
automações, justamente para não repassar `ORCHESTRATOR_API_KEY` nem as
credenciais Oracle. Os demais pontos que criam subprocesso — alertas de
WhatsApp/e-mail, limpeza de retenção e refresh do Beneficiamento — faziam
`os.environ.copy()` (ou omitiam `env=`, herdando tudo por padrão), furando essa
allowlist pelo canal de alerta e pelos jobs do scheduler.

Consolidado em 31/07/2026. Qualquer subprocesso novo deve usar
`build_subprocess_env()`; herdar `os.environ` é o caminho errado por omissão.
"""

from __future__ import annotations

import os

# Variáveis de ambiente permitidas nos subprocessos PowerShell (D3/1.5).
# Deliberadamente SEM: ORCHESTRATOR_API_KEY, ORACLE_READONLY_PASSWORD e
# qualquer outro segredo carregado do `.env` pelo Start-Orchestrator.ps1.
ALLOWED_ENV_KEYS = frozenset(
    {
        "PATH",
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "COMPUTERNAME",
        "USERNAME",
        "ORACLE_CLIENT_LIB_DIR",
        "ORACLE_CLIENT_PATH",
        # Caminho do tnsnames.ora, não credencial. Lido por
        # `beneficiamento/oracle.py`; usuário/senha/DSN vêm do `.env` via
        # `load_dotenv(override=True)`, nunca do ambiente herdado.
        "TNS_ADMIN",
        "HUB_API_PORT",
        "PYTHONUTF8",
        "PYTHONIOENCODING",
    }
)


def build_subprocess_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Ambiente filtrado pela allowlist, acrescido de `extra`.

    `extra` carrega o que o subprocesso precisa receber explicitamente (ExecId,
    corpo do alerta, correlation_id). Como é aplicado depois do filtro, uma
    chave em `extra` sempre vence — é passagem intencional, não herança.
    """
    env = {k: v for k, v in os.environ.items() if k in ALLOWED_ENV_KEYS}
    if extra:
        env.update(extra)
    return env
