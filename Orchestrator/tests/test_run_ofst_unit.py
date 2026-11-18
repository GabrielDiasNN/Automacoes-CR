"""Testes unitarios do runner de OBs Fluxo Sem Tingimento (OBs Fluxo Sem Tingimento/run_ofst.py).

Sem Oracle, sem WhatsApp e sem rede. O passo de extracao (hr.run_python_step), o formatador
(rr._executar_formatador), o envio (hw.send_whatsapp) e o mutex OFST-06 (hr.AutomationMutex,
que so existe no Windows) sao substituidos por dubles. Os arquivos da automacao vivem em
tmp_path: nunca na pasta OBs Fluxo Sem Tingimento nem em Logs/ do repo. Manifesto de cards,
batch_input, reconciliacao do lote e record_counts sao os reais de hub_whatsapp, lidos de
arquivos temporarios.

Cada desfecho do run.ps1 anterior tem pelo menos um teste (codigos 0, 1, 2, 3, 4, 9, 21,
22, 26 e 27); o dry-run tem os seus. Os nomes dos testes dizem o desfecho.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import hub_runner as hr
import hub_whatsapp as hw
import pytest
from tests.carregadores_modulos import carregar_modulo_automacao

# Os dublês de teste sao deliberadamente minimos (um metodo cada).
# pylint: disable=too-few-public-methods,protected-access

RAIZ_REPO = Path(__file__).resolve().parents[2]
rr: Any = carregar_modulo_automacao(
    "run_ofst", RAIZ_REPO / "OBs Fluxo Sem Tingimento" / "run_ofst.py"
)

DESTINO_ENV = "OFST_WHATSAPP_TARGET"
DESTINO = "TESTE-DESTINO-0001@g.us"
EXEC_ID = "EXEC-TESTE-OFST-0001"
PNG = b"\x89PNG-teste"
ESTADO_TMP: dict[str, Any] = {
    "notified": {"OB-1": "17/11/2026 10:00:00", "OB-2": "17/11/2026 10:00:00"}
}
ESTADO_VIVO: dict[str, Any] = {"notified": {"OB-0": "16/11/2026 08:00:00"}}
RESULTADO_EXTRACAO: dict[str, Any] = {"record_counts": {"sent": 2, "notified": 2}}
EXTRACAO_OK = hr.PythonStepResult(
    success=True,
    idempotent=False,
    non_retryable=False,
    output="",
    exit_code=0,
    attempts=1,
)
CardSpec = tuple[str, str, str, tuple[str, ...]]
CARD_UNICO: tuple[CardSpec, ...] = (
    ("PHASE-1", "card.png", "Legenda da pagina 1", ("OB-1", "OB-2")),
)
CARDS_LOTE: tuple[CardSpec, ...] = (
    ("PHASE-1", "card_01.png", "Legenda da pagina 1", ("OB-1",)),
    ("PHASE-2", "card_02.png", "Legenda da pagina 2", ("OB-2",)),
)
LOTE_TUDO_ENVIADO: list[dict[str, Any]] = [
    {"phase_key": "PHASE-1", "success": True},
    {"phase_key": "PHASE-2", "success": True},
]
LOTE_UMA_FALHOU: list[dict[str, Any]] = [
    {"phase_key": "PHASE-1", "success": True},
    {"phase_key": "PHASE-2", "success": False},
]
LOTE_NENHUM_ENVIADO: list[dict[str, Any]] = [
    {"phase_key": "PHASE-1", "success": False},
    {"phase_key": "PHASE-2", "success": False},
]


class _ExtractFalso:
    """Dublê de hr.run_python_step para o extract_ofst.py.

    Devolve o desfecho da etapa ou levanta a excecao. Como o script real, grava o .tmp do
    state (quando ``grava_tmp``) e, no sucesso, o ofst_result.json com record_counts.
    """

    def __init__(
        self, resposta: hr.PythonStepResult | BaseException, grava_tmp: bool
    ) -> None:
        self.resposta = resposta
        self.grava_tmp = grava_tmp
        self.chamadas: list[hr.PythonStepSpec] = []

    def __call__(
        self, _ctx: Any, spec: hr.PythonStepSpec, **_kwargs: object
    ) -> hr.PythonStepResult:
        self.chamadas.append(spec)
        if isinstance(self.resposta, BaseException):
            raise self.resposta
        pasta = Path(spec.script_path).parent
        if self.grava_tmp:
            (pasta / "ofst_state.json.tmp").write_text(
                json.dumps(ESTADO_TMP), encoding="utf-8"
            )
        if self.resposta.success:
            (pasta / "ofst_result.json").write_text(
                json.dumps(RESULTADO_EXTRACAO), encoding="utf-8"
            )
        return self.resposta


class _FormatadorFalso:
    """Dublê de rr._executar_formatador: devolve o exit code e, como format_message.py,
    grava message.txt, os cards PNG e o cards_manifest.json (so com exit 0 e cards)."""

    def __init__(self, codigo: int, cards: tuple[CardSpec, ...] | None) -> None:
        self.codigo = codigo
        self.cards = cards
        self.chamadas = 0

    def __call__(self, _ctx: Any, caminhos: Any) -> int:
        self.chamadas += 1
        if self.codigo == 0 and self.cards is not None:
            caminhos.mensagem.write_bytes(b"mensagem do card")
            manifesto: list[dict[str, Any]] = []
            for fase, imagem, legenda, obs in self.cards:
                (caminhos.pasta / imagem).write_bytes(PNG)
                manifesto.append(
                    {
                        "phase_key": fase,
                        "image_path": imagem,
                        "caption": legenda,
                        "ob_ids": list(obs),
                    }
                )
            caminhos.manifesto.write_text(
                json.dumps(manifesto, ensure_ascii=False), encoding="utf-8"
            )
        return self.codigo


class _WhatsAppFalso:
    """Dublê de hw.send_whatsapp: consome os exit codes em ordem e registra cada envio.

    No lote grava o batch_result.json, como o Send-WhatsApp.ps1 faria.
    """

    def __init__(
        self, codigos: Sequence[int], lote: list[dict[str, Any]] | None
    ) -> None:
        self.codigos = list(codigos)
        self.lote = lote
        self.chamadas: list[dict[str, Any]] = []

    def __call__(self, _ctx: Any, **kwargs: Any) -> int:
        self.chamadas.append(dict(kwargs))
        resultado = kwargs.get("batch_result_file")
        if resultado is not None and self.lote is not None:
            Path(resultado).write_text(json.dumps(self.lote), encoding="utf-8")
        return self.codigos.pop(0)


class _MutexFalso:
    """Dublê do AutomationMutex: registra a chave pedida e a saida, e nunca bloqueia."""

    chaves: list[str] = []
    saidas: list[str] = []

    def __init__(
        self,
        chave: str,
        *,
        timeout_ms: int = 5000,
        on_warning: Any = None,
    ) -> None:
        _ = (timeout_ms, on_warning)
        self.chave = chave
        _MutexFalso.chaves.append(chave)

    def __enter__(self) -> _MutexFalso:
        return self

    def __exit__(self, _tipo: object, _valor: object, _rastro: object) -> None:
        _MutexFalso.saidas.append(self.chave)


class _MutexBloqueado:
    """Dublê de um mutex OFST-06 ja ocupado por outra execucao."""

    def __init__(
        self,
        chave: str,
        *,
        timeout_ms: int = 5000,
        on_warning: Any = None,
    ) -> None:
        _ = (chave, timeout_ms, on_warning)

    def __enter__(self) -> _MutexBloqueado:
        raise hr.LockTimeoutError(
            "CONCORRENCIA DETECTADA: ja existe um processo com o lock OFST-06."
        )

    def __exit__(self, _tipo: object, _valor: object, _rastro: object) -> None:
        return None


@dataclass
class _Cenario:
    """O que cada dublê devolve numa execucao de teste."""

    extract: hr.PythonStepResult | BaseException = EXTRACAO_OK
    grava_tmp: bool = True
    formato: int = 0
    cards: tuple[CardSpec, ...] | None = CARD_UNICO
    envios: tuple[int, ...] = (0,)
    lote: list[dict[str, Any]] | None = None


@dataclass
class _Duplos:
    """Dublês instalados numa execucao, para as asserções sobre o que foi chamado."""

    extract: _ExtractFalso
    formatador: _FormatadorFalso
    envio: _WhatsAppFalso


@dataclass
class _Execucao:
    """Resultado de uma execucao de teste: exit code, log, caminhos e dublês."""

    codigo: int
    ctx: hr.HubRunContext
    caminhos: Any
    duplos: _Duplos


@pytest.fixture(autouse=True)
def _ambiente_isolado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove variaveis do ambiente real que mudariam o pre-flight ou a telemetria."""
    for chave in (
        "HUB_TRACE_ID",
        "ORACLE_CONNECT_STRING",
        "ORACLE_DRIVER_MODE",
        "ORACLE_QUEUE_DIR",
        "ORACLE_CLIENT_PATH",
        "ENVIRONMENT",
        "WHATSAPP_AUTH_PATH",
    ):
        monkeypatch.delenv(chave, raising=False)
    monkeypatch.setenv(DESTINO_ENV, DESTINO)


