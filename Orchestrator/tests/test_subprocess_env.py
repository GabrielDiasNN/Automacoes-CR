"""Regressão: segredos não podem vazar para subprocessos por herança de ambiente.

Até 31/07/2026 a allowlist `_ALLOWED_ENV_KEYS` era local ao `worker.py`. Os
demais criadores de subprocesso não tinham acesso a ela e faziam
`os.environ.copy()` — ou omitiam `env=`, herdando tudo por padrão:

- `notifications.py` (alertas de WhatsApp e e-mail, 4 call sites)
- `scheduler_runtime.run_file_cleanup` (job diário de retenção)
- `beneficiamento_refresh.run_beneficiamento_refresh`
- `env_admin.sync_global_test_mode_env`

Ou seja: a superfície que a allowlist fechava para os scripts de automação
continuava aberta pelo canal de alerta e pelos jobs do scheduler.
"""

import os
from unittest.mock import patch

import pytest
from app.subprocess_env import ALLOWED_ENV_KEYS, build_subprocess_env

SEGREDOS = {
    "ORCHESTRATOR_API_KEY": "chave-secreta",
    "ORACLE_READONLY_PASSWORD": "senha-oracle",
    "ORACLE_READONLY_USER": "usuario-oracle",
    "ORACLE_CONNECT_STRING": "dbprd",
    "SMTP_PASSWORD": "senha-smtp",
}


@pytest.mark.unitario
def test_segredos_nao_entram_no_ambiente_do_subprocesso() -> None:
    with patch.dict(os.environ, SEGREDOS):
        env = build_subprocess_env()

    for chave in SEGREDOS:
        assert chave not in env, f"{chave} vazou para o ambiente do subprocesso"


@pytest.mark.unitario
def test_variaveis_operacionais_sao_preservadas() -> None:
    with patch.dict(os.environ, {"PATH": "C:\\Windows", "TEMP": "C:\\Temp"}):
        env = build_subprocess_env()

    assert env["PATH"] == "C:\\Windows"
    assert env["TEMP"] == "C:\\Temp"


@pytest.mark.unitario
def test_extra_e_aplicado_e_vence_a_allowlist() -> None:
    """`extra` é passagem intencional — deve sobrescrever o herdado."""
    with patch.dict(os.environ, {"TEMP": "C:\\Herdado"}):
        env = build_subprocess_env({"EXEC_ID": "EXEC_1", "TEMP": "C:\\Explicito"})

    assert env["EXEC_ID"] == "EXEC_1"
    assert env["TEMP"] == "C:\\Explicito"


@pytest.mark.unitario
def test_configuracao_do_beneficiamento_chega_ao_subprocesso() -> None:
    """A allowlist não pode cortar configuração operacional junto com segredo.

    `BENEFICIAMENTO_HISTORICO_DB` redireciona o banco histórico
    (`data/schema.py`). Filtrada, o subprocesso de refresh escrevia no caminho
    default enquanto o pai lia o redirecionado — dois bancos divergentes, sem
    erro. Os demais são knobs de tuning lidos por `settings.py` no import, que
    degradavam para o default em silêncio.
    """
    configuracao = {
        "BENEFICIAMENTO_HISTORICO_DB": "D:\\dados\\historico.db",
        "BENEFICIAMENTO_ORACLE_TIMEOUT_MS": "25000",
        "BENEFICIAMENTO_WALL_CLOCK_SECONDS": "30",
        "BENEFICIAMENTO_FETCH_ARRAY_SIZE": "2000",
        "BENEFICIAMENTO_FETCH_BATCH_SIZE": "8000",
    }
    with patch.dict(os.environ, configuracao):
        env = build_subprocess_env()

    for chave, valor in configuracao.items():
        assert env.get(chave) == valor, f"{chave} não chegou ao subprocesso"


@pytest.mark.unitario
def test_allowlist_nao_contem_segredo_conhecido() -> None:
    """Guarda contra alguém adicionar uma chave sensível à allowlist."""
    proibidos = {"KEY", "PASSWORD", "SECRET", "TOKEN", "PASSWD", "CREDENTIAL"}
    for chave in ALLOWED_ENV_KEYS:
        assert not any(
            termo in chave.upper() for termo in proibidos
        ), f"{chave} tem cara de segredo e está na allowlist de subprocessos"


@pytest.mark.unitario
def test_worker_delega_para_a_fonte_unica() -> None:
    """O worker não pode manter uma cópia divergente da allowlist."""
    import worker  # pylint: disable=import-outside-toplevel

    # pylint: disable-next=protected-access
    allowlist_do_worker = worker._ALLOWED_ENV_KEYS
    assert allowlist_do_worker is ALLOWED_ENV_KEYS
