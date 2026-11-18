"""Testes unitarios do check Oracle do pre-flight em lib/python/hub_runner.py.

Reproduzem a decisao de Test-AutomationPreFlight -CheckOracle e de
Get-OraclePreFlightExitCode (lib/Lib-Logging.psm1, lib/Lib-Oracle.psm1 e
lib/Lib-OracleEndpoint.psm1), um desfecho por teste. Sem rede e sem Oracle: a sonda TCP
e um dublê, a pasta da fila e tmp_path, e o mtime do heartbeat e recuado para a idade
do cenario. Nenhum teste toca a pasta real da fila.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import hub_runner as hr
import pytest

# Os dublês de teste sao deliberadamente minimos (um metodo cada).
# pylint: disable=too-few-public-methods

FILA_UNC = "\\\\servidor-fila.exemplo.invalid\\Dados\\fila"
TNSNAMES = """DBPRD.WORLD =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = banco.exemplo.invalid)(PORT = 1600))
    (CONNECT_DATA = (SERVICE_NAME = prd))
  )

OUTRO =
  (DESCRIPTION = (ADDRESS = (PROTOCOL = TCP)(HOST = outro.exemplo.invalid)))
"""


@pytest.fixture(autouse=True)
def _ambiente_isolado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sem variaveis reais de Oracle, fila ou tnsnames: cada teste define o que usa."""
    for chave in (
        "ORACLE_CONNECT_STRING",
        "ORACLE_QUEUE_DIR",
        "TNS_ADMIN",
        "ORACLE_CLIENT_PATH",
    ):
        monkeypatch.delenv(chave, raising=False)


class _SondaFalsa:
    """Dublê da sonda TCP: registra (host, porta, prazo) e devolve o resultado configurado."""

    def __init__(self, resultado: bool = True) -> None:
        self.resultado = resultado
        self.chamadas: list[tuple[str, int, float]] = []

    def __call__(self, host: str, porta: int, prazo_s: float) -> bool:
        self.chamadas.append((host, porta, prazo_s))
        return self.resultado


class _HeartbeatFalso:
    """Dublê da leitura do heartbeat: devolve o registro configurado ou levanta o erro."""

    def __init__(
        self,
        resposta: hr.WorkerHeartbeat | None = None,
        erro: OSError | None = None,
    ) -> None:
        self.resposta = resposta
        self.erro = erro

    def __call__(self, _pasta: Path) -> hr.WorkerHeartbeat | None:
        if self.erro is not None:
            raise self.erro
        return self.resposta


def _pasta_fila(tmp_path: Path, *nomes: str) -> Path:
    """Pasta de fila local com os arquivos pedidos (vazios)."""
    fila = tmp_path / "fila"
    fila.mkdir(exist_ok=True)
    for nome in nomes:
        (fila / nome).write_bytes(b"")
    return fila


def _heartbeat(
    fila: Path, *, idade_s: float, estado: str = "idle", versao: str = "2.6.1"
) -> None:
    """Grava _worker_heartbeat.json com o mtime recuado em idade_s segundos."""
    caminho = fila / "_worker_heartbeat.json"
    caminho.write_text(
        json.dumps({"state": estado, "version": versao}), encoding="utf-8"
    )
    instante = time.time() - idade_s
    os.utime(caminho, (instante, instante))


def _codigo(preflight: hr.OraclePreflight, *, outros_ok: bool = True) -> int:
    """Codigo de falha com os demais checks ok (padrao) ou reprovados."""
    return hr.oracle_preflight_exit_code(preflight, outros_checks=lambda: outros_ok)


def _status(preflight: hr.OraclePreflight) -> hr.StatusFila:
    """Status da fila do preflight, com a garantia de que o modo queue o produziu."""
    assert preflight.status is not None
    return preflight.status


def test_codigos_de_falha_sao_os_do_run_ps1() -> None:
    assert hr.EXIT_PREFLIGHT_FALHA == 9
    assert hr.EXIT_ORACLE_WORKER_OFFLINE == 26


def test_limiares_de_heartbeat_sao_os_do_get_test_oracle_queue_worker_alive() -> None:
    """-MaxAgeSeconds 45 e -BusyMaxAgeSeconds 240 do PowerShell."""
    assert hr.MAX_IDADE_HEARTBEAT_S == 45
    assert hr.MAX_IDADE_HEARTBEAT_OCUPADO_S == 240


def test_pasta_inexistente_marca_fila_off_e_devolve_26(tmp_path: Path) -> None:
    pre = hr.oracle_preflight(modo="queue", pasta_fila=str(tmp_path / "nao-existe"))

    assert pre.ok is False
    assert pre.linhas[0].startswith("ERRO: Oracle Queue (")
    assert " Off (pasta inacessivel (" in pre.linhas[0]
    assert _codigo(pre) == 26
    assert _codigo(pre, outros_ok=False) == 9