def _config_whatsapp(*, destino_habilitado: bool = True) -> dict[str, Any]:
    """whatsapp-config.json de teste: destino vem de OFST_WHATSAPP_TARGET, como o real."""
    return {
        "app": {"enabled": True},
        "auth": {"clientId": "hub-global"},
        "target": {
            "enabled": destino_habilitado,
            "type": "group",
            "contactIdEnv": DESTINO_ENV,
            "contactId": "550000000000-0000000000@g.us",
        },
        "message": {"textFile": "message.txt", "sendAttachment": True},
        "paths": {"attachmentPath": "card.png"},
    }


@pytest.fixture(name="pasta")
def _pasta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pasta de automacao falsa: scripts vazios, config do WhatsApp e disco com folga."""
    monkeypatch.setattr(rr, "_espaco_livre_gb", lambda _caminho: 10.0)
    (tmp_path / "extract_ofst.py").write_text("# script falso\n", encoding="utf-8")
    (tmp_path / "format_message.py").write_text("# script falso\n", encoding="utf-8")
    (tmp_path / "whatsapp-config.json").write_text(
        json.dumps(_config_whatsapp()), encoding="utf-8"
    )
    return tmp_path


def _instalar(monkeypatch: pytest.MonkeyPatch, cenario: _Cenario) -> _Duplos:
    """Substitui extract, formatador, envio e mutex pelos dublês do cenario."""
    duplos = _Duplos(
        extract=_ExtractFalso(cenario.extract, cenario.grava_tmp),
        formatador=_FormatadorFalso(cenario.formato, cenario.cards),
        envio=_WhatsAppFalso(cenario.envios, cenario.lote),
    )
    monkeypatch.setattr(hr, "run_python_step", duplos.extract)
    monkeypatch.setattr(rr, "_executar_formatador", duplos.formatador)
    monkeypatch.setattr(hw, "send_whatsapp", duplos.envio)
    monkeypatch.setattr(hr, "AutomationMutex", _MutexFalso)
    _MutexFalso.chaves.clear()
    _MutexFalso.saidas.clear()
    return duplos


def _contexto(pasta: Path) -> hr.HubRunContext:
    """Contexto de log da execucao de teste: ExecId fixo, sem telemetria, log em tmp."""
    return hr.create_run_context(
        hr.AutomationSpec(
            automacao="OBs Fluxo Sem Tingimento",
            slug="Ofst",
            trace_slug="ofst",
            lock_key="OFST-06",
            log_dir=pasta / "Logs",
            non_failure_codes=(0, 2, 22),
        ),
        exec_id=EXEC_ID,
        telemetry=None,
        project_root=pasta,
    )


def _executar_cenario(
    monkeypatch: pytest.MonkeyPatch,
    pasta: Path,
    cenario: _Cenario,
    *,
    dry_run: bool = False,
) -> _Execucao:
    """Instala os dublês do cenario e roda o fluxo completo."""
    duplos = _instalar(monkeypatch, cenario)
    ctx = _contexto(pasta)
    caminhos = rr.Caminhos.da_pasta(pasta, pasta)
    codigo = rr.executar(ctx, caminhos, dry_run=dry_run)
    return _Execucao(codigo=codigo, ctx=ctx, caminhos=caminhos, duplos=duplos)


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


def _fila_com_heartbeat(pasta: Path, *, idade_s: float) -> Path:
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


def _desabilitar_destino(pasta: Path) -> None:
    """Regrava o whatsapp-config.json com o destino desabilitado (target.enabled = false)."""
    (pasta / "whatsapp-config.json").write_text(
        json.dumps(_config_whatsapp(destino_habilitado=False)), encoding="utf-8"
    )


def _estado_vivo(pasta: Path) -> None:
    """Grava o ofst_state.json definitivo, como ficaria depois de uma execucao anterior."""
    (pasta / "ofst_state.json").write_text(json.dumps(ESTADO_VIVO), encoding="utf-8")


def _ler_json(caminho: Path) -> Any:
    """JSON de um arquivo da automacao."""
    return json.loads(caminho.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Pre-flight: codigos 26, 9 e 1 antes do lock
# ---------------------------------------------------------------------------


def test_worker_offline_no_modo_queue_com_resto_ok_devolve_26_sem_lock(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 26: modo queue, worker parado e demais checks ok (Get-OraclePreFlightExitCode)."""
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "queue")
    monkeypatch.setenv("ORACLE_QUEUE_DIR", str(_fila_com_heartbeat(pasta, idade_s=600)))

    execucao = _executar_cenario(monkeypatch, pasta, _Cenario())

    assert execucao.codigo == 26
    assert not execucao.duplos.extract.chamadas
    assert not _MutexFalso.chaves
    assert any("Worker Offline" in m for m in _mensagens(execucao.ctx))


