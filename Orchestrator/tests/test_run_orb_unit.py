"""Testes unitarios do runner de OBs Restrição Branco (OBs Restricao Branco/run_orb.py).

Sem Oracle, sem WhatsApp e sem rede. O passo de extracao (hr.run_python_step), o formatador
(ro._executar_formatador), o envio (hw.send_whatsapp) e o mutex ORB-07 (hr.AutomationMutex,
que so existe no Windows) sao substituidos por dubles. Os arquivos da automacao vivem em
tmp_path: nunca na pasta OBs Restricao Branco nem em Logs/ do repo. Manifesto de cards,
batch_input, reconciliacao do lote e record_counts sao os reais de hub_whatsapp, lidos de
arquivos temporarios. O envio real (argv do Send-WhatsApp.ps1) e conferido com um executor
falso injetado em hw.send_whatsapp.

Cada desfecho do run.ps1 antigo tem pelo menos um teste (codigos 0, 1, 2, 3, 4, 9, 21, 22,
26 e 27); o dry-run tem os seus. Os nomes dos testes dizem o desfecho.
"""

from __future__ import annotations

import json
import os
import re
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
ORB_DIR = RAIZ_REPO / "OBs Restricao Branco"
ro: Any = carregar_modulo_automacao("run_orb", ORB_DIR / "run_orb.py")

DESTINO_ENV = "OFST_WHATSAPP_TARGET"
DESTINO = "TESTE-DESTINO-GRUPO-4417"
EXEC_ID = "EXEC-TESTE-ORB-0001"
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
    """Dublê de hr.run_python_step para o extract_orb.py.

    Devolve o desfecho da etapa ou levanta a excecao. Como o script real, grava o .tmp do
    state (quando ``grava_tmp``) e, no sucesso, o orb_result.json com record_counts.
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
            (pasta / "orb_state.json.tmp").write_text(
                json.dumps(ESTADO_TMP), encoding="utf-8"
            )
        if self.resposta.success:
            (pasta / "orb_result.json").write_text(
                json.dumps(RESULTADO_EXTRACAO), encoding="utf-8"
            )
        return self.resposta


class _FormatadorFalso:
    """Dublê de ro._executar_formatador: devolve o exit code e, como format_message.py,
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
    """Dublê de um mutex ORB-07 ja ocupado por outra execucao."""

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
            "CONCORRENCIA DETECTADA: ja existe um processo com o lock ORB-07."
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
    mutex: Any = _MutexFalso


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
    monkeypatch.setattr(ro, "_espaco_livre_gb", lambda _caminho: 10.0)
    (tmp_path / "extract_orb.py").write_text("# script falso\n", encoding="utf-8")
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
    monkeypatch.setattr(ro, "_executar_formatador", duplos.formatador)
    monkeypatch.setattr(hw, "send_whatsapp", duplos.envio)
    monkeypatch.setattr(hr, "AutomationMutex", cenario.mutex)
    _MutexFalso.chaves.clear()
    _MutexFalso.saidas.clear()
    return duplos