def test_smb_fora_do_ar_consulta_a_porta_445_e_nao_acessa_o_compartilhamento() -> None:
    sonda = _SondaFalsa(resultado=False)

    pre = hr.oracle_preflight(modo="queue", pasta_fila=FILA_UNC, sonda_tcp=sonda)

    assert sonda.chamadas == [("servidor-fila.exemplo.invalid", 445, 1.5)]
    assert pre.linhas == (
        f"ERRO: Oracle Queue ({FILA_UNC}) Off "
        "(servidor SMB servidor-fila.exemplo.invalid inacessivel (porta 445))",
    )
    assert _codigo(pre) == 26


def test_heartbeat_fresco_deixa_a_fila_on_com_versao_do_worker(tmp_path: Path) -> None:
    fila = _pasta_fila(tmp_path)
    _heartbeat(fila, idade_s=5, versao="2.6.1")

    pre = hr.oracle_preflight(modo="queue", pasta_fila=str(fila))

    assert pre.ok is True
    assert pre.linhas[0].startswith("OK: Oracle Queue (")
    assert pre.linhas[0].endswith("(heartbeat ativo (5s, state=idle) worker 2.6.1)")
    assert _status(pre).source == "heartbeat"
    assert _codigo(pre) == 9


def test_heartbeat_expirado_marca_worker_offline_e_devolve_26(tmp_path: Path) -> None:
    fila = _pasta_fila(tmp_path)
    _heartbeat(fila, idade_s=600)

    pre = hr.oracle_preflight(modo="queue", pasta_fila=str(fila))

    assert pre.ok is False
    assert " Worker Offline (heartbeat expirado ha " in pre.linhas[0]
    assert "(limite 45s)" in pre.linhas[0]
    assert _codigo(pre) == 26
    assert _codigo(pre, outros_ok=False) == 9


@pytest.mark.parametrize(
    ("estado", "idade_s", "vivo"),
    [
        ("busy", 100, True),
        ("BUSY", 100, True),
        ("idle", 100, False),
        ("busy", 300, False),
    ],
)
def test_worker_ocupado_usa_o_limite_de_240_segundos(
    tmp_path: Path, estado: str, idade_s: float, vivo: bool
) -> None:
    fila = _pasta_fila(tmp_path)
    _heartbeat(fila, idade_s=idade_s, estado=estado)

    pre = hr.oracle_preflight(modo="queue", pasta_fila=str(fila))

    assert _status(pre).alive is vivo


def test_requisicao_em_processamento_eleva_o_limite_para_240_segundos(
    tmp_path: Path,
) -> None:
    fila = _pasta_fila(tmp_path, "req_1700000000_abcdef12.proc")
    _heartbeat(fila, idade_s=100, estado="idle")

    pre = hr.oracle_preflight(modo="queue", pasta_fila=str(fila))

    assert _status(pre).alive is True


def test_heartbeat_ilegivel_mantem_a_idade_pelo_mtime_e_estado_vazio(
    tmp_path: Path,
) -> None:
    fila = _pasta_fila(tmp_path)
    caminho = fila / "_worker_heartbeat.json"
    caminho.write_text("{trunc", encoding="utf-8")
    instante = time.time() - 5
    os.utime(caminho, (instante, instante))

    pre = hr.oracle_preflight(modo="queue", pasta_fila=str(fila))

    assert _status(pre).alive is True
    assert _status(pre).versao == ""
    assert pre.linhas[0].endswith("(heartbeat ativo (5s, state=))")


def test_sem_heartbeat_mas_com_sinal_legado_conta_como_vivo(tmp_path: Path) -> None:
    fila = _pasta_fila(tmp_path, "_worker_sinal_b.txt")

    pre = hr.oracle_preflight(modo="queue", pasta_fila=str(fila))

    assert _status(pre).alive is True
    assert _status(pre).source == "signal"
    assert "arquivo de sinal legado presente" in pre.linhas[0]


def test_sem_heartbeat_mas_com_processo_ativo_conta_como_vivo(tmp_path: Path) -> None:
    fila = _pasta_fila(tmp_path, "req_1700000000_abcdef12.proc")

    pre = hr.oracle_preflight(modo="queue", pasta_fila=str(fila))

    assert _status(pre).alive is True
    assert _status(pre).source == "proc"


