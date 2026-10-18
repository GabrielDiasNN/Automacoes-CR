"""Retenção de backups automáticos e leitura de WORKER_MAX_CONCURRENCY (sem banco)."""

import os
from pathlib import Path

import pytest
from app.runtime import get_worker_max_concurrency
from app.services import system_runtime

pytestmark = pytest.mark.unitario


def _backups_automaticos(quantidade: int) -> list[str]:
    return [
        f"automacoes_backup_202610{dia:02d}_120000.db"
        for dia in range(1, quantidade + 1)
    ]


def _gravar(pasta: Path, nomes: list[str]) -> None:
    for nome in nomes:
        (pasta / nome).write_bytes(b"x")


def test_retencao_remove_so_o_automatico_mais_antigo_alem_do_limite(
    tmp_path: Path,
) -> None:
    automaticos = _backups_automaticos(8)
    _gravar(tmp_path, automaticos + ["Antigo.db", "abc.db", "trabalho.db"])

    removidos = system_runtime.aplicar_retencao_backups(str(tmp_path))

    assert removidos == automaticos[:1]
    restantes = {p.name for p in tmp_path.iterdir()}
    assert restantes == set(automaticos[1:]) | {"Antigo.db", "abc.db", "trabalho.db"}


def test_retencao_abaixo_do_limite_nao_remove_nada(tmp_path: Path) -> None:
    _gravar(tmp_path, _backups_automaticos(7) + ["manual.db"])

    assert not system_runtime.aplicar_retencao_backups(str(tmp_path))
    assert len(list(tmp_path.iterdir())) == 8


def test_retencao_falha_ao_remover_vira_aviso_e_segue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    automaticos = _backups_automaticos(8)
    _gravar(tmp_path, automaticos)
    remocao_original = os.remove

    def remover_com_bloqueio(caminho: str) -> None:
        if caminho.endswith(automaticos[0]):
            raise PermissionError("arquivo em uso")
        remocao_original(caminho)

    monkeypatch.setattr(os, "remove", remover_com_bloqueio)

    assert not system_runtime.aplicar_retencao_backups(str(tmp_path))
    assert (tmp_path / automaticos[0]).exists()


def test_worker_max_concurrency_padrao_e_valor_valido(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WORKER_MAX_CONCURRENCY", raising=False)
    assert get_worker_max_concurrency() == 4

    monkeypatch.setenv("WORKER_MAX_CONCURRENCY", "8")
    assert get_worker_max_concurrency() == 8


@pytest.mark.parametrize("valor", ["abc", "0", "-2", ""])
def test_worker_max_concurrency_invalido_levanta_erro_claro(
    monkeypatch: pytest.MonkeyPatch, valor: str
) -> None:
    monkeypatch.setenv("WORKER_MAX_CONCURRENCY", valor)
    with pytest.raises(ValueError, match="WORKER_MAX_CONCURRENCY inválido"):
        get_worker_max_concurrency()


def test_rota_de_versao_nao_cai_com_concorrencia_invalida(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configuração inválida é apontada pelo diagnóstico; a rota de versão segue respondendo."""
    from datetime import datetime  # pylint: disable=import-outside-toplevel

    monkeypatch.setenv("WORKER_MAX_CONCURRENCY", "0")
    monkeypatch.setattr(system_runtime, "get_schema_version", lambda: "teste")
    payload = system_runtime.build_version_payload(datetime.now())
    assert payload.max_workers == 4


def test_worker_concorrencia_invalida_sai_com_codigo_definido_e_log_estruturado(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regressão (achado 22): valor inválido não derruba a importação com traceback cru."""
    import json  # pylint: disable=import-outside-toplevel

    import worker  # pylint: disable=import-outside-toplevel

    monkeypatch.setenv("WORKER_MAX_CONCURRENCY", "abc")
    with pytest.raises(SystemExit) as info:
        worker._ler_max_workers()  # pylint: disable=protected-access
    assert info.value.code == worker.EXIT_CONFIG_INVALIDA
    evento = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert evento["event"] == "config.invalid"
    assert "WORKER_MAX_CONCURRENCY" in evento["message"]
