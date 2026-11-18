"""Testes unitarios do runner de OBs Paradas Fase (OBs Paradas Fase/run_obs_paradas.py).

Sem Oracle, sem WhatsApp e sem rede. Os passos Python (hr.run_python_step), o envio em lote
(hw.send_whatsapp), a limpeza de Chrome (powershell.exe), o mutex OBP-04 (hr.AutomationMutex,
que so existe no Windows), a CLI de alerta e o disco sao substituidos por dubles. Os arquivos
da automacao vivem em tmp_path: nunca em OBs Paradas Fase/ nem em Logs/ do repositorio.

Um teste por desfecho do run.ps1 anterior (git show HEAD:"OBs Paradas Fase/run.ps1"): saidas
0, 1, 2 (idempotencia do extract, gerador sem OB, lote ja entregue, phase_cards vazio), 3, 4,
9, 21, 22, 26 e 27. Mais o dry-run, que nao envia nem confirma estado.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import hub_runner as hr
import hub_whatsapp as hw
import pytest
from tests.carregadores_modulos import carregar_modulo_automacao

# Os dubles de teste sao deliberadamente minimos (um metodo cada).
# pylint: disable=too-few-public-methods

RAIZ_REPO = Path(__file__).resolve().parents[2]
PASTA_OBP = RAIZ_REPO / "OBs Paradas Fase"
ro: Any = carregar_modulo_automacao("run_obs_paradas", PASTA_OBP / "run_obs_paradas.py")

TARGET = "120363000000000000@g.us"
HASH_NOVO = "HASH-NOVO"
CARDS = [
    {
        "phase_key": "FASE_A",
        "phase_display": "Fase A",
        "image_path": "images/FASE_A.png",
        "caption": "Legenda A",
    },
    {
        "phase_key": "FASE_B",
        "phase_display": "Fase B",
        "image_path": "images/FASE_B.png",
        "caption": "Legenda B",
    },
]


def _ok(exit_code: int = 0, output: str = "") -> hr.PythonStepResult:
    """Desfecho de um passo Python bem-sucedido."""
    return hr.PythonStepResult(
        success=True,
        idempotent=False,
        non_retryable=False,
        output=output,
        exit_code=exit_code,
        attempts=1,
    )


def _idempotente() -> hr.PythonStepResult:
    """Desfecho do exit 2: idempotencia, sem retry."""
    return hr.PythonStepResult(
        success=False,
        idempotent=True,
        non_retryable=False,
        output="",
        exit_code=2,
        attempts=1,
    )


def _falha(exit_code: int, nao_repetivel: bool = False) -> hr.PythonStepResult:
    """Desfecho de falha definitiva de um passo Python."""
    return hr.PythonStepResult(
        success=False,
        idempotent=False,
        non_retryable=nao_repetivel,
        output="",
        exit_code=exit_code,
        attempts=1,
    )


class _PassosFalsos:
    """Dublê de hr.run_python_step: devolve o desfecho do passo, ou levanta se for excecao."""

    def __init__(self, respostas: dict[str, Any]) -> None:
        self.respostas = respostas
        self.chamadas: list[Any] = []

    def __call__(self, _ctx: Any, spec: Any) -> Any:
        self.chamadas.append(spec)
        resposta = self.respostas[spec.step]
        if isinstance(resposta, BaseException):
            raise resposta
        return resposta


class _WhatsAppFalso:
    """Dublê de hr.send_whatsapp: registra o lote lido do disco e grava o resultado do motor."""

    def __init__(self) -> None:
        self.codigo = 0
        self.resultados: list[dict[str, Any]] | None = [
            {"phase_key": "FASE_A", "success": True},
            {"phase_key": "FASE_B", "success": True},
        ]
        self.bruto: str | None = None
        self.excecao: BaseException | None = None
        self.chamadas: list[dict[str, Any]] = []

    def __call__(self, _ctx: Any, **kwargs: Any) -> int:
        lote = Path(kwargs["batch_input_file"])
        fases: list[str] = []
        if lote.exists():
            fases = [
                str(item["phase_key"])
                for item in json.loads(lote.read_text(encoding="utf-8-sig"))
            ]
        conteudo = lote.read_bytes().decode("utf-8") if lote.exists() else ""
        self.chamadas.append(
            {
                **kwargs,
                "lote_existia": lote.exists(),
                "fases_lote": fases,
                "conteudo_lote": conteudo,
            }
        )
        if self.excecao is not None:
            raise self.excecao
        resultado = Path(kwargs["batch_result_file"])
        if self.bruto is not None:
            resultado.write_text(self.bruto, encoding="utf-8")
        elif self.resultados is not None:
            resultado.write_text(json.dumps(self.resultados), encoding="utf-8")
        return self.codigo


class _Limpeza:
    """Dublê da limpeza de Chrome zumbi: registra a pasta da sessao e devolve a saida pedida."""

    def __init__(self) -> None:
        self.saida: list[str] = []
        self.chamadas: list[str] = []

    def __call__(self, pasta_auth: str) -> list[str]:
        self.chamadas.append(pasta_auth)
        return list(self.saida)


class _Alerta:
    """Dublê de hr.send_failure_alert: nao deve ser chamado pelo runner do OBP-04."""

    def __init__(self) -> None:
        self.chamadas: list[dict[str, Any]] = []

    def __call__(self, _ctx: Any, **kwargs: Any) -> bool:
        self.chamadas.append(kwargs)
        return True


class _MutexFalso:
    """Dublê do AutomationMutex: registra a chave pedida e a saida, e nunca bloqueia."""

    chaves: list[str] = []
    saidas: list[str] = []

    def __init__(
        self,
        chave: str,
        *,
        timeout_ms: int = 5000,
        on_warning: Callable[[str], None] | None = None,
    ) -> None:
        _ = (timeout_ms, on_warning)
        self.chave = chave
        _MutexFalso.chaves.append(chave)

    def __enter__(self) -> _MutexFalso:
        return self

    def __exit__(self, _tipo: object, _valor: object, _rastro: object) -> None:
        _MutexFalso.saidas.append(self.chave)


class _MutexBloqueado:
    """Dublê de um mutex OBP-04 ja ocupado por outra execucao."""

    def __init__(
        self,
        chave: str,
        *,
        timeout_ms: int = 5000,
        on_warning: Callable[[str], None] | None = None,
    ) -> None:
        _ = (chave, timeout_ms, on_warning)

    def __enter__(self) -> _MutexBloqueado:
        raise hr.LockTimeoutError(
            "CONCORRENCIA DETECTADA: ja existe um processo com o lock OBP-04."
        )

    def __exit__(self, _tipo: object, _valor: object, _rastro: object) -> None:
        return None


@dataclass
class _Duplos:
    """Conjunto de dubles instalado em cada teste, com as chamadas registradas."""

    passos: _PassosFalsos
    envio: _WhatsAppFalso
    limpeza: _Limpeza
    alerta: _Alerta
    extras: dict[str, Any] = field(default_factory=dict)


@pytest.fixture(autouse=True)
def _ambiente_isolado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove variaveis do ambiente real que mudariam o pre-flight, o destino ou a telemetria."""
    for chave in (
        "HUB_TRACE_ID",
        "ORACLE_CONNECT_STRING",
        "ORACLE_QUEUE_DIR",
        "ORACLE_CLIENT_PATH",
        "ORACLE_CLIENT_LIB_DIR",
        "ENVIRONMENT",
        "TNS_ADMIN",
    ):
        monkeypatch.delenv(chave, raising=False)
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "thick")
    monkeypatch.setenv("OBP_WHATSAPP_TARGET", TARGET)