def test_sem_heartbeat_nem_sinal_fica_offline(tmp_path: Path) -> None:
    fila = _pasta_fila(tmp_path)

    pre = hr.oracle_preflight(modo="queue", pasta_fila=str(fila))

    assert _status(pre).alive is False
    assert pre.linhas[0].endswith(
        "Worker Offline (sem heartbeat nem sinal do worker na fila)"
    )
    assert _codigo(pre) == 26


def test_falha_ao_ler_heartbeat_sem_sinal_fica_offline_com_a_causa(
    tmp_path: Path,
) -> None:
    fila = _pasta_fila(tmp_path)

    pre = hr.oracle_preflight(
        modo="queue",
        pasta_fila=str(fila),
        ler_heartbeat=_HeartbeatFalso(erro=OSError("acesso negado")),
    )

    assert _status(pre).alive is False
    assert (
        "falha ao ler heartbeat: acesso negado; sem sinal do worker na fila"
        in pre.linhas[0]
    )
    assert _codigo(pre) == 26


def test_falha_ao_ler_heartbeat_com_processo_ativo_continua_vivo(
    tmp_path: Path,
) -> None:
    fila = _pasta_fila(tmp_path, "req_1700000000_abcdef12.proc")

    pre = hr.oracle_preflight(
        modo="queue",
        pasta_fila=str(fila),
        ler_heartbeat=_HeartbeatFalso(erro=OSError("acesso negado")),
    )

    assert _status(pre).alive is True
    assert _status(pre).source == "proc"


@pytest.mark.parametrize(("idade_s", "vivo"), [(45.04, True), (45.06, False)])
def test_idade_do_heartbeat_e_arredondada_a_1_casa_como_no_ps(
    tmp_path: Path, idade_s: float, vivo: bool
) -> None:
    """Round(idade, 1) antes de comparar: 45,04 s vira 45,0 (vivo); 45,06 s vira 45,1 (morto)."""
    fila = _pasta_fila(tmp_path)
    instante = 1_000_000.0
    caminho = fila / "_worker_heartbeat.json"
    caminho.write_text(
        json.dumps({"state": "idle", "version": "2.6.1"}), encoding="utf-8"
    )
    os.utime(caminho, (instante, instante))

    def leitor(pasta: Path) -> hr.WorkerHeartbeat | None:
        return hr.read_worker_heartbeat(pasta, relogio=lambda _p: instante + idade_s)

    pre = hr.oracle_preflight(modo="queue", pasta_fila=str(fila), ler_heartbeat=leitor)

    assert _status(pre).alive is vivo


def test_pasta_da_fila_vazia_e_erro_de_configuracao_9() -> None:
    pre = hr.oracle_preflight(modo="queue", pasta_fila="   ")

    assert pre.ok is False
    assert pre.status is None
    assert pre.linhas[0].startswith(
        "ERRO: Oracle Queue (DEFAULT_QUEUE_DIR nao encontrado"
    )
    assert _codigo(pre) == 9


def test_outros_checks_so_rodam_com_o_worker_parado(tmp_path: Path) -> None:
    fila = _pasta_fila(tmp_path)
    _heartbeat(fila, idade_s=5)
    pre = hr.oracle_preflight(modo="queue", pasta_fila=str(fila))
    chamadas: list[bool] = []

    def registra() -> bool:
        chamadas.append(True)
        return True

    assert hr.oracle_preflight_exit_code(pre, outros_checks=registra) == 9
    assert not chamadas


def test_excecao_nos_outros_checks_reprova_o_preflight(tmp_path: Path) -> None:
    fila = _pasta_fila(tmp_path)
    pre = hr.oracle_preflight(modo="queue", pasta_fila=str(fila))

    def quebra() -> bool:
        raise RuntimeError("falha no disco")

    assert hr.oracle_preflight_exit_code(pre, outros_checks=quebra) == 9


def test_outros_checks_que_devolvem_false_reprovam(tmp_path: Path) -> None:
    fila = _pasta_fila(tmp_path)
    pre = hr.oracle_preflight(modo="queue", pasta_fila=str(fila))

    def reprova() -> bool:
        return False

    assert hr.oracle_preflight_exit_code(pre, outros_checks=reprova) == 9


def test_sem_connect_string_vira_warn_e_nao_reprova() -> None:
    sonda = _SondaFalsa()

    pre = hr.oracle_preflight(modo="thick", conexao="", sonda_tcp=sonda)

    assert pre.linhas == (
        "WARN: Oracle host nao configurado (ORACLE_CONNECT_STRING ausente)",
    )
    assert pre.ok is True
    assert pre.status is None
    assert not sonda.chamadas
    assert _codigo(pre) == 9


