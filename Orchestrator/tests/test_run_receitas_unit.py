"""Testes unitarios do runner de Receitas Emitidas (Receitas Emitidas/run_receitas.py).

Sem Oracle, sem Outlook e sem rede. Os passos Python (hr.run_python_step), a CLI de
e-mail (hr.send_outlook_email e hr.send_failure_alert), o mutex RE-03 (hr.AutomationMutex,
que so existe no Windows), a fila Oracle e o disco sao substituidos por dubles. Os
arquivos da automacao vivem em tmp_path: nunca em Receitas Emitidas/ nem em Logs/ do repo.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import hub_runner as hr
import pytest
from tests.carregadores_modulos import carregar_modulo_automacao

# Os dublês de teste sao deliberadamente minimos (um metodo cada).
# pylint: disable=too-few-public-methods

RAIZ_REPO = Path(__file__).resolve().parents[2]
rr: Any = carregar_modulo_automacao(
    "run_receitas", RAIZ_REPO / "Receitas Emitidas" / "run_receitas.py"
)

DESTINO = "destino@teste.invalid"
PREFIXO = "Relatorio Semanal: Controle de Receitas Emitidas"
INTRO = "Segue relatorio atualizado."
HASH_NOVO = "HASH-NOVO"
EXTRACAO_OK = hr.PythonStepResult(
    success=True,
    idempotent=False,
    non_retryable=False,
    output='[{"NUMERO_OB": "OB-1"}]\n',
    exit_code=0,
    attempts=1,
)
HTML_OK = hr.PythonStepResult(
    success=True,
    idempotent=False,
    non_retryable=False,
    output="<html>relatorio</html>\n",
    exit_code=0,
    attempts=1,
)


class _PassosFalsos:
    """Dublê de hr.run_python_step: devolve o desfecho da etapa, ou levanta se for excecao."""

    def __init__(self, respostas: dict[str, Any]) -> None:
        self.respostas = respostas
        self.chamadas: list[Any] = []

    def __call__(self, _ctx: Any, spec: Any, **_kwargs: object) -> Any:
        self.chamadas.append(spec)
        resposta = self.respostas[spec.step]
        if isinstance(resposta, BaseException):
            raise resposta
        return resposta


class _EmailFalso:
    """Dublê de hr.send_outlook_email: consome as respostas em ordem e registra o envio."""

    def __init__(self, respostas: list[bool]) -> None:
        self.respostas = list(respostas)
        self.chamadas: list[dict[str, str]] = []

    def __call__(self, _ctx: Any, *, to: str, subject: str, html_body: str) -> bool:
        self.chamadas.append({"to": to, "subject": subject, "html_body": html_body})
        return self.respostas.pop(0)


class _AlertaFalso:
    """Dublê de hr.send_failure_alert: registra o alerta de falha definitiva."""

    def __init__(self) -> None:
        self.chamadas: list[dict[str, Any]] = []

    def __call__(
        self, _ctx: Any, *, task_name: str, ultimo_erro: str, tentativas: int
    ) -> bool:
        self.chamadas.append(
            {
                "task_name": task_name,
                "ultimo_erro": ultimo_erro,
                "tentativas": tentativas,
            }
        )
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
    """Dublê de um mutex RE-03 ja ocupado por outra execucao."""

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
            "CONCORRENCIA DETECTADA: ja existe um processo com o lock RE-03."
        )

    def __exit__(self, _tipo: object, _valor: object, _rastro: object) -> None:
        return None


@dataclass
class _Duplos:
    """Conjunto de dublês instalado num teste, com as esperas registradas."""

    passos: _PassosFalsos
    email: _EmailFalso
    alerta: _AlertaFalso
    esperas: list[float]


@pytest.fixture(autouse=True)
def _ambiente_isolado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove variaveis do ambiente real que mudariam o pre-flight ou a telemetria."""
    for chave in (
        "HUB_TRACE_ID",
        "ORACLE_CONNECT_STRING",
        "ORACLE_QUEUE_DIR",
        "ORACLE_CLIENT_PATH",
        "ENVIRONMENT",
    ):
        monkeypatch.delenv(chave, raising=False)
    monkeypatch.setenv("RE_EMAIL_TO", DESTINO)