def test_worker_offline_com_destino_whatsapp_ausente_devolve_9(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 9: outro check reprovado somado ao worker parado nao vira 26."""
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "queue")
    monkeypatch.setenv("ORACLE_QUEUE_DIR", str(_fila_com_heartbeat(pasta, idade_s=600)))
    monkeypatch.delenv(DESTINO_ENV)

    execucao = _executar_cenario(monkeypatch, pasta, _Cenario())

    assert execucao.codigo == 9
    assert not execucao.duplos.extract.chamadas
    assert not _MutexFalso.chaves
    assert any("Pre-Flight WhatsApp falhou" in m for m in _mensagens(execucao.ctx))


@pytest.mark.parametrize(
    ("modo", "sem_script", "sem_destino"),
    [
        ("auto", True, False),
        ("auto", False, True),
        ("queue", True, False),
    ],
)
def test_preflight_reprovado_sem_worker_parado_devolve_9_antes_do_lock(
    pasta: Path,
    monkeypatch: pytest.MonkeyPatch,
    modo: str,
    sem_script: bool,
    sem_destino: bool,
) -> None:
    """Desfecho 9: paths ausentes ou destino do WhatsApp ausente, fora do caso do worker parado."""
    monkeypatch.setenv("ORACLE_DRIVER_MODE", modo)
    if modo == "queue":
        monkeypatch.setenv(
            "ORACLE_QUEUE_DIR", str(_fila_com_heartbeat(pasta, idade_s=5))
        )
    if sem_script:
        (pasta / "extract_ofst.py").unlink()
    if sem_destino:
        monkeypatch.delenv(DESTINO_ENV)

    execucao = _executar_cenario(monkeypatch, pasta, _Cenario())

    assert execucao.codigo == 9
    assert not execucao.duplos.extract.chamadas
    assert not _MutexFalso.chaves
    assert _passos_iniciados(_eventos(execucao.ctx))[-1] == "preflight"


def test_excecao_inesperada_no_preflight_devolve_1_sem_pegar_o_lock(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 1: erro fora do try do run.ps1 sai com 1 (processo), com execution.end."""

    def quebra() -> hr.OraclePreflight:
        raise RuntimeError("falha inesperada no pre-flight")

    monkeypatch.setattr(rr, "_resultado_oracle", quebra)

    execucao = _executar_cenario(monkeypatch, pasta, _Cenario())

    assert execucao.codigo == 1
    assert not execucao.duplos.extract.chamadas
    assert not _MutexFalso.chaves
    fim = _eventos(execucao.ctx)[-1]
    assert fim["event"] == "execution.end"
    assert fim["outcome_reason"] == "ERRO FATAL: falha inesperada no pre-flight"


# ---------------------------------------------------------------------------
# Fluxo protegido pelo lock: cada desfecho do run.ps1 antigo
# ---------------------------------------------------------------------------


def test_envio_unico_com_sucesso_commita_o_state_e_sai_com_0(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 0 com 1 card: Send-WhatsApp em modo AUTO, state promovido, etapas em ordem."""
    execucao = _executar_cenario(monkeypatch, pasta, _Cenario())

    assert execucao.codigo == 0
    assert _MutexFalso.chaves == ["OFST-06"]
    assert _MutexFalso.saidas == ["OFST-06"]
    chamada = execucao.duplos.envio.chamadas
    assert len(chamada) == 1
    assert chamada[0]["mode"] == "AUTO"
    assert chamada[0]["batch_input_file"] is None
    assert chamada[0]["config_path"] == execucao.caminhos.config_wa
    assert chamada[0]["work_dir"] == pasta
    assert not execucao.caminhos.estado_tmp.exists()
    assert _ler_json(execucao.caminhos.estado) == ESTADO_TMP
    eventos = _eventos(execucao.ctx)
    assert _passos_iniciados(eventos) == [
        "preflight",
        "lock",
        "extract",
        "transform",
        "dispatch",
        "commit",
    ]
    assert eventos[-1]["outcome_code"] == 0
    assert eventos[-1]["outcome_reason"] == (
        "Execucao concluida com sucesso (1 card(s))."
    )


def test_envio_em_lote_com_sucesso_usa_modo_batch_e_commita(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 0 com varios cards: batch_input.json, modo BATCH e state commitado inteiro."""
    cenario = _Cenario(cards=CARDS_LOTE, envios=(0,), lote=LOTE_TUDO_ENVIADO)

    execucao = _executar_cenario(monkeypatch, pasta, cenario)

    assert execucao.codigo == 0
    chamada = execucao.duplos.envio.chamadas[0]
    assert chamada["mode"] == "BATCH"
    assert chamada["batch_input_file"] == execucao.caminhos.batch_input
    assert chamada["batch_result_file"] == execucao.caminhos.batch_result
    assert execucao.caminhos.batch_input.exists()
    assert _ler_json(execucao.caminhos.estado) == ESTADO_TMP
    assert not execucao.caminhos.estado_tmp.exists()


def test_extracao_idempotente_reconcilia_o_tmp_e_sai_com_2_sem_envio(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 2 pelo extract (exit 2): o .tmp e promovido, nada e enviado."""
    idempotente = hr.PythonStepResult(
        success=False,
        idempotent=True,
        non_retryable=False,
        output="",
        exit_code=2,
        attempts=1,
    )

    execucao = _executar_cenario(
        monkeypatch, pasta, _Cenario(extract=idempotente, grava_tmp=True)
    )

    assert execucao.codigo == 2
    assert not execucao.duplos.envio.chamadas
    assert execucao.duplos.formatador.chamadas == 0
    assert _ler_json(execucao.caminhos.estado) == ESTADO_TMP
    assert not execucao.caminhos.estado_tmp.exists()
    assert _eventos(execucao.ctx)[-1]["outcome_reason"] == (
        "Nenhuma OB nova com estoque suficiente — nada a notificar."
    )


def test_extracao_idempotente_sem_tmp_sai_com_2_e_nao_commita(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 2 sem .tmp: nada a reconciliar, o state vivo fica intocado."""
    _estado_vivo(pasta)
    idempotente = hr.PythonStepResult(
        success=False,
        idempotent=True,
        non_retryable=False,
        output="",
        exit_code=2,
        attempts=1,
    )

    execucao = _executar_cenario(
        monkeypatch, pasta, _Cenario(extract=idempotente, grava_tmp=False)
    )

    assert execucao.codigo == 2
    assert not execucao.duplos.envio.chamadas
    assert _ler_json(execucao.caminhos.estado) == ESTADO_VIVO


@pytest.mark.parametrize(
    ("exit_code", "nao_repetivel", "codigo_esperado"),
    [
        (1, False, 3),
        (5, True, 3),
        (6, True, 26),
        (7, True, 27),
    ],
)
def test_falha_definitiva_na_extracao_usa_o_codigo_canonico_e_limpa_o_tmp(
    pasta: Path,
    monkeypatch: pytest.MonkeyPatch,
    exit_code: int,
    nao_repetivel: bool,
    codigo_esperado: int,
) -> None:
    """Desfecho 3, 26 ou 27 pelo extract (Resolve-OracleFailureExitCode); o .tmp sai pelo finally."""
    falha = hr.PythonStepResult(
        success=False,
        idempotent=False,
        non_retryable=nao_repetivel,
        output="",
        exit_code=exit_code,
        attempts=1,
    )

    execucao = _executar_cenario(
        monkeypatch, pasta, _Cenario(extract=falha, grava_tmp=True)
    )

    assert execucao.codigo == codigo_esperado
    assert execucao.duplos.formatador.chamadas == 0
    assert not execucao.duplos.envio.chamadas
    assert not execucao.caminhos.estado.exists()
    assert not execucao.caminhos.estado_tmp.exists()
    assert _eventos(execucao.ctx)[-1]["outcome_reason"] == (
        f"Falha definitiva na extracao Oracle (PythonExit={exit_code})."
    )


def test_formatador_sem_ob_qualificada_sai_com_2_sem_mensagem(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 2 pelo format_message.py (exit 2): nenhuma OB, nenhum envio, sem commit."""
    cenario = _Cenario(formato=2, cards=None)

    execucao = _executar_cenario(monkeypatch, pasta, cenario)

    assert execucao.codigo == 2
    assert not execucao.duplos.envio.chamadas
    assert not execucao.caminhos.estado.exists()
    assert not execucao.caminhos.estado_tmp.exists()
    assert _eventos(execucao.ctx)[-1]["outcome_reason"] == (
        "Nenhuma OB qualificada — mensagem nao gerada."
    )


def test_formatador_com_erro_sai_com_4(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 4 pelo format_message.py (exit diferente de 0 e de 2)."""
    cenario = _Cenario(formato=1, cards=None)

    execucao = _executar_cenario(monkeypatch, pasta, cenario)

    assert execucao.codigo == 4
    assert not execucao.duplos.envio.chamadas
    assert _eventos(execucao.ctx)[-1]["outcome_reason"] == (
        "Falha em format_message.py. ExitCode=1"
    )


def test_manifesto_de_cards_invalido_sai_com_4_sem_envio(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 4 quando o cards_manifest.json e rejeitado (ob_ids vazio)."""
    cenario = _Cenario(cards=(("PHASE-1", "card.png", "Legenda", ()),))

    execucao = _executar_cenario(monkeypatch, pasta, cenario)

    assert execucao.codigo == 4
    assert not execucao.duplos.envio.chamadas
    assert not execucao.caminhos.estado.exists()
    assert "ob_ids vazio" in str(_eventos(execucao.ctx)[-1]["outcome_reason"])


def test_whatsapp_desabilitado_na_configuracao_sai_com_2_sem_envio(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 2 no dispatch: target.enabled false, nada enviado e state nao commitado."""
    _desabilitar_destino(pasta)

    execucao = _executar_cenario(monkeypatch, pasta, _Cenario())

    assert execucao.codigo == 2
    assert not execucao.duplos.envio.chamadas
    assert not execucao.caminhos.estado.exists()
    assert not execucao.caminhos.estado_tmp.exists()
    assert _eventos(execucao.ctx)[-1]["outcome_reason"] == (
        "Envio WhatsApp desabilitado na configuracao — nada enviado e state preservado."
    )


def test_envio_unico_com_reautenticacao_sai_com_21_sem_commit(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 21 com 1 card: WhatsApp pede reautenticacao; state nao commitado."""
    execucao = _executar_cenario(monkeypatch, pasta, _Cenario(envios=(21,)))

    assert execucao.codigo == 21
    assert not execucao.caminhos.estado.exists()
    assert not execucao.caminhos.estado_tmp.exists()
    assert _eventos(execucao.ctx)[-1]["outcome_reason"] == (
        "WhatsApp requer reautenticacao."
    )


def test_envio_unico_adiado_por_lock_sai_com_22_sem_commit(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 22 com 1 card: adiado por lock ou cooldown; state nao commitado."""
    execucao = _executar_cenario(monkeypatch, pasta, _Cenario(envios=(22,)))

    assert execucao.codigo == 22
    assert not execucao.caminhos.estado.exists()
    assert _eventos(execucao.ctx)[-1]["outcome_reason"] == (
        "WhatsApp adiado por lock ou cooldown da sessao hub-global."
    )


def test_envio_unico_com_falha_sai_com_4_e_nao_commita(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 4 com 1 card: falha do Send-WhatsApp (exit 24); as OBs serao reavaliadas."""
    execucao = _executar_cenario(monkeypatch, pasta, _Cenario(envios=(24,)))

    assert execucao.codigo == 4
    assert not execucao.caminhos.estado.exists()
    assert not execucao.caminhos.estado_tmp.exists()
    assert _eventos(execucao.ctx)[-1]["outcome_reason"] == (
        "Falha no envio WhatsApp (ExitCode=24). State NAO commitado — as OBs serao "
        "reavaliadas na proxima execucao."
    )


@pytest.mark.parametrize(
    ("codigo_envio", "codigo_esperado"),
    [(21, 21), (22, 22), (24, 4)],
)
def test_lote_sem_nenhuma_pagina_entregue_sai_pelo_codigo_do_whatsapp(
    pasta: Path,
    monkeypatch: pytest.MonkeyPatch,
    codigo_envio: int,
    codigo_esperado: int,
) -> None:
    """Desfechos 21, 22 e 4 no lote com 0 paginas entregues (NoneSent): state nao commitado."""
    cenario = _Cenario(
        cards=CARDS_LOTE,
        envios=(codigo_envio,),
        lote=LOTE_NENHUM_ENVIADO,
    )

    execucao = _executar_cenario(monkeypatch, pasta, cenario)

    assert execucao.codigo == codigo_esperado
    assert not execucao.caminhos.estado.exists()
    assert not execucao.caminhos.estado_tmp.exists()


@pytest.mark.parametrize(
    ("codigo_envio", "codigo_esperado", "trecho"),
    [
        (0, 4, "Envio WhatsApp parcial (1/2 paginas entregues, ExitCode=0)"),
        (21, 21, "WhatsApp requer reautenticacao apos envio parcial (1/2 paginas)."),
    ],
)
def test_lote_com_envio_parcial_commita_sem_as_obs_falhas_e_ajusta_contagens(
    pasta: Path,
    monkeypatch: pytest.MonkeyPatch,
    codigo_envio: int,
    codigo_esperado: int,
    trecho: str,
) -> None:
    """Desfechos 4 e 21 no lote parcial: OB da pagina falha sai do .tmp; record_counts ajustado."""
    cenario = _Cenario(
        cards=CARDS_LOTE,
        envios=(codigo_envio,),
        lote=LOTE_UMA_FALHOU,
    )

    execucao = _executar_cenario(monkeypatch, pasta, cenario)

    assert execucao.codigo == codigo_esperado
    assert trecho in str(_eventos(execucao.ctx)[-1]["outcome_reason"])
    assert _ler_json(execucao.caminhos.estado) == {
        "notified": {"OB-1": ESTADO_TMP["notified"]["OB-1"]}
    }
    assert not execucao.caminhos.estado_tmp.exists()
    contagens = _ler_json(execucao.caminhos.resultado)["record_counts"]
    assert contagens["pages_sent"] == 1
    assert contagens["pages_total"] == 2
    assert contagens["notified"] == 1


def test_lock_ocupado_sai_com_4_sem_executar_etapas(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 4 pelo catch externo: mutex OFST-06 ocupado, nenhuma etapa protegida roda."""
    duplos = _instalar(monkeypatch, _Cenario())
    monkeypatch.setattr(hr, "AutomationMutex", _MutexBloqueado)
    ctx = _contexto(pasta)

    codigo = rr.executar(ctx, rr.Caminhos.da_pasta(pasta, pasta))

    assert codigo == 4
    assert not duplos.extract.chamadas
    fim = _eventos(ctx)[-1]
    assert fim["outcome_reason"].startswith(
        "Falha critica na orquestracao: CONCORRENCIA DETECTADA"
    )


def test_excecao_na_extracao_sai_com_4_e_libera_o_lock(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 4 pelo catch externo: excecao dentro do fluxo; o mutex e liberado."""
    execucao = _executar_cenario(
        monkeypatch, pasta, _Cenario(extract=RuntimeError("boom"))
    )

    assert execucao.codigo == 4
    assert _MutexFalso.saidas == ["OFST-06"]
    assert _eventos(execucao.ctx)[-1]["outcome_reason"] == (
        "Falha critica na orquestracao: boom"
    )


# ---------------------------------------------------------------------------
# Dry-run: prepara e loga, sem enviar e sem commitar
# ---------------------------------------------------------------------------


def test_dry_run_com_um_card_roda_extract_e_formato_mas_nao_envia_nem_commita(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dry-run: extract e transform reais (dublados), nenhum envio, state vivo nao criado."""
    _estado_vivo(pasta)
    execucao = _executar_cenario(monkeypatch, pasta, _Cenario(), dry_run=True)

    assert execucao.codigo == 0
    assert not execucao.duplos.envio.chamadas
    assert execucao.duplos.formatador.chamadas == 1
    assert _ler_json(execucao.caminhos.estado) == ESTADO_VIVO
    assert not execucao.caminhos.batch_input.exists()
    mensagens = _mensagens(execucao.ctx)
    assert any(
        m.startswith("[DRY-RUN] Envio WhatsApp nao executado") for m in mensagens
    )
    assert any("Commit de estado nao executado" in m for m in mensagens)
    assert all(DESTINO not in m for m in mensagens)


def test_dry_run_em_lote_prepara_o_batch_input_sem_enviar(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dry-run com varios cards: batch_input.json e preparado, mas o lote nao e enviado."""
    cenario = _Cenario(cards=CARDS_LOTE, lote=LOTE_TUDO_ENVIADO)

    execucao = _executar_cenario(monkeypatch, pasta, cenario, dry_run=True)

    assert execucao.codigo == 0
    assert not execucao.duplos.envio.chamadas
    assert execucao.caminhos.batch_input.exists()
    assert not execucao.caminhos.estado.exists()


def test_dry_run_com_whatsapp_desabilitado_sai_com_2_sem_envio(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dry-run com o envio desabilitado na configuracao: mesma decisao do real, exit 2."""
    _desabilitar_destino(pasta)

    execucao = _executar_cenario(monkeypatch, pasta, _Cenario(), dry_run=True)

    assert execucao.codigo == 2
    assert not execucao.duplos.envio.chamadas
    assert not execucao.caminhos.estado.exists()


# ---------------------------------------------------------------------------
# Auxiliares: destino do WhatsApp, caminhos, rotacao e .env
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("alvo", "esperado"),
    [
        ({"contactIdEnv": DESTINO_ENV, "contactId": "placeholder"}, DESTINO),
        ({"contactId": "550000000000-0000000000@g.us"}, "550000000000-0000000000@g.us"),
    ],
)
def test_resolver_destino_devolve_o_valor_do_ambiente_ou_o_placeholder(
    alvo: dict[str, Any], esperado: str
) -> None:
    """Resolve-WhatsAppTarget: contactIdEnv vem do ambiente; sem ele, o contactId."""
    assert (
        rr._resolver_destino(alvo, Path("cfg.json")) == esperado
    )  # pylint: disable=protected-access


@pytest.mark.parametrize(
    "alvo",
    [
        {"contactIdEnv": "OFST_VARIAVEL_NAO_DEFINIDA"},
        {},
        "texto no lugar do objeto",
    ],
)
def test_resolver_destino_recusa_destino_ausente(alvo: object) -> None:
    """Resolve-WhatsAppTarget: variavel vazia, sem destino ou target que nao e objeto."""
    with pytest.raises(ValueError, match="Destino do WhatsApp ausente"):
        rr._resolver_destino(alvo, Path("cfg.json"))  # pylint: disable=protected-access


def test_caminhos_usam_os_nomes_de_arquivo_do_run_ps1(tmp_path: Path) -> None:
    """Os nomes de estado, resultado, manifesto e batch sao os do run.ps1 antigo."""
    caminhos = rr.Caminhos.da_pasta(tmp_path, tmp_path.parent)

    assert caminhos.estado.name == "ofst_state.json"
    assert caminhos.estado_tmp.name == "ofst_state.json.tmp"
    assert caminhos.resultado.name == "ofst_result.json"
    assert caminhos.manifesto.name == "cards_manifest.json"
    assert caminhos.batch_input.name == "batch_input.json"
    assert caminhos.batch_result.name == "batch_result.json"
    assert caminhos.send_wa == tmp_path.parent / "lib" / "Send-WhatsApp.ps1"


def test_rotacao_remove_eventos_anteriores_a_retencao(tmp_path: Path) -> None:
    """Invoke-LogRotation -KeepDays 15: eventos antigos saem do jsonl, os recentes ficam."""
    caminho = tmp_path / "Ofst.jsonl"
    antigo = (date.today() - timedelta(days=30)).isoformat()
    hoje = date.today().isoformat()
    caminho.write_text(
        f'{{"ts":"{antigo}T10:00:00Z","message":"antigo"}}\r\n'
        f'{{"ts":"{hoje}T10:00:00Z","message":"recente"}}\r\n',
        encoding="utf-8",
    )

    rr._rotacionar_log(caminho)  # pylint: disable=protected-access

    mantidas = caminho.read_text(encoding="utf-8-sig").splitlines()
    assert len(mantidas) == 1
    assert "recente" in mantidas[0]


@pytest.mark.parametrize(
    ("linha", "esperado"),
    [
        (
            "OFST_WHATSAPP_TARGET=valor-de-teste",
            ("OFST_WHATSAPP_TARGET", "valor-de-teste"),
        ),
        ("  CHAVE = valor  ", ("CHAVE", "valor")),
        ("# so comentario", None),
        ("SEM_IGUAL", None),
        ("VAZIA=", None),
    ],
)
def test_ler_linha_env_segue_convert_from_env_line(
    linha: str, esperado: tuple[str, str] | None
) -> None:
    """ConvertFrom-EnvLine: chave e valor com aparagem; comentario e linha vazia ficam fora."""
    assert rr._ler_linha_env(linha) == esperado  # pylint: disable=protected-access


def test_sessao_padrao_nao_confirma_estado_nem_encerra(tmp_path: Path) -> None:
    """Estado inicial da sessao: nada confirmado, nada encerrado, sem destino mascarado."""
    ctx = hr.create_run_context(
        hr.AutomationSpec(
            automacao="OBs Fluxo Sem Tingimento",
            slug="Ofst",
            trace_slug="ofst",
            lock_key="OFST-06",
            non_failure_codes=(0, 2, 22),
        ),
        exec_id=EXEC_ID,
        telemetry=None,
        project_root=tmp_path,
    )
    sessao = rr._Sessao(  # pylint: disable=protected-access
        ctx=ctx,
        caminhos=rr.Caminhos.da_pasta(tmp_path, tmp_path),
        dry_run=False,
    )

    assert sessao.estado_confirmado is False
    assert sessao.encerrada is False
    assert sessao.destino_mascarado == ""
    assert sessao.cards == ()
    assert sessao.config_wa == {}