@pytest.fixture(name="duplos")
def _duplos(monkeypatch: pytest.MonkeyPatch) -> _Duplos:
    """Instala os dubles: passos Python bem-sucedidos, envio com dois resultados, disco livre."""
    duplos = _Duplos(
        passos=_PassosFalsos({"extract": _ok(), "transform": _ok()}),
        envio=_WhatsAppFalso(),
        limpeza=_Limpeza(),
        alerta=_Alerta(),
    )
    monkeypatch.setattr(hr, "run_python_step", duplos.passos)
    monkeypatch.setattr(hw, "send_whatsapp", duplos.envio)
    monkeypatch.setattr(ro, "_executar_limpeza_chrome", duplos.limpeza)
    monkeypatch.setattr(hr, "send_failure_alert", duplos.alerta)
    monkeypatch.setattr(hr, "AutomationMutex", _MutexFalso)
    monkeypatch.setattr(ro, "_espaco_livre_gb", lambda _caminho: 10.0)
    _MutexFalso.chaves.clear()
    _MutexFalso.saidas.clear()
    return duplos


@pytest.fixture(name="pasta")
def _pasta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pasta de automacao falsa: scripts vazios, config do WhatsApp, cards e .tmp de estado."""
    pasta = tmp_path / "OBs Paradas Fase"
    pasta.mkdir()
    (pasta / "extract_obs.py").write_text("# script falso\n", encoding="utf-8")
    (pasta / "generate_phase_cards.py").write_text("# script falso\n", encoding="utf-8")
    config = {
        "target": {
            "type": "group",
            "contactIdEnv": "OBP_WHATSAPP_TARGET",
            "contactId": "placeholder@g.us",
        },
        "auth": {"clientId": "hub-global"},
    }
    (pasta / "whatsapp-config.json").write_text(json.dumps(config), encoding="utf-8")
    (pasta / "phase_cards.json").write_text(
        json.dumps(CARDS, ensure_ascii=False), encoding="utf-8"
    )
    (pasta / "obs_state.json.tmp").write_text(
        json.dumps({"last_hash": HASH_NOVO}), encoding="utf-8"
    )
    monkeypatch.setenv("WHATSAPP_AUTH_PATH", str(tmp_path / "wwebjs_auth"))
    return pasta


def _rodar(pasta: Path, *, dry_run: bool = False) -> tuple[int, hr.HubRunContext]:
    """Roda o fluxo com ExecId fixo, sem telemetria, e log dentro de tmp_path."""
    ctx = hr.create_run_context(
        hr.AutomationSpec(
            automacao="OBs Paradas Fase",
            slug="ObsParadasFase",
            trace_slug="obp",
            lock_key="OBP-04",
            log_dir=pasta / "Logs",
            non_failure_codes=(0, 2, 22),
        ),
        exec_id="EXEC-TESTE-0001",
        telemetry=None,
        project_root=pasta.parent,
    )
    codigo = ro.executar(ctx, ro.Caminhos.da_pasta(pasta), dry_run=dry_run)
    return codigo, ctx


def _eventos(ctx: hr.HubRunContext) -> list[dict[str, Any]]:
    """Eventos gravados no jsonl da execucao, na ordem de emissao."""
    conteudo = ctx.log_path.read_text(encoding="utf-8-sig")
    return [json.loads(linha) for linha in conteudo.splitlines() if linha.strip()]


def _passos_iniciados(eventos: list[dict[str, Any]]) -> list[str]:
    """Etapas abertas (step.start), na ordem."""
    return [e["step"] for e in eventos if e["event"] == "step.start"]


def _mensagens(ctx: hr.HubRunContext) -> list[str]:
    """Mensagens de todos os eventos da execucao."""
    return [str(e["message"]) for e in _eventos(ctx)]


def _fim(ctx: hr.HubRunContext) -> dict[str, Any]:
    """Evento execution.end, que e sempre o ultimo."""
    eventos = _eventos(ctx)
    assert eventos[-1]["event"] == "execution.end"
    return eventos[-1]


def _estado(pasta: Path) -> dict[str, Any]:
    """delivery_state.json gravado pelo commit."""
    dados: dict[str, Any] = json.loads(
        ro.Caminhos.da_pasta(pasta).entrega.read_text(encoding="utf-8")
    )
    return dados


def _gravar_estado(pasta: Path, dados: dict[str, Any]) -> None:
    """Escreve um delivery_state.json de entrega anterior."""
    (pasta / "delivery_state.json").write_text(json.dumps(dados), encoding="utf-8")


def _pasta_fila(pasta: Path, *, idade_s: float) -> Path:
    """Fila local com heartbeat de idade controlada pelo mtime (worker 2.6.1, state idle)."""
    fila = pasta / "fila"
    fila.mkdir(exist_ok=True)
    heartbeat = fila / "_worker_heartbeat.json"
    heartbeat.write_text(
        json.dumps({"state": "idle", "version": "2.6.1"}), encoding="utf-8"
    )
    instante = time.time() - idade_s
    os.utime(heartbeat, (instante, instante))
    return fila


# ---------------------------------------------------------------------------
# Desfechos de saida (um teste por codigo do run.ps1 antigo)
# ---------------------------------------------------------------------------


def test_fluxo_feliz_envia_o_lote_e_confirma_o_estado(
    pasta: Path, duplos: _Duplos
) -> None:
    codigo, ctx = _rodar(pasta)

    assert codigo == 0
    assert [s.step for s in duplos.passos.chamadas] == ["extract", "transform"]
    assert len(duplos.envio.chamadas) == 1
    envio = duplos.envio.chamadas[0]
    assert envio["mode"] == "BATCH"
    assert envio["client_id"] == "hub-global"
    assert envio["phone"] == TARGET
    assert envio["lote_existia"] is True
    assert envio["fases_lote"] == ["FASE_A", "FASE_B"]
    caminhos = ro.Caminhos.da_pasta(pasta)
    assert json.loads(caminhos.obs_state.read_text(encoding="utf-8")) == {
        "last_hash": HASH_NOVO
    }
    assert not caminhos.obs_state_tmp.exists()
    estado = _estado(pasta)
    assert estado["last_sent_hash"] == HASH_NOVO
    assert [fase["success"] for fase in estado["phases"]] == [True, True]
    assert not caminhos.batch_input.exists()
    assert not caminhos.batch_result.exists()
    eventos = _eventos(ctx)
    assert _passos_iniciados(eventos) == [
        "preflight",
        "lock",
        "extract",
        "transform",
        "dispatch",
        "commit",
    ]
    fim = _fim(ctx)
    assert fim["outcome_code"] == 0
    assert fim["level"] == "INFO"
    assert fim["record_counts"] == {
        "phases_total": 2,
        "phases_attempted": 2,
        "phases_sent": 2,
        "phases_failed": 0,
    }
    assert _MutexFalso.chaves == ["OBP-04"]
    assert _MutexFalso.saidas == ["OBP-04"]
    assert duplos.limpeza.chamadas == [hw.get_whatsapp_auth_path().lower()]


def test_extracao_idempotente_sai_com_2_sem_envio(pasta: Path, duplos: _Duplos) -> None:
    duplos.passos.respostas["extract"] = _idempotente()

    codigo, ctx = _rodar(pasta)

    assert codigo == 2
    assert [s.step for s in duplos.passos.chamadas] == ["extract"]
    assert not duplos.envio.chamadas
    fim = _fim(ctx)
    assert fim["outcome_reason"] == (
        "Idempotencia confirmada — nenhuma mudanca desde o ultimo envio."
    )
    assert fim["level"] == "INFO"


@pytest.mark.parametrize(
    ("exit_code", "nao_repetivel", "codigo_esperado"),
    [(1, False, 3), (5, True, 3), (6, True, 26), (7, True, 27)],
)
def test_falha_de_extracao_devolve_o_codigo_canonico_sem_alerta(
    pasta: Path,
    duplos: _Duplos,
    exit_code: int,
    nao_repetivel: bool,
    codigo_esperado: int,
) -> None:
    duplos.passos.respostas["extract"] = _falha(exit_code, nao_repetivel)

    codigo, ctx = _rodar(pasta)

    assert codigo == codigo_esperado
    assert [s.step for s in duplos.passos.chamadas] == ["extract"]
    assert not duplos.envio.chamadas
    assert not duplos.alerta.chamadas
    assert _fim(ctx)["outcome_reason"] == (
        f"Falha definitiva na extracao Oracle (Python (extract_obs.py)) (PythonExit={exit_code})."
    )


def test_gerador_sem_ob_qualificada_sai_com_2(pasta: Path, duplos: _Duplos) -> None:
    duplos.passos.respostas["transform"] = _idempotente()

    codigo, ctx = _rodar(pasta)

    assert codigo == 2
    assert not duplos.envio.chamadas
    assert _fim(ctx)["outcome_reason"] == "Nenhuma OB qualificada — nenhum card gerado."


def test_gerador_com_erro_sai_com_4_sem_retry(pasta: Path, duplos: _Duplos) -> None:
    duplos.passos.respostas["transform"] = _falha(1)

    codigo, ctx = _rodar(pasta)

    assert codigo == 4
    assert not duplos.envio.chamadas
    assert duplos.passos.chamadas[-1].max_attempts == 1
    assert _fim(ctx)["outcome_reason"] == (
        "Falha em generate_phase_cards.py. ExitCode=1"
    )


def test_phase_cards_ausente_sai_com_4(pasta: Path, duplos: _Duplos) -> None:
    (pasta / "phase_cards.json").unlink()

    codigo, ctx = _rodar(pasta)

    assert codigo == 4
    assert not duplos.envio.chamadas
    assert _fim(ctx)["outcome_reason"] == "phase_cards.json nao foi gerado."


def test_phase_cards_invalido_sai_com_4(pasta: Path, duplos: _Duplos) -> None:
    (pasta / "phase_cards.json").write_text("{nao e json", encoding="utf-8")

    codigo, ctx = _rodar(pasta)

    assert codigo == 4
    assert not duplos.envio.chamadas
    assert _fim(ctx)["outcome_reason"].startswith("Falha ao interpretar")


def test_phase_cards_vazio_sai_com_2_sem_envio(pasta: Path, duplos: _Duplos) -> None:
    (pasta / "phase_cards.json").write_text("[]", encoding="utf-8")

    codigo, ctx = _rodar(pasta)

    assert codigo == 2
    assert not duplos.envio.chamadas
    assert _fim(ctx)["outcome_reason"] == (
        "phase_cards.json vazio — nenhuma fase para enviar."
    )


def test_entrega_ja_realizada_sai_com_2_e_promove_o_estado(
    pasta: Path, duplos: _Duplos
) -> None:
    _gravar_estado(
        pasta,
        {
            "last_sent_hash": HASH_NOVO,
            "phases": [
                {"key": "FASE_A", "success": True, "sent_at": "01/01/2026 10:00:00"},
                {"key": "FASE_B", "success": True, "sent_at": "01/01/2026 10:00:00"},
            ],
        },
    )

    codigo, ctx = _rodar(pasta)

    assert codigo == 2
    assert not duplos.envio.chamadas
    caminhos = ro.Caminhos.da_pasta(pasta)
    assert caminhos.obs_state.exists()
    assert not caminhos.obs_state_tmp.exists()
    fim = _fim(ctx)
    assert fim["outcome_reason"] == (
        "Entrega ja realizada — nenhum novo envio necessario."
    )
    assert fim["record_counts"] == {
        "phases_total": 2,
        "phases_sent": 2,
        "phases_attempted": 0,
    }


def test_hash_novo_zera_as_entregas_e_envia_o_lote_inteiro(
    pasta: Path, duplos: _Duplos
) -> None:
    _gravar_estado(
        pasta,
        {
            "last_sent_hash": "HASH-ANTIGO",
            "phases": [
                {"key": "FASE_A", "success": True, "sent_at": "01/01/2026 10:00:00"},
                {"key": "FASE_B", "success": True, "sent_at": "01/01/2026 10:00:00"},
            ],
        },
    )

    codigo, ctx = _rodar(pasta)

    assert codigo == 0
    assert duplos.envio.chamadas[0]["fases_lote"] == ["FASE_A", "FASE_B"]
    assert (
        f"Novo hash ({HASH_NOVO}) — resetando estado de entrega por fase."
        in _mensagens(ctx)
    )


def test_fases_ja_entregues_saem_do_lote(pasta: Path, duplos: _Duplos) -> None:
    _gravar_estado(
        pasta,
        {
            "last_sent_hash": HASH_NOVO,
            "phases": [
                {"key": "FASE_A", "success": True, "sent_at": "01/01/2026 10:00:00"}
            ],
        },
    )

    codigo, ctx = _rodar(pasta)

    assert codigo == 0
    assert duplos.envio.chamadas[0]["fases_lote"] == ["FASE_B"]
    fim = _fim(ctx)
    assert fim["record_counts"] == {
        "phases_total": 2,
        "phases_attempted": 1,
        "phases_sent": 2,
        "phases_failed": 0,
    }


def test_card_sem_image_path_sai_com_4_antes_de_enviar(
    pasta: Path, duplos: _Duplos
) -> None:
    cartoes = [dict(CARDS[0], image_path=""), dict(CARDS[1])]
    (pasta / "phase_cards.json").write_text(json.dumps(cartoes), encoding="utf-8")

    codigo, ctx = _rodar(pasta)

    assert codigo == 4
    assert not duplos.envio.chamadas
    assert _fim(ctx)["outcome_reason"] == (
        "Card 'FASE_A' sem image_path — phase_cards.json corrompido."
    )


def test_whatsapp_adiado_sai_com_22_e_remove_os_arquivos_do_lote(
    pasta: Path, duplos: _Duplos
) -> None:
    duplos.envio.codigo = 22

    codigo, ctx = _rodar(pasta)

    assert codigo == 22
    caminhos = ro.Caminhos.da_pasta(pasta)
    assert not caminhos.batch_input.exists()
    assert not caminhos.batch_result.exists()
    assert not caminhos.entrega.exists()
    assert not caminhos.obs_state.exists()
    assert not caminhos.obs_state_tmp.exists()
    fim = _fim(ctx)
    assert fim["outcome_reason"] == (
        "WhatsApp adiado por lock ou cooldown da sessao hub-global."
    )
    assert fim["level"] == "INFO"


def test_whatsapp_pedindo_reautenticacao_sai_com_21(
    pasta: Path, duplos: _Duplos
) -> None:
    duplos.envio.codigo = 21

    codigo, ctx = _rodar(pasta)

    assert codigo == 21
    assert not ro.Caminhos.da_pasta(pasta).entrega.exists()
    fim = _fim(ctx)
    assert fim["outcome_reason"] == "WhatsApp requer reautenticacao."
    assert fim["level"] == "ERRO"


def test_falha_total_do_envio_sai_com_4_sem_confirmar_o_estado(
    pasta: Path, duplos: _Duplos
) -> None:
    duplos.envio.codigo = 24
    duplos.envio.resultados = None

    codigo, ctx = _rodar(pasta)

    assert codigo == 4
    caminhos = ro.Caminhos.da_pasta(pasta)
    assert not caminhos.obs_state.exists()
    assert not caminhos.obs_state_tmp.exists()
    estado = _estado(pasta)
    assert [fase["success"] for fase in estado["phases"]] == [False, False]
    fim = _fim(ctx)
    assert fim["outcome_reason"] == (
        "Uma ou mais fases falharam no envio WhatsApp. Verifique os logs."
    )
    assert fim["record_counts"]["phases_failed"] == 2


def test_envio_parcial_confirma_so_as_fases_entregues(
    pasta: Path, duplos: _Duplos
) -> None:
    duplos.envio.resultados = [{"phase_key": "FASE_A", "success": True}]

    codigo, _ctx = _rodar(pasta)

    assert codigo == 4
    caminhos = ro.Caminhos.da_pasta(pasta)
    assert not caminhos.obs_state.exists()
    estado = _estado(pasta)
    assert {fase["key"]: fase["success"] for fase in estado["phases"]} == {
        "FASE_A": True,
        "FASE_B": False,
    }


def test_batch_result_ilegivel_avisa_e_marca_as_fases_como_falha(
    pasta: Path, duplos: _Duplos
) -> None:
    duplos.envio.bruto = "{nao e json"

    codigo, ctx = _rodar(pasta)

    assert codigo == 4
    eventos = _eventos(ctx)
    avisos = [
        e["message"]
        for e in eventos
        if e["level"] == "WARN" and "batch_result.json" in e["message"]
    ]
    assert avisos
    assert _estado(pasta)["phases"][0]["success"] is False


def test_lote_sem_resultado_de_fase_nao_avanca_o_hash(
    pasta: Path, duplos: _Duplos
) -> None:
    duplos.envio.resultados = []

    codigo, _ctx = _rodar(pasta)

    assert codigo == 4
    assert not ro.Caminhos.da_pasta(pasta).obs_state.exists()


def test_preflight_sem_destino_whatsapp_sai_com_9_antes_do_lock(
    pasta: Path, duplos: _Duplos, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OBP_WHATSAPP_TARGET")

    codigo, ctx = _rodar(pasta)

    assert codigo == 9
    assert not duplos.passos.chamadas
    assert not _MutexFalso.chaves
    assert any(
        "Pre-Flight WhatsApp falhou: Destino do WhatsApp ausente" in m
        for m in _mensagens(ctx)
    )


def test_preflight_queue_com_worker_offline_devolve_26_so_se_o_resto_passa(
    pasta: Path, duplos: _Duplos, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "queue")
    monkeypatch.setenv("ORACLE_QUEUE_DIR", str(_pasta_fila(pasta, idade_s=600)))

    codigo, ctx = _rodar(pasta)

    assert codigo == 26
    assert not duplos.passos.chamadas
    assert not _MutexFalso.chaves
    assert any("Worker Offline" in m for m in _mensagens(ctx))


def test_preflight_queue_offline_com_arquivo_faltando_devolve_9(
    pasta: Path, duplos: _Duplos, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "queue")
    monkeypatch.setenv("ORACLE_QUEUE_DIR", str(_pasta_fila(pasta, idade_s=600)))
    (pasta / "extract_obs.py").unlink()

    codigo, _ctx = _rodar(pasta)

    assert codigo == 9
    assert not duplos.passos.chamadas


def test_preflight_com_disco_critico_sai_com_9(
    pasta: Path, duplos: _Duplos, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ro, "_espaco_livre_gb", lambda _caminho: 0.4)

    codigo, ctx = _rodar(pasta)

    assert codigo == 9
    assert not duplos.passos.chamadas
    assert any("ERRO: Disco critico (0.4 GB)" in m for m in _mensagens(ctx))


def test_excecao_no_lote_sai_com_4_libera_o_lock_e_limpa_o_tmp(
    pasta: Path, duplos: _Duplos
) -> None:
    duplos.envio.excecao = RuntimeError("falha inesperada no envio")

    codigo, ctx = _rodar(pasta)

    assert codigo == 4
    assert _MutexFalso.saidas == ["OBP-04"]
    assert not ro.Caminhos.da_pasta(pasta).obs_state_tmp.exists()
    fim = _fim(ctx)
    assert fim["outcome_reason"] == (
        "Falha critica na orquestracao: falha inesperada no envio"
    )
    assert fim["level"] == "ERRO"


def test_excecao_no_preflight_sai_com_1_sem_pegar_o_lock(
    pasta: Path, duplos: _Duplos, monkeypatch: pytest.MonkeyPatch
) -> None:
    def quebra() -> hr.OraclePreflight:
        raise RuntimeError("falha inesperada no pre-flight")

    monkeypatch.setattr(ro, "_resultado_oracle", quebra)

    codigo, ctx = _rodar(pasta)

    assert codigo == 1
    assert not duplos.passos.chamadas
    assert not _MutexFalso.chaves
    assert _fim(ctx)["outcome_reason"] == ("ERRO FATAL: falha inesperada no pre-flight")


def test_lock_ocupado_sai_com_4_sem_executar_etapas(
    pasta: Path, duplos: _Duplos, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hr, "AutomationMutex", _MutexBloqueado)

    codigo, ctx = _rodar(pasta)

    assert codigo == 4
    assert not duplos.passos.chamadas
    assert _fim(ctx)["outcome_reason"].startswith(
        "Falha critica na orquestracao: CONCORRENCIA DETECTADA"
    )


# ---------------------------------------------------------------------------
# Dry-run: pre-flight, extract e transform reais; sem envio, sem lote, sem commit
# ---------------------------------------------------------------------------


def test_dry_run_nao_envia_nem_grava_o_lote_nem_o_estado(
    pasta: Path, duplos: _Duplos
) -> None:
    codigo, ctx = _rodar(pasta, dry_run=True)

    assert codigo == 0
    assert [s.step for s in duplos.passos.chamadas] == ["extract", "transform"]
    assert not duplos.envio.chamadas
    caminhos = ro.Caminhos.da_pasta(pasta)
    assert not caminhos.batch_input.exists()
    assert not caminhos.entrega.exists()
    assert not caminhos.obs_state.exists()
    assert not duplos.limpeza.chamadas
    mensagens = _mensagens(ctx)
    assert any(
        m.startswith("[DRY-RUN] Envio WhatsApp nao executado") for m in mensagens
    )
    assert any("Commit de estado nao executado" in m for m in mensagens)
    assert not any(TARGET in m for m in mensagens)
    assert any("@g.us" in m for m in mensagens)
    assert not duplos.alerta.chamadas


def test_dry_run_com_extracao_idempotente_sai_com_2(
    pasta: Path, duplos: _Duplos
) -> None:
    duplos.passos.respostas["extract"] = _idempotente()

    codigo, _ctx = _rodar(pasta, dry_run=True)

    assert codigo == 2
    assert not duplos.envio.chamadas


# ---------------------------------------------------------------------------
# Limpeza de Chrome zumbi, helpers e contrato dos arquivos
# ---------------------------------------------------------------------------


def test_limpeza_de_chrome_zumbi_loga_os_encerrados_e_as_falhas(
    pasta: Path, duplos: _Duplos
) -> None:
    duplos.limpeza.saida = ["TOTAL 2", "OK 10", "FALHA 11 acesso negado"]

    codigo, ctx = _rodar(pasta)

    assert codigo == 0
    mensagens = _mensagens(ctx)
    assert "Limpando 2 processo(s) Chrome zumbi do motor WhatsApp..." in mensagens
    assert "Aviso: nao foi possivel encerrar Chrome PID=11: acesso negado" in mensagens


def test_interpretar_limpeza_separa_total_e_falhas() -> None:
    total, falhas = ro._interpretar_limpeza(  # pylint: disable=protected-access
        ["TOTAL 2", "OK 10", "FALHA 11 acesso negado", "lixo"]
    )

    assert total == 2
    assert falhas == [("11", "acesso negado")]


@pytest.mark.parametrize(
    ("destino", "esperado"),
    [
        ("120363000000000000@g.us", "**************0000@g.us"),
        ("1234@g.us", "1234@g.us"),
        ("12", "12"),
    ],
)
def test_mascarar_destino_mantem_so_os_ultimos_digitos(
    destino: str, esperado: str
) -> None:
    assert ro._mascarar_destino(destino) == esperado  # pylint: disable=protected-access


def test_resolver_destino_prefere_a_variavel_e_reprova_destino_vazio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    origem = tmp_path / "whatsapp-config.json"
    resolver = ro._resolver_destino  # pylint: disable=protected-access

    assert (
        resolver({"contactIdEnv": "OBP_WHATSAPP_TARGET", "contactId": "x@g.us"}, origem)
        == TARGET
    )
    assert resolver({"contactId": "5511@g.us"}, origem) == "5511@g.us"
    monkeypatch.setenv("OBP_WHATSAPP_TARGET", "   ")
    with pytest.raises(ValueError, match="variavel de ambiente 'OBP_WHATSAPP_TARGET'"):
        resolver({"contactIdEnv": "OBP_WHATSAPP_TARGET"}, origem)
    with pytest.raises(ValueError, match="nao declara contactId"):
        resolver({}, origem)


@pytest.mark.parametrize(
    ("linha", "esperado"),
    [
        ("OBP_WHATSAPP_TARGET=120@g.us   # grupo", ("OBP_WHATSAPP_TARGET", "120@g.us")),
        ("  CHAVE = valor  ", ("CHAVE", "valor")),
        ("# so comentario", None),
        ("VAZIA=", None),
    ],
)
def test_ler_linha_env_segue_convert_from_env_line(
    linha: str, esperado: tuple[str, str] | None
) -> None:
    assert ro._ler_linha_env(linha) == esperado  # pylint: disable=protected-access


def test_rotacao_remove_eventos_anteriores_a_retencao(tmp_path: Path) -> None:
    caminho = tmp_path / "ObsParadasFase.jsonl"
    antigo = (date.today() - timedelta(days=30)).isoformat()
    hoje = date.today().isoformat()
    caminho.write_text(
        f'{{"ts":"{antigo}T10:00:00Z","message":"antigo"}}\r\n'
        f'{{"ts":"{hoje}T10:00:00Z","message":"recente"}}\r\n',
        encoding="utf-8",
    )

    ro._rotacionar_log(caminho)  # pylint: disable=protected-access

    mantidas = caminho.read_text(encoding="utf-8-sig").splitlines()
    assert len(mantidas) == 1
    assert "recente" in mantidas[0]


def test_caminhos_usam_os_nomes_de_arquivo_do_run_ps1(tmp_path: Path) -> None:
    caminhos = ro.Caminhos.da_pasta(tmp_path)

    assert caminhos.obs_state.name == "obs_state.json"
    assert caminhos.obs_state_tmp.name == "obs_state.json.tmp"
    assert caminhos.entrega.name == "delivery_state.json"
    assert caminhos.resultado.name == "obs_result.json"
    assert caminhos.phase_cards.name == "phase_cards.json"
    assert caminhos.batch_input.name == "batch_input.json"
    assert caminhos.batch_result.name == "batch_result.json"
    assert caminhos.wa_config.name == "whatsapp-config.json"


def test_codigos_de_nao_falha_sao_zero_dois_e_22() -> None:
    assert ro.NAO_FALHA == (0, 2, 22)


def test_lote_gravado_segue_o_layout_do_convert_to_json_do_powershell(
    pasta: Path, duplos: _Duplos
) -> None:
    _rodar(pasta)

    conteudo = duplos.envio.chamadas[0]["conteudo_lote"]
    assert conteudo.startswith('[\r\n    {\r\n        "caption":  "Legenda A",')
    assert conteudo.endswith('"phase_key":  "FASE_B"\r\n    }\r\n]')
    # Caminho absoluto da imagem, com as barras escapadas como o ConvertTo-Json do PS.
    assert r"images\\FASE_A.png" in conteudo
    assert not (pasta / "batch_input.json").exists()


# ---------------------------------------------------------------------------
# Contrato do shim e do runner (leitura de texto, sem executar PowerShell)
# ---------------------------------------------------------------------------


def _shim() -> str:
    """Conteudo do run.ps1 (com BOM), lido como texto."""
    return (PASTA_OBP / "run.ps1").read_text(encoding="utf-8-sig")


def test_shim_delega_ao_runner_e_repassa_o_exit_code() -> None:
    fonte = _shim()

    assert "Resolve-HubPythonExe" in fonte
    assert '"run_obs_paradas.py"' in fonte
    assert "exit $LASTEXITCODE" in fonte
    assert "--dry-run" in fonte
    assert "Enter-AutomationLock" not in fonte
    assert "Register-ExecutionTelemetry" not in fonte
    assert "Invoke-OraclePythonScript" not in fonte


def test_shim_valida_o_python_antes_de_delegar_e_tem_no_maximo_40_linhas() -> None:
    fonte = _shim()
    sem_ajuda = fonte.split("#>", 1)[1]
    linhas_codigo = [
        linha
        for linha in sem_ajuda.splitlines()
        if linha.strip() and not linha.strip().startswith("#")
    ]

    assert "Test-Path -LiteralPath $pythonExe" in fonte
    assert "exit 9" in fonte
    assert len(linhas_codigo) <= 40


def test_runner_fecha_a_execucao_em_um_unico_ponto() -> None:
    fonte = (PASTA_OBP / "run_obs_paradas.py").read_text(encoding="utf-8")

    assert fonte.count("hr.finish(") == 1
    assert "return hr.finish(" in fonte
    assert "sys.exit(main())" in fonte


def test_runner_nao_envia_alerta_de_falha_como_o_run_ps1_antigo() -> None:
    fonte = (PASTA_OBP / "run_obs_paradas.py").read_text(encoding="utf-8")

    assert "send_failure_alert" not in fonte
    assert "send_outlook_email" not in fonte
    assert 'CHAVE_LOCK: Final[str] = "OBP-04"' in fonte


def test_runner_nao_usa_dependencias_novas_nem_caminho_absoluto() -> None:
    fonte = (PASTA_OBP / "run_obs_paradas.py").read_text(encoding="utf-8")

    assert "C:\\" not in fonte
    assert "import requests" not in fonte
    assert "import psutil" not in fonte


def test_datetime_do_carimbo_segue_o_formato_do_powershell() -> None:
    carimbo = ro._agora()  # pylint: disable=protected-access

    assert datetime.strptime(carimbo, "%d/%m/%Y %H:%M:%S")


def test_limpeza_de_chrome_protege_a_arvore_do_daemon_whatsapp() -> None:
    """O daemon WhatsApp usa o mesmo perfil: a limpeza nao pode matar o Chrome dele.

    Checagem textual do script (executa-lo encerraria processos reais).
    """
    script = ro._SCRIPT_LIMPEZA_CHROME  # pylint: disable=protected-access

    assert "whatsapp-daemon.js" in script
    assert "-not $protegidos.Contains([int]$_.ProcessId)" in script
    assert "ParentProcessId" in script


@pytest.mark.skipif(os.name != "nt", reason="parser do PowerShell 5.1 so no Windows")
def test_script_de_limpeza_de_chrome_parseia_no_powershell_51() -> None:
    """O script embutido tem sintaxe valida no powershell.exe (so parse, sem executar)."""
    import subprocess  # pylint: disable=import-outside-toplevel

    script = ro._SCRIPT_LIMPEZA_CHROME  # pylint: disable=protected-access
    verificador = (
        "$e = $null; [void][System.Management.Automation.Language.Parser]::ParseInput("
        "$env:HUB_SCRIPT, [ref]$null, [ref]$e); $e.Count"
    )
    resultado = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", verificador],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "HUB_SCRIPT": script},
        timeout=60,
    )
    assert resultado.stdout.strip() == "0", resultado.stdout + resultado.stderr