@pytest.fixture(name="pasta")
def _pasta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pasta de automacao falsa: scripts vazios, config, .tmp de estado e Oracle Client."""
    cliente = tmp_path / "oracle_client"
    cliente.mkdir()
    (cliente / "oci.dll").write_bytes(b"")
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "thick")
    monkeypatch.setenv("ORACLE_CLIENT_LIB_DIR", str(cliente))
    monkeypatch.setattr(rr, "_espaco_livre_gb", lambda _caminho: 10.0)
    (tmp_path / "extract_oracle.py").write_text("# script falso\n", encoding="utf-8")
    (tmp_path / "generate_html_report.py").write_text(
        "# script falso\n", encoding="utf-8"
    )
    config = {
        "email": {
            "to": "placeholder@teste.invalid",
            "subject_prefix": PREFIXO,
            "intro_text": INTRO,
        }
    }
    (tmp_path / "receitas_config.json").write_text(
        json.dumps(config, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "receitas_state.json.tmp").write_text(
        json.dumps({"last_hash": HASH_NOVO}), encoding="utf-8"
    )
    return tmp_path


def _instalar(
    monkeypatch: pytest.MonkeyPatch,
    respostas: dict[str, Any],
    respostas_email: list[bool] | None = None,
) -> _Duplos:
    """Substitui os passos, a CLI de e-mail, o alerta, o mutex e a espera pelos dublês."""
    duplos = _Duplos(
        passos=_PassosFalsos(respostas),
        email=_EmailFalso(respostas_email or [True]),
        alerta=_AlertaFalso(),
        esperas=[],
    )
    monkeypatch.setattr(hr, "run_python_step", duplos.passos)
    monkeypatch.setattr(hr, "send_outlook_email", duplos.email)
    monkeypatch.setattr(hr, "send_failure_alert", duplos.alerta)
    monkeypatch.setattr(hr, "AutomationMutex", _MutexFalso)
    monkeypatch.setattr(rr, "_aguardar", duplos.esperas.append)
    _MutexFalso.chaves.clear()
    _MutexFalso.saidas.clear()
    return duplos


def _contexto(pasta: Path) -> hr.HubRunContext:
    """Contexto de log da execucao de teste: ExecId fixo, sem telemetria, log em tmp."""
    return hr.create_run_context(
        hr.AutomationSpec(
            automacao="Receitas Emitidas",
            slug="ReceitasEmitidas",
            trace_slug="re",
            lock_key="RE-03",
            log_dir=pasta / "Logs",
            non_failure_codes=(0,),
        ),
        exec_id="EXEC-TESTE-0001",
        telemetry=None,
        project_root=pasta,
    )


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


def test_fluxo_feliz_extrai_transforma_envia_e_confirma(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    duplos = _instalar(
        monkeypatch, {"extract": EXTRACAO_OK, "transform": HTML_OK}, [True]
    )
    ctx = _contexto(pasta)
    caminhos = rr.Caminhos.da_pasta(pasta)

    codigo = rr.executar(ctx, caminhos)

    assert codigo == 0
    assert [s.step for s in duplos.passos.chamadas] == ["extract", "transform"]
    assert duplos.passos.chamadas[0].python_exe == sys.executable
    assert duplos.passos.chamadas[1].input_data == EXTRACAO_OK.output
    assert len(duplos.email.chamadas) == 1
    envio = duplos.email.chamadas[0]
    assert envio["to"] == DESTINO
    assert envio["subject"] == f"{PREFIXO} - {datetime.now():%d/%m/%Y}"
    assert envio["html_body"] == f"<p>{INTRO}</p>{HTML_OK.output}"
    assert not caminhos.estado_tmp.exists()
    assert json.loads(caminhos.estado.read_text(encoding="utf-8")) == {
        "last_hash": HASH_NOVO
    }
    entrega = json.loads(caminhos.entrega.read_text(encoding="utf-8-sig"))
    assert entrega["delivery_status"]["email"]["success"] is True
    assert _MutexFalso.chaves == ["RE-03"]
    eventos = _eventos(ctx)
    assert _passos_iniciados(eventos) == [
        "preflight",
        "lock",
        "extract",
        "transform",
        "dispatch",
        "commit",
    ]
    assert eventos[-1]["event"] == "execution.end"
    assert eventos[-1]["outcome_code"] == 0
    assert eventos[-1]["level"] == "INFO"
    assert {e["component"] for e in eventos} == {"ps_script"}


def test_extracao_idempotente_encerra_com_zero_sem_email(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    idempotente = hr.PythonStepResult(
        success=False,
        idempotent=True,
        non_retryable=False,
        output="",
        exit_code=2,
        attempts=1,
    )
    duplos = _instalar(monkeypatch, {"extract": idempotente})
    ctx = _contexto(pasta)
    caminhos = rr.Caminhos.da_pasta(pasta)

    codigo = rr.executar(ctx, caminhos)

    assert codigo == 0
    assert [s.step for s in duplos.passos.chamadas] == ["extract"]
    assert not duplos.email.chamadas
    assert caminhos.estado_tmp.exists()
    assert _eventos(ctx)[-1]["outcome_reason"] == (
        "Processo finalizado (Idempotencia Extrator)."
    )


@pytest.mark.parametrize(
    "caso",
    [(6, True, 26, 1), (7, True, 27, 1), (1, False, 3, 3)],
)
def test_falha_de_extracao_aciona_alerta_e_devolve_codigo_canonico(
    pasta: Path,
    monkeypatch: pytest.MonkeyPatch,
    caso: tuple[int, bool, int, int],
) -> None:
    exit_code, nao_repetivel, codigo_esperado, tentativas = caso
    falha = hr.PythonStepResult(
        success=False,
        idempotent=False,
        non_retryable=nao_repetivel,
        output="",
        exit_code=exit_code,
        attempts=tentativas,
    )
    duplos = _instalar(monkeypatch, {"extract": falha})
    ctx = _contexto(pasta)

    codigo = rr.executar(ctx, rr.Caminhos.da_pasta(pasta))

    assert codigo == codigo_esperado
    assert [s.step for s in duplos.passos.chamadas] == ["extract"]
    assert duplos.alerta.chamadas == [
        {
            "task_name": "Receitas Emitidas",
            "ultimo_erro": f"Falha na extracao Oracle (PythonExit={exit_code}).",
            "tentativas": tentativas,
        }
    ]
    assert not duplos.email.chamadas


def test_conteudo_ja_entregue_suprime_email_e_confirma_estado(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entrega_previa = {
        "last_sent_hash": HASH_NOVO,
        "delivery_status": {
            "email": {"success": True, "sent_at": "01/01/2026 10:00:00"}
        },
    }
    (pasta / "delivery_state.json").write_text(
        json.dumps(entrega_previa), encoding="utf-8"
    )
    duplos = _instalar(monkeypatch, {"extract": EXTRACAO_OK, "transform": HTML_OK})
    ctx = _contexto(pasta)
    caminhos = rr.Caminhos.da_pasta(pasta)

    codigo = rr.executar(ctx, caminhos)

    assert codigo == 0
    assert not duplos.email.chamadas
    assert not caminhos.estado_tmp.exists()
    assert caminhos.estado.exists()
    assert any("Suprimindo" in m for m in _mensagens(ctx))


def test_falha_no_envio_do_email_nao_confirma_estado(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    duplos = _instalar(
        monkeypatch,
        {"extract": EXTRACAO_OK, "transform": HTML_OK},
        [False, False],
    )
    ctx = _contexto(pasta)
    caminhos = rr.Caminhos.da_pasta(pasta)

    codigo = rr.executar(ctx, caminhos)

    assert codigo == 1
    assert len(duplos.email.chamadas) == 2
    assert duplos.esperas == [15]
    assert caminhos.estado_tmp.exists()
    assert not caminhos.estado.exists()
    assert not caminhos.entrega.exists()
    eventos = _eventos(ctx)
    assert "commit" not in _passos_iniciados(eventos)
    assert eventos[-1]["level"] == "ERRO"
    assert eventos[-1]["outcome_reason"] == (
        "ERRO FATAL: Falha definitiva no envio do e-mail."
    )


def test_envio_recupera_na_segunda_tentativa_com_backoff_de_15_segundos(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    duplos = _instalar(
        monkeypatch,
        {"extract": EXTRACAO_OK, "transform": HTML_OK},
        [False, True],
    )
    ctx = _contexto(pasta)

    codigo = rr.executar(ctx, rr.Caminhos.da_pasta(pasta))

    assert codigo == 0
    assert len(duplos.email.chamadas) == 2
    assert duplos.esperas == [15]
    retries = [
        (e["attempt"], e["level"], e["step"])
        for e in _eventos(ctx)
        if e["event"] == "retry.attempt"
    ]
    assert retries == [
        (1, "WARN", "dispatch"),
        (2, "WARN", "dispatch"),
        (2, "INFO", "dispatch"),
    ]


def test_preflight_sem_oci_dll_aborta_com_9_antes_do_lock(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (pasta / "oracle_client" / "oci.dll").unlink()
    duplos = _instalar(monkeypatch, {"extract": EXTRACAO_OK})
    ctx = _contexto(pasta)

    codigo = rr.executar(ctx, rr.Caminhos.da_pasta(pasta))

    assert codigo == 9
    assert not duplos.passos.chamadas
    assert not _MutexFalso.chaves
    assert any("PRE-FLIGHT ERRO: oci.dll ausente" in m for m in _mensagens(ctx))


@pytest.mark.parametrize(
    ("sem_extract", "codigo_esperado"),
    [(False, 26), (True, 9)],
)
def test_modo_queue_com_worker_offline_devolve_26_so_se_o_resto_passa(
    pasta: Path,
    monkeypatch: pytest.MonkeyPatch,
    sem_extract: bool,
    codigo_esperado: int,
) -> None:
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "queue")
    monkeypatch.setenv("ORACLE_QUEUE_DIR", str(_pasta_fila(pasta, idade_s=600)))
    if sem_extract:
        (pasta / "extract_oracle.py").unlink()
    duplos = _instalar(monkeypatch, {"extract": EXTRACAO_OK})
    ctx = _contexto(pasta)

    codigo = rr.executar(ctx, rr.Caminhos.da_pasta(pasta))

    assert codigo == codigo_esperado
    assert not duplos.passos.chamadas
    assert any("Worker Offline" in m for m in _mensagens(ctx))


def test_modo_queue_com_worker_vivo_passa_o_preflight_e_segue_o_fluxo(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "queue")
    monkeypatch.setenv("ORACLE_QUEUE_DIR", str(_pasta_fila(pasta, idade_s=5)))
    duplos = _instalar(monkeypatch, {"extract": EXTRACAO_OK, "transform": HTML_OK})
    ctx = _contexto(pasta)

    codigo = rr.executar(ctx, rr.Caminhos.da_pasta(pasta))

    assert codigo == 0
    assert [s.step for s in duplos.passos.chamadas] == ["extract", "transform"]
    assert any("OK: Oracle Queue" in m and "worker 2.6.1" in m for m in _mensagens(ctx))


def test_excecao_fora_das_esperadas_encerra_com_erro_fatal_e_libera_o_lock(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Residual do runner: KeyError ou RuntimeError no meio do fluxo viram ERRO FATAL."""
    duplos = _instalar(
        monkeypatch, {"extract": EXTRACAO_OK, "transform": KeyError("NUMERO_OB")}
    )
    ctx = _contexto(pasta)

    codigo = rr.executar(ctx, rr.Caminhos.da_pasta(pasta))

    assert codigo == 1
    assert [s.step for s in duplos.passos.chamadas] == ["extract", "transform"]
    assert not duplos.email.chamadas
    assert _MutexFalso.chaves == ["RE-03"]
    assert _MutexFalso.saidas == ["RE-03"]
    eventos = _eventos(ctx)
    assert eventos[-1]["event"] == "execution.end"
    assert eventos[-1]["outcome_code"] == 1
    assert eventos[-1]["level"] == "ERRO"
    assert eventos[-1]["outcome_reason"].startswith("ERRO FATAL: ")
    assert "commit" not in _passos_iniciados(eventos)