def _contexto(pasta: Path) -> hr.HubRunContext:
    """Contexto de log da execucao de teste: ExecId fixo, sem telemetria, log em tmp."""
    return hr.create_run_context(
        hr.AutomationSpec(
            automacao=ro.AUTOMACAO,
            slug=ro.SLUG_LOG,
            trace_slug=ro.SLUG_TRACE,
            lock_key=ro.CHAVE_LOCK,
            log_dir=pasta / "Logs",
            non_failure_codes=ro.CODIGOS_SEM_FALHA,
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
    caminhos = ro.Caminhos.da_pasta(pasta, pasta)
    codigo = ro.executar(ctx, caminhos, dry_run=dry_run)
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


def _motivo(ctx: hr.HubRunContext) -> str:
    """Motivo de saida (outcome_reason do execution.end): a mensagem final do run.ps1."""
    return str(_eventos(ctx)[-1]["outcome_reason"])


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
    """Grava o orb_state.json definitivo, como ficaria depois de uma execucao anterior."""
    (pasta / "orb_state.json").write_text(json.dumps(ESTADO_VIVO), encoding="utf-8")


def _ler_json(caminho: Path) -> Any:
    """JSON de um arquivo da automacao."""
    return json.loads(caminho.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Identidade: os nomes que o Orchestrator e o log usam nao podem mudar
# ---------------------------------------------------------------------------


def test_identidade_bate_com_o_run_ps1_antigo() -> None:
    """Nome da automacao, chave do lock, slug de log e codigos sem falha do run.ps1 antigo."""
    assert ro.AUTOMACAO == "OBs Restrição Branco"
    assert ro.CHAVE_LOCK == "ORB-07"
    assert ro.SLUG_LOG == "Orb"
    assert ro.SLUG_TRACE == "orb"
    assert ro.CODIGOS_SEM_FALHA == (0, 2, 22)


def test_caminhos_usam_os_nomes_de_arquivo_do_run_ps1(tmp_path: Path) -> None:
    """Os arquivos de estado, resultado e envio tem o nome que o run.ps1 antigo usava."""
    caminhos = ro.Caminhos.da_pasta(tmp_path, tmp_path.parent)

    assert caminhos.extract_py.name == "extract_orb.py"
    assert caminhos.format_py.name == "format_message.py"
    assert caminhos.config_wa.name == "whatsapp-config.json"
    assert caminhos.estado.name == "orb_state.json"
    assert caminhos.estado_tmp.name == "orb_state.json.tmp"
    assert caminhos.resultado.name == "orb_result.json"
    assert caminhos.manifesto.name == "cards_manifest.json"
    assert caminhos.mensagem.name == "message.txt"
    assert caminhos.card.name == "card.png"
    assert caminhos.batch_input.name == "batch_input.json"
    assert caminhos.batch_result.name == "batch_result.json"
    assert caminhos.send_wa == tmp_path.parent / "lib" / "Send-WhatsApp.ps1"


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
        (pasta / "extract_orb.py").unlink()
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

    monkeypatch.setattr(ro, "_resultado_oracle", quebra)

    execucao = _executar_cenario(monkeypatch, pasta, _Cenario())

    assert execucao.codigo == 1
    assert not execucao.duplos.extract.chamadas
    assert not _MutexFalso.chaves
    fim = _eventos(execucao.ctx)[-1]
    assert fim["event"] == "execution.end"
    assert fim["outcome_reason"] == "ERRO FATAL: falha inesperada no pre-flight"


def test_aviso_de_env_que_nao_carregou_vira_warn_apos_o_inicio(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Import-HubEnv com falha: aviso WARN de preflight, logo depois do inicio da execucao."""
    _instalar(monkeypatch, _Cenario())
    ctx = _contexto(pasta)

    ro.executar(
        ctx,
        ro.Caminhos.da_pasta(pasta, pasta),
        aviso_env="permissao negada",
    )

    eventos = _eventos(ctx)
    assert eventos[0]["event"] == "execution.start"
    assert eventos[1]["message"] == "Aviso: falha ao carregar .env: permissao negada"
    assert eventos[1]["level"] == "WARN"


# ---------------------------------------------------------------------------
# Fluxo protegido pelo lock: cada desfecho do run.ps1 antigo
# ---------------------------------------------------------------------------


def test_envio_unico_com_sucesso_commita_o_state_e_sai_com_0(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 0: um card enviado; o .tmp vira orb_state.json e o lock usa a chave ORB-07."""
    execucao = _executar_cenario(monkeypatch, pasta, _Cenario())

    assert execucao.codigo == 0
    assert _MutexFalso.chaves == ["ORB-07"]
    assert _MutexFalso.saidas == ["ORB-07"]
    assert _ler_json(pasta / "orb_state.json") == ESTADO_TMP
    assert not (pasta / "orb_state.json.tmp").exists()
    fim = _eventos(execucao.ctx)[-1]
    assert fim["outcome_code"] == 0
    assert fim["outcome_reason"] == "Execucao concluida com sucesso (1 card(s))."


def test_envio_em_lote_com_sucesso_usa_modo_batch_e_commita(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 0 em lote: dois cards em modo BATCH, todos com success e state commitado."""
    cenario = _Cenario(cards=CARDS_LOTE, lote=LOTE_TUDO_ENVIADO)

    execucao = _executar_cenario(monkeypatch, pasta, cenario)

    assert execucao.codigo == 0
    chamada = execucao.duplos.envio.chamadas[0]
    assert chamada["mode"] == "BATCH"
    assert chamada["batch_input_file"] == pasta / "batch_input.json"
    assert chamada["batch_result_file"] == pasta / "batch_result.json"
    assert (pasta / "orb_state.json").exists()
    assert execucao.ctx.log_path.exists()


def test_extracao_idempotente_reconcilia_o_tmp_e_sai_com_2_sem_envio(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 2 (extract idempotente): o .tmp e promovido sem envio e sai com 2."""
    cenario = _Cenario(
        extract=hr.PythonStepResult(
            success=False,
            idempotent=True,
            non_retryable=False,
            output="",
            exit_code=2,
            attempts=1,
        )
    )

    execucao = _executar_cenario(monkeypatch, pasta, cenario)

    assert execucao.codigo == 2
    assert not execucao.duplos.envio.chamadas
    assert _ler_json(pasta / "orb_state.json") == ESTADO_TMP
    assert "State reconciliado sem necessidade de envio." in _mensagens(execucao.ctx)


def test_extracao_idempotente_sem_tmp_sai_com_2_e_nao_commita(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 2 sem .tmp: nada a reconciliar, sem envio e sem state criado."""
    cenario = _Cenario(
        extract=hr.PythonStepResult(
            success=False,
            idempotent=True,
            non_retryable=False,
            output="",
            exit_code=2,
            attempts=1,
        ),
        grava_tmp=False,
    )

    execucao = _executar_cenario(monkeypatch, pasta, cenario)

    assert execucao.codigo == 2
    assert not execucao.duplos.envio.chamadas
    assert not (pasta / "orb_state.json").exists()
    assert _motivo(execucao.ctx) == (
        "Nenhuma OB nova com estoque suficiente — nada a notificar."
    )


@pytest.mark.parametrize(
    ("codigo_python", "non_retryable", "codigo_canonico"),
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
    codigo_python: int,
    non_retryable: bool,
    codigo_canonico: int,
) -> None:
    """Desfechos 3, 26 e 27: a falha do extract vira o codigo canonico; nada e enviado."""
    cenario = _Cenario(
        extract=hr.PythonStepResult(
            success=False,
            idempotent=False,
            non_retryable=non_retryable,
            output="",
            exit_code=codigo_python,
            attempts=1,
        )
    )

    execucao = _executar_cenario(monkeypatch, pasta, cenario)

    assert execucao.codigo == codigo_canonico
    assert not execucao.duplos.formatador.chamadas
    assert not execucao.duplos.envio.chamadas
    assert not (pasta / "orb_state.json").exists()
    assert not (pasta / "orb_state.json.tmp").exists()
    assert _MutexFalso.saidas == ["ORB-07"]
    assert _motivo(execucao.ctx) == (
        f"Falha definitiva na extracao Oracle (PythonExit={codigo_python})."
    )


def test_formatador_sem_ob_qualificada_sai_com_2_sem_mensagem(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 2 no transform: format_message.py sem OB qualificada, sem envio."""
    execucao = _executar_cenario(monkeypatch, pasta, _Cenario(formato=2, cards=None))

    assert execucao.codigo == 2
    assert not execucao.duplos.envio.chamadas
    assert not (pasta / "orb_state.json").exists()
    assert _motivo(execucao.ctx) == "Nenhuma OB qualificada — mensagem nao gerada."


def test_formatador_com_erro_sai_com_4(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 4: format_message.py com exit diferente de 0 e de 2 (sem retry)."""
    execucao = _executar_cenario(monkeypatch, pasta, _Cenario(formato=1, cards=None))

    assert execucao.codigo == 4
    assert execucao.duplos.formatador.chamadas == 1
    assert not execucao.duplos.envio.chamadas
    assert _motivo(execucao.ctx) == "Falha em format_message.py. ExitCode=1"


def test_manifesto_de_cards_invalido_sai_com_4_sem_envio(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 4: exit 0 do formatador sem cards_manifest.json e o envio nao acontece."""
    execucao = _executar_cenario(monkeypatch, pasta, _Cenario(formato=0, cards=None))

    assert execucao.codigo == 4
    assert not execucao.duplos.envio.chamadas
    assert "cards_manifest.json nao encontrado." in _motivo(execucao.ctx)


def test_whatsapp_desabilitado_na_configuracao_sai_com_2_sem_envio(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 2: target.enabled = false; nada enviado e state preservado."""
    _desabilitar_destino(pasta)

    execucao = _executar_cenario(monkeypatch, pasta, _Cenario())

    assert execucao.codigo == 2
    assert not execucao.duplos.envio.chamadas
    assert not (pasta / "orb_state.json").exists()
    assert any("State NAO commitado." in m for m in _mensagens(execucao.ctx))


def test_envio_unico_com_reautenticacao_sai_com_21_sem_commit(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 21 (um card): WhatsApp pede reautenticacao; o .tmp nao e commitado."""
    execucao = _executar_cenario(monkeypatch, pasta, _Cenario(envios=(21,)))

    assert execucao.codigo == 21
    assert not (pasta / "orb_state.json").exists()
    assert not (pasta / "orb_state.json.tmp").exists()
    assert _motivo(execucao.ctx) == "WhatsApp requer reautenticacao."


def test_envio_unico_adiado_por_lock_sai_com_22_sem_commit(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 22 (um card): adiado por lock ou cooldown; sem commit e sem alerta de falha."""
    execucao = _executar_cenario(monkeypatch, pasta, _Cenario(envios=(22,)))

    assert execucao.codigo == 22
    assert not (pasta / "orb_state.json").exists()
    fim = _eventos(execucao.ctx)[-1]
    assert fim["event"] == "execution.end"
    assert fim["outcome_code"] == 22


def test_envio_unico_com_falha_sai_com_4_e_nao_commita(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 4 (um card): falha do Send-WhatsApp; as OBs serao reavaliadas depois."""
    execucao = _executar_cenario(monkeypatch, pasta, _Cenario(envios=(1,)))

    assert execucao.codigo == 4
    assert not (pasta / "orb_state.json").exists()
    assert not (pasta / "orb_state.json.tmp").exists()
    motivo = _motivo(execucao.ctx)
    assert "State NAO commitado" in motivo
    assert "ExitCode=1" in motivo


@pytest.mark.parametrize(
    ("codigo_envio", "codigo_final"),
    [(1, 4), (21, 21), (22, 22)],
)
def test_lote_sem_nenhuma_pagina_entregue_sai_pelo_codigo_do_whatsapp(
    pasta: Path,
    monkeypatch: pytest.MonkeyPatch,
    codigo_envio: int,
    codigo_final: int,
) -> None:
    """Desfechos 4, 21 e 22 em lote sem entrega: o codigo do WhatsApp decide a saida."""
    cenario = _Cenario(
        cards=CARDS_LOTE, envios=(codigo_envio,), lote=LOTE_NENHUM_ENVIADO
    )

    execucao = _executar_cenario(monkeypatch, pasta, cenario)

    assert execucao.codigo == codigo_final
    assert not (pasta / "orb_state.json").exists()
    assert not (pasta / "orb_state.json.tmp").exists()


@pytest.mark.parametrize(
    ("codigo_envio", "codigo_final"),
    [(1, 4), (21, 21)],
)
def test_lote_com_envio_parcial_commita_sem_as_obs_falhas_e_ajusta_contagens(
    pasta: Path,
    monkeypatch: pytest.MonkeyPatch,
    codigo_envio: int,
    codigo_final: int,
) -> None:
    """Envio parcial: a OB da pagina que falhou sai do state, o resto e commitado e o record_counts muda."""
    cenario = _Cenario(cards=CARDS_LOTE, envios=(codigo_envio,), lote=LOTE_UMA_FALHOU)

    execucao = _executar_cenario(monkeypatch, pasta, cenario)

    assert execucao.codigo == codigo_final
    estado = _ler_json(pasta / "orb_state.json")
    assert list(estado["notified"]) == ["OB-1"]
    contagens = _ler_json(pasta / "orb_result.json")["record_counts"]
    assert contagens["notified"] == 1
    assert contagens["sent"] == 1
    assert contagens["pages_sent"] == 1
    assert contagens["pages_total"] == 2
    assert not (pasta / "orb_state.json.tmp").exists()


def test_lock_ocupado_sai_com_4_sem_executar_etapas(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 4 (catch externo): mutex ORB-07 ocupado; nenhuma etapa do extract roda."""
    execucao = _executar_cenario(monkeypatch, pasta, _Cenario(mutex=_MutexBloqueado))

    assert execucao.codigo == 4
    assert not execucao.duplos.extract.chamadas
    assert not execucao.duplos.envio.chamadas
    eventos = _eventos(execucao.ctx)
    assert "lock" in _passos_iniciados(eventos)
    assert "extract" not in _passos_iniciados(eventos)
    assert eventos[-1]["outcome_reason"].startswith(
        "Falha critica na orquestracao: CONCORRENCIA DETECTADA"
    )


def test_excecao_na_extracao_sai_com_4_e_libera_o_lock(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 4 (excecao de etapa): sai com 4 e o mutex e liberado pelo with."""
    cenario = _Cenario(extract=RuntimeError("quebra na extracao"), grava_tmp=False)

    execucao = _executar_cenario(monkeypatch, pasta, cenario)

    assert execucao.codigo == 4
    assert _MutexFalso.saidas == ["ORB-07"]
    assert _eventos(execucao.ctx)[-1]["outcome_reason"] == (
        "Falha critica na orquestracao: quebra na extracao"
    )


# ---------------------------------------------------------------------------
# Dry-run: roda extract e transform, nao envia e nao commita
# ---------------------------------------------------------------------------


def test_dry_run_com_um_card_roda_extract_e_formato_mas_nao_envia_nem_commita(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dry-run: extract e formato rodam; o envio so e logado, com o destino mascarado."""
    execucao = _executar_cenario(monkeypatch, pasta, _Cenario(), dry_run=True)

    assert execucao.codigo == 0
    assert len(execucao.duplos.extract.chamadas) == 1
    assert execucao.duplos.formatador.chamadas == 1
    assert not execucao.duplos.envio.chamadas
    assert not (pasta / "orb_state.json").exists()
    mensagens = _mensagens(execucao.ctx)
    assert any("[DRY-RUN] Envio WhatsApp nao executado" in m for m in mensagens)
    assert any("***4417" in m for m in mensagens)
    assert not any(DESTINO in m for m in mensagens)
    assert any("seria promovido a orb_state.json" in m for m in mensagens)


def test_dry_run_em_lote_prepara_o_batch_input_sem_enviar(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dry-run em lote: grava o batch_input.json (arquivo local) e nao chama o envio."""
    cenario = _Cenario(cards=CARDS_LOTE)

    execucao = _executar_cenario(monkeypatch, pasta, cenario, dry_run=True)

    assert execucao.codigo == 0
    assert (pasta / "batch_input.json").exists()
    assert not execucao.duplos.envio.chamadas
    assert any("modo BATCH" in m for m in _mensagens(execucao.ctx) if "DRY-RUN" in m)


def test_dry_run_com_whatsapp_desabilitado_sai_com_2_sem_envio(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dry-run com WhatsApp desabilitado: sai com 2 antes do ramo de dry-run."""
    _desabilitar_destino(pasta)

    execucao = _executar_cenario(monkeypatch, pasta, _Cenario(), dry_run=True)

    assert execucao.codigo == 2
    assert not execucao.duplos.envio.chamadas


# ---------------------------------------------------------------------------
# Envio real: argv do Send-WhatsApp.ps1 com o executor falso injetado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cards", "modo", "lote"),
    [
        (CARD_UNICO, "AUTO", None),
        (CARDS_LOTE, "BATCH", LOTE_TUDO_ENVIADO),
    ],
)
def test_argv_do_envio_segue_o_send_whatsapp_do_run_ps1_antigo(
    pasta: Path,
    monkeypatch: pytest.MonkeyPatch,
    cards: tuple[CardSpec, ...],
    modo: str,
    lote: list[dict[str, Any]] | None,
) -> None:
    """Um card: -Mode AUTO (padrao do Send-WhatsApp.ps1), sem arquivos de lote; lote: -Mode BATCH."""
    original = hw.send_whatsapp
    capturados: list[Any] = []

    def executor(comando: Any, _encaminhar: Any) -> int:
        capturados.append(comando)
        resultado = (
            comando.argv[comando.argv.index("-BatchResultFile") + 1]
            if ("-BatchResultFile" in comando.argv)
            else None
        )
        if resultado is not None and lote is not None:
            Path(resultado).write_text(json.dumps(lote), encoding="utf-8")
        return 0

    def envio(ctx: hr.HubRunContext, **kwargs: Any) -> int:
        return original(ctx, executor=executor, **kwargs)

    _instalar(monkeypatch, _Cenario(cards=cards, lote=lote))
    monkeypatch.setattr(hw, "send_whatsapp", envio)
    ctx = _contexto(pasta)

    codigo = ro.executar(ctx, ro.Caminhos.da_pasta(pasta, pasta))

    assert codigo == 0
    assert len(capturados) == 1
    comando = capturados[0]
    argv = list(comando.argv)
    assert argv[:4] == ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass"]
    assert (
        argv[argv.index("-File") + 1]
        .replace("\\", "/")
        .endswith("lib/Send-WhatsApp.ps1")
    )
    assert argv[argv.index("-ExecId") + 1] == EXEC_ID
    assert argv[argv.index("-Mode") + 1] == modo
    assert argv[argv.index("-ConfigPath") + 1] == str(pasta / "whatsapp-config.json")
    assert argv[argv.index("-LogFile") + 1] == str(ctx.log_path)
    assert ("-BatchInputFile" in argv) == (modo == "BATCH")
    assert ("-BatchResultFile" in argv) == (modo == "BATCH")
    assert comando.work_dir == pasta


# ---------------------------------------------------------------------------
# Auxiliares: destino, mascara, .env, rotacao e shim
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("alvo", "esperado"),
    [
        ({"contactIdEnv": DESTINO_ENV}, DESTINO),
        ({"contactId": "550000000000-0000000000@g.us"}, "550000000000-0000000000@g.us"),
    ],
)
def test_resolver_destino_devolve_o_valor_do_ambiente_ou_o_placeholder(
    alvo: dict[str, str], esperado: str
) -> None:
    """Resolve-WhatsAppTarget: contactIdEnv vence; sem ele, o placeholder do contactId."""
    assert ro._resolver_destino(alvo, Path("whatsapp-config.json")) == esperado


@pytest.mark.parametrize("alvo", [None, {}])
def test_resolver_destino_recusa_destino_ausente(alvo: object) -> None:
    """Sem target util, o pre-flight falha: nunca envia para um destino vazio."""
    with pytest.raises(ValueError, match="Destino do WhatsApp ausente"):
        ro._resolver_destino(alvo, Path("whatsapp-config.json"))


def test_resolver_destino_recusa_env_vazia(monkeypatch: pytest.MonkeyPatch) -> None:
    """contactIdEnv apontando para variavel vazia: a mensagem cita o nome da variavel."""
    monkeypatch.delenv(DESTINO_ENV)

    with pytest.raises(ValueError, match="variavel de ambiente 'OFST_WHATSAPP_TARGET'"):
        ro._resolver_destino(
            {"contactIdEnv": DESTINO_ENV}, Path("whatsapp-config.json")
        )


def test_mascara_mostra_so_os_quatro_ultimos_caracteres() -> None:
    """Destinatario no log de dry-run: so os 4 ultimos caracteres aparecem."""
    assert ro._mascarar(DESTINO) == "***4417"
    assert ro._mascarar("1234") == "***"


@pytest.mark.parametrize(
    ("linha", "esperado"),
    [
        ("", None),
        ("# comentario", None),
        ("SEM_VALOR=", None),
        ("CHAVE=valor # comentario", ("CHAVE", "valor")),
        ("  X = 1 ", ("X", "1")),
    ],
)
def test_ler_linha_env_segue_convert_from_env_line(
    linha: str, esperado: tuple[str, str] | None
) -> None:
    """Linha do .env como ConvertFrom-EnvLine: comentario e valor vazio nao contam."""
    assert ro._ler_linha_env(linha) == esperado


def test_rotacao_remove_eventos_anteriores_a_retencao(tmp_path: Path) -> None:
    """Invoke-LogRotation: eventos com ts anterior a 15 dias saem do jsonl."""
    antigo = (date.today() - timedelta(days=40)).isoformat()
    hoje = date.today().isoformat()
    caminho = tmp_path / "Orb.jsonl"
    caminho.write_text(
        f'{{"ts":"{antigo}T10:00:00Z","event":"log"}}\n'
        f'{{"ts":"{hoje}T10:00:00Z","event":"log"}}\n',
        encoding="utf-8",
    )

    ro._rotacionar_log(caminho)

    restante = caminho.read_text(encoding="utf-8-sig").splitlines()
    assert len(restante) == 1
    assert hoje in restante[0]


def test_shim_delega_ao_runner_e_repassa_o_exit_code() -> None:
    """O run.ps1 e shim: resolve o python, chama run_orb.py e sai com o mesmo exit code.

    Lock, telemetria, pre-flight e envio ficam no runner: o shim nao pode te-los.
    """
    fonte = (ORB_DIR / "run.ps1").read_text(encoding="utf-8-sig")

    assert "Resolve-HubPythonExe" in fonte
    assert '"run_orb.py"' in fonte
    assert "exit $LASTEXITCODE" in fonte
    assert "--dry-run" in fonte
    assert re.search(r"Test-Path\s+-LiteralPath\s+\$pythonExe", fonte)
    assert "exit 9" in fonte
    assert "Enter-AutomationLock" not in fonte
    assert "Register-ExecutionTelemetry" not in fonte
    assert "Send-WhatsApp" not in fonte
    assert not re.search(r"[A-Za-z]:\\", fonte), "shim sem caminhos absolutos"


def test_runner_fecha_a_execucao_em_um_unico_ponto() -> None:
    """Toda saida do runner passa por _encerrar, que chama hr.finish (execution.end e telemetria)."""
    fonte = (ORB_DIR / "run_orb.py").read_text(encoding="utf-8")

    assert fonte.count("hr.finish(") == 1, "so _encerrar pode chamar hr.finish"
    assert fonte.count("hw.send_whatsapp(") == 1, "um unico ponto de envio"