def test_ezconnect_resolve_host_e_porta_e_sonda_por_3_segundos() -> None:
    sonda = _SondaFalsa(resultado=True)

    pre = hr.oracle_preflight(
        modo="thick",
        conexao="tcps://db.exemplo.invalid:2484/SVC?wallet_location=/x",
        sonda_tcp=sonda,
    )

    assert sonda.chamadas == [("db.exemplo.invalid", 2484, 3.0)]
    assert pre.linhas == (
        "OK: Oracle (db.exemplo.invalid -> db.exemplo.invalid:2484) On",
    )
    assert pre.ok is True


def test_porta_do_oracle_sem_resposta_e_warn_e_nao_reprova() -> None:
    """Oracle inalcancavel fora do modo queue e WARN: o PS nao reprova por ele."""
    pre = hr.oracle_preflight(
        modo="thick",
        conexao="db.exemplo.invalid:1521/SVC",
        sonda_tcp=_SondaFalsa(resultado=False),
    )

    assert pre.linhas == (
        "WARN: Oracle (db.exemplo.invalid -> db.exemplo.invalid:1521) Off "
        "(porta TCP sem resposta em 3 s)",
    )
    assert pre.ok is True
    assert _codigo(pre) == 9


def test_alias_do_tnsnames_com_sufixo_de_dominio_resolve_host_e_porta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "tnsnames.ora").write_text(TNSNAMES, encoding="utf-8")
    monkeypatch.setenv("TNS_ADMIN", str(tmp_path))

    assert hr.resolve_oracle_endpoint("DBPRD") == hr.OracleEndpoint(
        "banco.exemplo.invalid", 1600
    )
    assert hr.resolve_oracle_endpoint("dbprd") == hr.OracleEndpoint(
        "banco.exemplo.invalid", 1600
    )
    assert hr.resolve_oracle_endpoint("OUTRO") == hr.OracleEndpoint(
        "outro.exemplo.invalid", 1521
    )


def test_tnsnames_do_oracle_client_path_em_network_admin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = tmp_path / "network" / "admin"
    admin.mkdir(parents=True)
    (admin / "tnsnames.ora").write_text(TNSNAMES, encoding="utf-8")
    monkeypatch.setenv("ORACLE_CLIENT_PATH", str(tmp_path))

    assert hr.find_tnsnames() == admin / "tnsnames.ora"
    assert hr.resolve_oracle_endpoint("OUTRO") == hr.OracleEndpoint(
        "outro.exemplo.invalid", 1521
    )


def test_alias_fora_do_tnsnames_sem_endereco_vira_warn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "tnsnames.ora").write_text(TNSNAMES, encoding="utf-8")
    monkeypatch.setenv("TNS_ADMIN", str(tmp_path))
    sonda = _SondaFalsa()

    pre = hr.oracle_preflight(modo="thick", conexao="INEXISTENTE", sonda_tcp=sonda)

    assert hr.resolve_oracle_endpoint("INEXISTENTE") is None
    assert pre.linhas == (
        "WARN: Oracle (INEXISTENTE) sem endpoint resolvido (alias ausente no tnsnames.ora)",
    )
    assert not sonda.chamadas


def test_alias_sem_tnsnames_nem_separador_nao_vira_host() -> None:
    assert hr.resolve_oracle_endpoint("ALIAS") is None


def test_ezconnect_sem_porta_usa_1521() -> None:
    assert hr.resolve_oracle_endpoint("host.exemplo.invalid/SVC") == hr.OracleEndpoint(
        "host.exemplo.invalid", 1521
    )


@pytest.mark.parametrize(
    ("conexao", "esperado"),
    [
        ("tcps://h.exemplo.invalid:2484/SVC", "h.exemplo.invalid"),
        ("//h.exemplo.invalid/SVC", "h.exemplo.invalid"),
        ("h.exemplo.invalid:1521", "h.exemplo.invalid"),
        ("ALIAS", "ALIAS"),
        ("   ", ""),
        ("", ""),
    ],
)
def test_host_da_conexao_segue_a_extracao_do_pre_flight(
    conexao: str, esperado: str
) -> None:
    assert hr.oracle_host(conexao) == esperado


def test_modo_que_nao_e_queue_nunca_devolve_26() -> None:
    pre = hr.oracle_preflight(modo="auto", conexao="", sonda_tcp=_SondaFalsa())

    assert _codigo(pre, outros_ok=True) == 9


def test_relogio_do_servidor_apaga_a_sonda_e_cai_no_local_sem_pasta(
    tmp_path: Path,
) -> None:
    agora = hr.relogio_servidor(tmp_path)

    assert abs(agora - time.time()) < 60
    assert not list(tmp_path.glob("_clock_probe_*"))
    assert abs(hr.relogio_servidor(tmp_path / "nao-existe") - time.time()) < 60