def test_runtime_error_no_meio_do_fluxo_encerra_com_erro_fatal(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    duplos = _instalar(
        monkeypatch,
        {"extract": EXTRACAO_OK, "transform": RuntimeError("falha inesperada")},
    )
    ctx = _contexto(pasta)

    codigo = rr.executar(ctx, rr.Caminhos.da_pasta(pasta))

    assert codigo == 1
    assert [s.step for s in duplos.passos.chamadas] == ["extract", "transform"]
    assert _MutexFalso.saidas == ["RE-03"]
    assert _eventos(ctx)[-1]["outcome_reason"] == "ERRO FATAL: falha inesperada"


def test_excecao_no_preflight_encerra_com_erro_fatal_sem_pegar_o_lock(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def quebra(_ctx: Any) -> bool:
        raise RuntimeError("falha inesperada no pre-flight")

    monkeypatch.setattr(rr, "_checar_cliente_oracle", quebra)
    duplos = _instalar(monkeypatch, {"extract": EXTRACAO_OK})
    ctx = _contexto(pasta)

    codigo = rr.executar(ctx, rr.Caminhos.da_pasta(pasta))

    assert codigo == 1
    assert not duplos.passos.chamadas
    assert not _MutexFalso.chaves
    eventos = _eventos(ctx)
    assert eventos[-1]["event"] == "execution.end"
    assert eventos[-1]["outcome_reason"] == "ERRO FATAL: falha inesperada no pre-flight"


def test_dry_run_roda_extract_e_transform_mas_nao_envia_nem_confirma(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    duplos = _instalar(monkeypatch, {"extract": EXTRACAO_OK, "transform": HTML_OK})
    ctx = _contexto(pasta)
    caminhos = rr.Caminhos.da_pasta(pasta)

    codigo = rr.executar(ctx, caminhos, dry_run=True)

    assert codigo == 0
    assert [s.step for s in duplos.passos.chamadas] == ["extract", "transform"]
    assert not duplos.email.chamadas
    assert not duplos.alerta.chamadas
    assert caminhos.estado_tmp.exists()
    assert not caminhos.estado.exists()
    assert not caminhos.entrega.exists()
    mensagens = _mensagens(ctx)
    assert any(m.startswith("[DRY-RUN] E-mail nao enviado.") for m in mensagens)
    assert any("Commit de estado nao executado" in m for m in mensagens)


def test_dry_run_com_falha_de_extracao_nao_envia_alerta_real(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    falha = hr.PythonStepResult(
        success=False,
        idempotent=False,
        non_retryable=False,
        output="",
        exit_code=1,
        attempts=3,
    )
    duplos = _instalar(monkeypatch, {"extract": falha})
    ctx = _contexto(pasta)

    codigo = rr.executar(ctx, rr.Caminhos.da_pasta(pasta), dry_run=True)

    assert codigo == 3
    assert not duplos.alerta.chamadas
    assert any(
        m.startswith("[DRY-RUN] Alerta de falha nao enviado") for m in _mensagens(ctx)
    )


def test_falha_na_transformacao_vira_erro_fatal(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    falha = hr.PythonStepResult(
        success=False,
        idempotent=False,
        non_retryable=False,
        output="",
        exit_code=1,
        attempts=3,
    )
    duplos = _instalar(monkeypatch, {"extract": EXTRACAO_OK, "transform": falha})
    ctx = _contexto(pasta)

    codigo = rr.executar(ctx, rr.Caminhos.da_pasta(pasta))

    assert codigo == 1
    assert not duplos.email.chamadas
    assert _eventos(ctx)[-1]["outcome_reason"] == (
        "ERRO FATAL: Falha definitiva na geracao do HTML."
    )


def test_extracao_vazia_vira_erro_fatal_sem_transformar(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vazia = hr.PythonStepResult(
        success=True,
        idempotent=False,
        non_retryable=False,
        output="  \n",
        exit_code=0,
        attempts=1,
    )
    duplos = _instalar(monkeypatch, {"extract": vazia})
    ctx = _contexto(pasta)

    codigo = rr.executar(ctx, rr.Caminhos.da_pasta(pasta))

    assert codigo == 1
    assert [s.step for s in duplos.passos.chamadas] == ["extract"]
    assert _eventos(ctx)[-1]["outcome_reason"] == (
        "ERRO FATAL: Extracao retornou dados vazios."
    )


def test_lock_ocupado_aborta_com_erro_fatal_sem_executar_etapas(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    duplos = _instalar(monkeypatch, {"extract": EXTRACAO_OK})
    monkeypatch.setattr(hr, "AutomationMutex", _MutexBloqueado)
    ctx = _contexto(pasta)

    codigo = rr.executar(ctx, rr.Caminhos.da_pasta(pasta))

    assert codigo == 1
    assert not duplos.passos.chamadas
    assert _eventos(ctx)[-1]["outcome_reason"].startswith(
        "ERRO FATAL: CONCORRENCIA DETECTADA"
    )


def test_disco_abaixo_de_1_gb_reprova_o_preflight(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rr, "_espaco_livre_gb", lambda _caminho: 0.4)
    duplos = _instalar(monkeypatch, {"extract": EXTRACAO_OK})
    ctx = _contexto(pasta)

    codigo = rr.executar(ctx, rr.Caminhos.da_pasta(pasta))

    assert codigo == 9
    assert not duplos.passos.chamadas
    assert any("ERRO: Disco critico (0.4 GB)" in m for m in _mensagens(ctx))


@pytest.mark.parametrize(
    ("linha", "esperado"),
    [
        ("ORACLE_QUEUE_DIR=C:\\fila", ("ORACLE_QUEUE_DIR", "C:\\fila")),
        (
            "RE_EMAIL_TO=destino@teste.invalid   # comentario",
            ("RE_EMAIL_TO", "destino@teste.invalid"),
        ),
        ("  CHAVE = valor  ", ("CHAVE", "valor")),
        ("# so comentario", None),
        ("SEM_IGUAL", None),
        ("VAZIA=", None),
        ("=SEM_CHAVE", None),
    ],
)
def test_ler_linha_env_segue_convert_from_env_line(
    linha: str, esperado: tuple[str, str] | None
) -> None:
    assert rr._ler_linha_env(linha) == esperado  # pylint: disable=protected-access


def test_rotacao_remove_eventos_anteriores_a_retencao(tmp_path: Path) -> None:
    caminho = tmp_path / "ReceitasEmitidas.jsonl"
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


def test_caminhos_usam_os_nomes_de_arquivo_do_run_ps1(tmp_path: Path) -> None:
    caminhos = rr.Caminhos.da_pasta(tmp_path)

    assert caminhos.estado.name == "receitas_state.json"
    assert caminhos.estado_tmp.name == "receitas_state.json.tmp"
    assert caminhos.entrega.name == "delivery_state.json"
    assert caminhos.resultado.name == "re_result.json"
