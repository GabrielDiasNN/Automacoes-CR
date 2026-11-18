"""Testes unitarios do runner de Receitas Bloqueadas (Receitas Bloqueadas/run_receitas_bloqueadas.py).

Um teste por desfecho do run.ps1 antigo, com cada codigo de saida coberto: 0, 2, 3, 4, 9, 21,
22, 24, 25, 26 e 27 (mais o passthrough de codigos desconhecidos do WhatsApp). Sem Oracle,
sem Outlook, sem WhatsApp e sem rede: o passo Python (hr.run_python_step), a CLI de e-mail
(hr.executar_cli_outlook), o alerta (hr.send_failure_alert), o Send-WhatsApp.ps1
(hw.send_whatsapp), o mutex RB-01 (hr.AutomationMutex, so existe no Windows) e o disco sao
substituidos por dubles. Os arquivos da automacao vivem em tmp_path: nunca na pasta real.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import hub_runner as hr
import hub_whatsapp as hw
import pytest
from tests.carregadores_modulos import carregar_modulo_automacao

# Os dubles sao deliberadamente minimos (um metodo cada).
# pylint: disable=too-few-public-methods

RAIZ_REPO = Path(__file__).resolve().parents[2]
rb: Any = carregar_modulo_automacao(
    "run_receitas_bloqueadas",
    RAIZ_REPO / "Receitas Bloqueadas" / "run_receitas_bloqueadas.py",
)

DESTINO = "destino@teste.invalid"
TESTE = "teste@teste.invalid"
OCULTA = "oculta@teste.invalid"
HASH_NOVO = "HASH-NOVO"
HTML = "<html>relatorio</html>"
PLANILHA = "Receitas Bloqueadas.xlsx"
EXTRACAO_OK = hr.PythonStepResult(
    success=True,
    idempotent=False,
    non_retryable=False,
    output='[{"NUMERO_OB": "OB-1"}]\n',
    exit_code=0,
    attempts=1,
)
IDEMPOTENTE = hr.PythonStepResult(
    success=False,
    idempotent=True,
    non_retryable=False,
    output="",
    exit_code=2,
    attempts=1,
)


def _falha_python(exit_code: int, *, nao_repetivel: bool) -> hr.PythonStepResult:
    """Desfecho de uma extracao que falhou (definitiva, com ou sem retry)."""
    return hr.PythonStepResult(
        success=False,
        idempotent=False,
        non_retryable=nao_repetivel,
        output="",
        exit_code=exit_code,
        attempts=1,
    )


class _PassoFalso:
    """Dubles de hr.run_python_step: devolve o desfecho preparado ou levanta a excecao."""

    def __init__(
        self,
        resposta: hr.PythonStepResult | BaseException,
        efeito: Callable[[], None] | None = None,
    ) -> None:
        self.resposta = resposta
        self.efeito = efeito
        self.specs: list[Any] = []

    def __call__(self, _ctx: Any, spec: Any, **_kwargs: object) -> Any:
        self.specs.append(spec)
        if self.efeito is not None:
            self.efeito()
        if isinstance(self.resposta, BaseException):
            raise self.resposta
        return self.resposta


class _CliFalsa:
    """Dubles de hr.executar_cli_outlook: consome as respostas em ordem e guarda os argumentos."""

    def __init__(self, respostas: list[tuple[int, str] | BaseException]) -> None:
        self.respostas = list(respostas)
        self.argumentos: list[list[str]] = []

    def __call__(self, _script: Path, argumentos: list[str]) -> tuple[int, str]:
        self.argumentos.append(list(argumentos))
        resposta = self.respostas.pop(0) if self.respostas else (0, "")
        if isinstance(resposta, BaseException):
            raise resposta
        return resposta


class _WhatsAppFalso:
    """Dubles de hw.send_whatsapp: consome os exit codes em ordem e guarda as chamadas."""

    def __init__(self, respostas: list[int | BaseException]) -> None:
        self.respostas = list(respostas)
        self.chamadas: list[dict[str, Any]] = []

    def __call__(self, _ctx: Any, **kwargs: Any) -> int:
        self.chamadas.append(kwargs)
        resposta = self.respostas.pop(0) if self.respostas else 0
        if isinstance(resposta, BaseException):
            raise resposta
        return resposta


class _AlertaFalso:
    """Dubles de hr.send_failure_alert: registra o alerta de falha definitiva."""

    def __init__(self) -> None:
        self.chamadas: list[dict[str, Any]] = []

    def __call__(self, _ctx: Any, **kwargs: Any) -> bool:
        self.chamadas.append(kwargs)
        return True


class _MutexFalso:
    """Dubles do AutomationMutex: registra a chave adquirida e a liberada, e nunca bloqueia."""

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

    def __enter__(self) -> _MutexFalso:
        _MutexFalso.chaves.append(self.chave)
        return self

    def __exit__(self, _tipo: object, _valor: object, _rastro: object) -> None:
        _MutexFalso.saidas.append(self.chave)


class _MutexBloqueado:
    """Dubles de um mutex RB-01 ja ocupado por outra execucao."""

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
            "CONCORRENCIA DETECTADA: ja existe um processo com o lock RB-01."
        )

    def __exit__(self, _tipo: object, _valor: object, _rastro: object) -> None:
        return None


@dataclass
class _Duplos:
    """Conjunto de dubles instalado num teste, com as esperas registradas."""

    passo: _PassoFalso
    cli: _CliFalsa
    alerta: _AlertaFalso
    whatsapp: _WhatsAppFalso
    esperas: list[float]


@pytest.fixture(autouse=True)
def _ambiente_isolado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove variaveis do ambiente real que mudariam o pre-flight, os destinos ou o modo teste."""
    for chave in (
        "ORACLE_CONNECT_STRING",
        "ORACLE_QUEUE_DIR",
        "ORACLE_CLIENT_PATH",
        "ENVIRONMENT",
        "ORCHESTRATOR_TEST_MODE",
        "AUTOMACAO_TEST_EMAIL",
        "AUTOMACAO_ALERT_EMAIL",
        "RB_EMAIL_CC",
    ):
        monkeypatch.delenv(chave, raising=False)
    # O modo teste le AUTOMACAO_TEST_EMAIL do escopo User (registro): isola do registro real.
    monkeypatch.setattr(hr, "user_environment_variable", lambda _nome: "")
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "thick")
    monkeypatch.setenv("RB_EMAIL_TO", DESTINO)


@pytest.fixture(name="pasta")
def _pasta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Raiz falsa com lib/ (scripts vazios) e a pasta da automacao, com estado pendente."""
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "Send-WhatsApp.ps1").write_text("# falso\n", encoding="utf-8")
    (tmp_path / "lib" / "Invoke-OutlookEmail.ps1").write_text(
        "# falso\n", encoding="utf-8"
    )
    pasta = tmp_path / "Receitas Bloqueadas"
    pasta.mkdir()
    (pasta / "processar_receitas.py").write_text("# falso\n", encoding="utf-8")
    (pasta / "whatsapp-config.json").write_text("{}", encoding="utf-8")
    config = {
        "email": {
            "to": ["placeholder@teste.invalid"],
            "cc": ["copia@teste.invalid"],
            "bcc": [],
        }
    }
    (pasta / "receitas_config.json").write_text(json.dumps(config), encoding="utf-8")
    (pasta / "receitas_state.json.tmp").write_text(
        json.dumps({"last_hash": HASH_NOVO}), encoding="utf-8"
    )
    (pasta / "email_body.html").write_text(HTML, encoding="utf-8")
    monkeypatch.setattr(rb, "_espaco_livre_gb", lambda _caminho: 10.0)
    return pasta


def _escopo_user(monkeypatch: pytest.MonkeyPatch, valores: dict[str, str]) -> None:
    """Simula variaveis do escopo User do Windows (registro), lidas por hr.user_environment_variable."""
    monkeypatch.setattr(
        hr, "user_environment_variable", lambda nome: valores.get(nome, "")
    )


def _instalar(
    monkeypatch: pytest.MonkeyPatch,
    *,
    passo: _PassoFalso | None = None,
    cli: list[tuple[int, str] | BaseException] | None = None,
    whatsapp: list[int | BaseException] | None = None,
) -> _Duplos:
    """Substitui o passo Python, a CLI, o alerta, o WhatsApp, o mutex e a espera por dubles."""
    duplos = _Duplos(
        passo=passo or _PassoFalso(EXTRACAO_OK),
        cli=_CliFalsa(cli or []),
        alerta=_AlertaFalso(),
        whatsapp=_WhatsAppFalso(whatsapp or []),
        esperas=[],
    )
    monkeypatch.setattr(hr, "run_python_step", duplos.passo)
    monkeypatch.setattr(hr, "executar_cli_outlook", duplos.cli)
    monkeypatch.setattr(hr, "send_failure_alert", duplos.alerta)
    monkeypatch.setattr(hw, "send_whatsapp", duplos.whatsapp)
    monkeypatch.setattr(hr, "AutomationMutex", _MutexFalso)
    monkeypatch.setattr(rb, "_aguardar", duplos.esperas.append)
    _MutexFalso.chaves.clear()
    _MutexFalso.saidas.clear()
    return duplos


def _rodar(pasta: Path, *, dry_run: bool = False) -> tuple[int, hr.HubRunContext]:
    """Roda o runner na pasta falsa e devolve o exit code com o contexto (para ler o log)."""
    ctx = hr.create_run_context(
        hr.AutomationSpec(
            automacao="Receitas Bloqueadas",
            slug="ReceitasBloqueadas",
            trace_slug="rb",
            lock_key="RB-01",
            log_dir=pasta / "Logs",
            non_failure_codes=(0, 2, 22),
        ),
        exec_id="EXEC-TESTE-0001",
        telemetry=None,
        project_root=pasta.parent,
    )
    codigo = rb.executar(
        ctx, rb.Caminhos.da_pasta(pasta, pasta.parent), dry_run=dry_run
    )
    return codigo, ctx


def _eventos(ctx: hr.HubRunContext) -> list[dict[str, Any]]:
    """Eventos gravados no jsonl da execucao, na ordem de emissao."""
    conteudo = ctx.log_path.read_text(encoding="utf-8-sig")
    return [json.loads(linha) for linha in conteudo.splitlines() if linha.strip()]


def _mensagens(ctx: hr.HubRunContext) -> list[str]:
    """Mensagens de todos os eventos da execucao."""
    return [str(evento["message"]) for evento in _eventos(ctx)]


def _passos(ctx: hr.HubRunContext) -> list[str]:
    """Etapas abertas (step.start), na ordem."""
    return [e["step"] for e in _eventos(ctx) if e["event"] == "step.start"]


def _fim(ctx: hr.HubRunContext) -> dict[str, Any]:
    """Evento execution.end da execucao."""
    return next(e for e in _eventos(ctx) if e["event"] == "execution.end")


def _valor(argumentos: list[str], flag: str) -> str:
    """Valor do argumento que segue a flag na linha de comando da CLI."""
    return argumentos[argumentos.index(flag) + 1]


def _estado(pasta: Path) -> dict[str, Any]:
    """email_state.json gravado pela execucao."""
    dados: dict[str, Any] = json.loads(
        (pasta / "email_state.json").read_text(encoding="utf-8")
    )
    return dados


def _escrever_estado(pasta: Path, dados: dict[str, Any]) -> None:
    """Grava um email_state.json anterior, para cenarios de idempotencia."""
    (pasta / "email_state.json").write_text(json.dumps(dados), encoding="utf-8")


def _fila(pasta: Path, monkeypatch: pytest.MonkeyPatch, *, com_worker: bool) -> Path:
    """Pasta da fila no modo queue; com_worker grava um heartbeat fresco."""
    fila = pasta.parent / "fila"
    fila.mkdir(exist_ok=True)
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "queue")
    monkeypatch.setenv("ORACLE_QUEUE_DIR", str(fila))
    if com_worker:
        (fila / "_worker_heartbeat.json").write_text(
            json.dumps({"state": "idle", "version": "2.6.1"}), encoding="utf-8"
        )
    return fila


def test_fluxo_feliz_envia_email_e_whatsapp_e_confirma_o_estado(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 0: e-mail com Cc e anexo, WhatsApp em AUTO, estado salvo e commit feito."""
    duplos = _instalar(monkeypatch, cli=[(0, "")], whatsapp=[0])

    codigo, ctx = _rodar(pasta)

    assert codigo == 0
    assert duplos.passo.specs[0].step == "extract"
    assert duplos.passo.specs[0].max_attempts == 3
    assert duplos.passo.specs[0].backoff_seconds == (60, 120, 300)
    argumentos = duplos.cli.argumentos[0]
    assert _valor(argumentos, "-To") == DESTINO
    assert _valor(argumentos, "-Cc") == "copia@teste.invalid"
    assert _valor(argumentos, "-Attachments") == str(pasta / PLANILHA)
    assert "-Bcc" not in argumentos
    assert duplos.whatsapp.chamadas[0]["mode"] == "AUTO"
    assert duplos.whatsapp.chamadas[0]["config_path"] == pasta / "whatsapp-config.json"
    estado = _estado(pasta)
    assert estado["delivery_status"]["email"]["success"] is True
    assert estado["delivery_status"]["whatsapp"]["success"] is True
    assert estado["delivery_status"]["whatsapp"]["exit_code"] == 0
    assert (pasta / "receitas_state.json").exists()
    assert not (pasta / "receitas_state.json.tmp").exists()
    assert _MutexFalso.chaves == ["RB-01"]
    assert _MutexFalso.saidas == ["RB-01"]
    assert _fim(ctx)["outcome_code"] == 0


def test_idempotencia_do_python_sai_com_2_sem_notificar_e_grava_record_counts(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 2: processar_receitas.py sem alteracoes; nada e enviado e as contagens entram."""

    def gravar_contagens() -> None:
        (pasta / "rb_result.json").write_text(
            json.dumps({"record_counts": {"read": 3, "changed": 0, "new": 0}}),
            encoding="utf-8",
        )

    duplos = _instalar(
        monkeypatch, passo=_PassoFalso(IDEMPOTENTE, efeito=gravar_contagens)
    )

    codigo, ctx = _rodar(pasta)

    assert codigo == 2
    assert not duplos.cli.argumentos
    assert not duplos.whatsapp.chamadas
    assert not duplos.alerta.chamadas
    assert _fim(ctx)["record_counts"] == {"read": 3, "changed": 0, "new": 0}


@pytest.mark.parametrize("exit_code", [5])
def test_falha_nao_repetivel_do_python_sai_com_3_e_alerta_uma_vez(
    pasta: Path, monkeypatch: pytest.MonkeyPatch, exit_code: int
) -> None:
    """Desfecho 3 sem retry: exit 5 nao repete, o alerta sai com 1 tentativa e o codigo e 3."""
    duplos = _instalar(
        monkeypatch,
        passo=_PassoFalso(_falha_python(exit_code, nao_repetivel=True)),
    )

    codigo, ctx = _rodar(pasta)

    assert codigo == 3
    assert duplos.alerta.chamadas[0]["task_name"] == "Receitas Bloqueadas"
    assert duplos.alerta.chamadas[0]["tentativas"] == 1
    assert "PythonExit=5" in duplos.alerta.chamadas[0]["ultimo_erro"]
    assert not duplos.cli.argumentos
    assert _fim(ctx)["outcome_code"] == 3


def test_fila_oracle_offline_no_python_sai_com_26(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 26 na extracao: exit 6 do processar (worker da fila offline) vira 26."""
    duplos = _instalar(
        monkeypatch, passo=_PassoFalso(_falha_python(6, nao_repetivel=True))
    )

    codigo, _ctx = _rodar(pasta)

    assert codigo == 26
    assert duplos.alerta.chamadas[0]["tentativas"] == 1
    assert not duplos.cli.argumentos


def test_timeout_da_fila_oracle_no_python_sai_com_27(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 27 na extracao: exit 7 do processar (timeout da fila) vira 27."""
    _instalar(monkeypatch, passo=_PassoFalso(_falha_python(7, nao_repetivel=True)))

    codigo, _ctx = _rodar(pasta)

    assert codigo == 27


def test_falha_repetivel_do_python_sai_com_3_e_alerta_com_tres_tentativas(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 3 com retry esgotado: 3 tentativas com backoff ja aplicado pelo runner."""
    duplos = _instalar(
        monkeypatch, passo=_PassoFalso(_falha_python(1, nao_repetivel=False))
    )

    codigo, _ctx = _rodar(pasta)

    assert codigo == 3
    assert duplos.alerta.chamadas[0]["tentativas"] == 3


def test_python_que_nao_inicia_sai_com_4_sem_alerta(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 4: o run.ps1 pega a excecao de invocacao e sai com 4, sem alerta de falha."""
    duplos = _instalar(monkeypatch, passo=_PassoFalso(OSError("interpretador ausente")))

    codigo, ctx = _rodar(pasta)

    assert codigo == 4
    assert "Falha ao invocar script Python" in _fim(ctx)["outcome_reason"]
    assert not duplos.alerta.chamadas


def test_hash_igual_com_canais_entregues_suprime_e_promove_o_estado(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 0 por idempotencia de canal: mesmo hash, ambos entregues, nada e reenviado."""
    _escrever_estado(
        pasta,
        {
            "last_sent_hash": HASH_NOVO,
            "delivery_status": {
                "email": {"success": True, "sent_at": "01/01/2026 10:00:00"},
                "whatsapp": {"success": True, "sent_at": "01/01/2026 10:00:00"},
            },
        },
    )
    duplos = _instalar(monkeypatch)

    codigo, _ctx = _rodar(pasta)

    assert codigo == 0
    assert not duplos.cli.argumentos
    assert not duplos.whatsapp.chamadas
    assert (pasta / "receitas_state.json").exists()
    assert not (pasta / "receitas_state.json.tmp").exists()


def test_html_ausente_nao_despacha_nem_promove_o_estado(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem email_body.html o dispatch do run.ps1 nao roda: sai 0 e o .tmp segue pendente."""
    (pasta / "email_body.html").unlink()
    duplos = _instalar(monkeypatch)

    codigo, _ctx = _rodar(pasta)

    assert codigo == 0
    assert not duplos.cli.argumentos
    assert not duplos.whatsapp.chamadas
    assert (pasta / "receitas_state.json.tmp").exists()


def test_destinatario_vazio_pula_o_email_e_segue_para_o_whatsapp(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem 'to' configurado o e-mail e pulado com aviso; o WhatsApp continua e confirma o canal."""
    monkeypatch.delenv("RB_EMAIL_TO")
    config: dict[str, Any] = {"email": {"to": [], "cc": [], "bcc": []}}
    (pasta / "receitas_config.json").write_text(json.dumps(config), encoding="utf-8")
    duplos = _instalar(monkeypatch, whatsapp=[0])

    codigo, ctx = _rodar(pasta)

    assert codigo == 0
    assert not duplos.cli.argumentos
    assert len(duplos.whatsapp.chamadas) == 1
    assert any("Destinatarios 'to' nao configurados" in m for m in _mensagens(ctx))
    assert _estado(pasta)["delivery_status"]["email"]["success"] is True


def test_falha_do_email_sai_com_25_e_adia_o_commit(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 25: a CLI recusa o envio nas 2 tentativas; o WhatsApp segue e o commit fica adiado.

    A CLI atual nao declara -Cc (lib/Invoke-OutlookEmail.ps1), entao a recusa do PowerShell
    aparece no log do canal e o envio falha fechado, sem sair incompleto.
    """
    recusa = (1, "A parameter cannot be found that matches parameter name 'Cc'.")
    duplos = _instalar(monkeypatch, cli=[recusa, recusa], whatsapp=[0])

    codigo, ctx = _rodar(pasta)

    assert codigo == 25
    assert len(duplos.cli.argumentos) == 2
    assert duplos.esperas == [15]
    assert len(duplos.whatsapp.chamadas) == 1
    assert any("A parameter cannot be found" in m for m in _mensagens(ctx))
    assert (pasta / "receitas_state.json.tmp").exists()
    assert not (pasta / "receitas_state.json").exists()
    estado = _estado(pasta)
    assert estado["delivery_status"]["email"]["success"] is False
    assert estado["delivery_status"]["whatsapp"]["success"] is True


def test_email_na_segunda_tentativa_espera_15_segundos(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retry do e-mail: falha na 1a tentativa, sucesso na 2a, com backoff de 15 s."""
    duplos = _instalar(monkeypatch, cli=[(1, ""), (0, "")], whatsapp=[0])

    codigo, _ctx = _rodar(pasta)

    assert codigo == 0
    assert len(duplos.cli.argumentos) == 2
    assert duplos.esperas == [15]


def test_whatsapp_adiado_22_sai_com_22_e_adia_o_commit(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 22: WhatsApp adiado por lock ou cooldown; o e-mail ja entregue fica salvo."""
    _instalar(monkeypatch, cli=[(0, "")], whatsapp=[22])

    codigo, ctx = _rodar(pasta)

    assert codigo == 22
    assert (pasta / "receitas_state.json.tmp").exists()
    assert any("Commit de estado adiado: WhatsApp adiado" in m for m in _mensagens(ctx))
    assert _estado(pasta)["delivery_status"]["email"]["success"] is True


def test_whatsapp_com_lock_ativo_40_nao_adia_o_commit(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codigo 40 do WhatsApp (lock ativo) nao e falha de canal: o estado e promovido e sai 0."""
    _instalar(monkeypatch, cli=[(0, "")], whatsapp=[40])

    codigo, _ctx = _rodar(pasta)

    assert codigo == 0
    assert (pasta / "receitas_state.json").exists()


def test_whatsapp_desabilitado_23_vira_falha_24(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 24: envio WhatsApp desabilitado na configuracao (23) vira falha do canal."""
    _instalar(monkeypatch, cli=[(0, "")], whatsapp=[23])

    codigo, ctx = _rodar(pasta)

    assert codigo == 24
    assert (pasta / "receitas_state.json.tmp").exists()
    assert "envio WhatsApp desabilitado" in _fim(ctx)["outcome_reason"]


def test_whatsapp_pede_reautenticacao_e_sai_com_21(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 21: o WhatsApp exige novo QR Code; o codigo 21 segue como esta."""
    _instalar(monkeypatch, cli=[(0, "")], whatsapp=[21])

    codigo, _ctx = _rodar(pasta)

    assert codigo == 21


@pytest.mark.parametrize(
    ("codigo_whatsapp", "esperado"),
    [(2, 24), (-1, 24), (7, 7)],
)
def test_codigo_desconhecido_do_whatsapp_nao_vira_sucesso(
    pasta: Path,
    monkeypatch: pytest.MonkeyPatch,
    codigo_whatsapp: int,
    esperado: int,
) -> None:
    """Codigo fora da lista de sucesso e repassado; 0, 2 e negativos viram 24 (nunca verde)."""
    _instalar(monkeypatch, cli=[(0, "")], whatsapp=[codigo_whatsapp])

    codigo, _ctx = _rodar(pasta)

    assert codigo == esperado


def test_whatsapp_que_nao_inicia_sai_com_24(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 24 por excecao: o processo do WhatsApp nao inicia e o canal vira falha."""
    _instalar(monkeypatch, cli=[(0, "")], whatsapp=[OSError("powershell ausente")])

    codigo, ctx = _rodar(pasta)

    assert codigo == 24
    assert "O wrapper nao conseguiu completar" in _fim(ctx)["outcome_reason"]
    # Como no run.ps1, o exit_code fica so em memoria: o ultimo Save foi o do e-mail, antes.
    estado = _estado(pasta)
    assert estado["delivery_status"]["whatsapp"]["success"] is False
    assert estado["delivery_status"]["whatsapp"]["exit_code"] is None


def test_falha_do_email_nao_e_apagada_pelo_adiamento_do_whatsapp(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regra do run.ps1: o adiamento (22) so grava o codigo quando nao ha falha antes."""
    recusa = (1, "recusado")
    _instalar(monkeypatch, cli=[recusa, recusa], whatsapp=[22])

    codigo, _ctx = _rodar(pasta)

    assert codigo == 25


def test_reautenticacao_do_whatsapp_sobrescreve_falha_do_email(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regra do run.ps1: o codigo 21 sempre substitui a falha de e-mail registrada antes."""
    recusa = (1, "recusado")
    _instalar(monkeypatch, cli=[recusa, recusa], whatsapp=[21])

    codigo, _ctx = _rodar(pasta)

    assert codigo == 21


def test_excecao_fora_das_esperadas_no_envio_sai_com_4_e_libera_o_lock(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch externo: excecao no meio do fluxo sai com 4 e o mutex RB-01 e liberado."""
    _instalar(monkeypatch, cli=[RuntimeError("falha inesperada")])

    codigo, ctx = _rodar(pasta)

    assert codigo == 4
    assert "Falha critica na orquestracao" in _fim(ctx)["outcome_reason"]
    assert _MutexFalso.saidas == ["RB-01"]


def test_lock_ocupado_sai_com_4_sem_executar_as_etapas(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch externo com lock ocupado: nenhuma etapa do fluxo roda e a saida e 4."""
    duplos = _instalar(monkeypatch)
    monkeypatch.setattr(hr, "AutomationMutex", _MutexBloqueado)

    codigo, ctx = _rodar(pasta)

    assert codigo == 4
    assert not duplos.passo.specs
    assert "extract" not in _passos(ctx)


def test_preflight_com_path_ausente_sai_com_9_antes_do_lock(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 9: script do WhatsApp ausente reprova o pre-flight antes de tomar o lock."""
    duplos = _instalar(monkeypatch)
    (pasta.parent / "lib" / "Send-WhatsApp.ps1").unlink()

    codigo, ctx = _rodar(pasta)

    assert codigo == 9
    assert not duplos.passo.specs
    assert not _MutexFalso.chaves
    assert "FALHA NO PRE-FLIGHT CHECK" in _fim(ctx)["outcome_reason"]


def test_preflight_com_disco_critico_sai_com_9(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 9 por disco: menos de 1 GB livre reprova o pre-flight."""
    _instalar(monkeypatch)
    monkeypatch.setattr(rb, "_espaco_livre_gb", lambda _caminho: 0.5)

    codigo, _ctx = _rodar(pasta)

    assert codigo == 9


def test_worker_offline_na_fila_sai_com_26(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desfecho 26 no pre-flight: modo queue com worker offline e o resto do pre-flight ok."""
    _instalar(monkeypatch)
    _fila(pasta, monkeypatch, com_worker=False)

    codigo, _ctx = _rodar(pasta)

    assert codigo == 26


def test_worker_offline_com_path_ausente_sai_com_9(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Worker offline somado a falha deterministica sai com 9, porque reenfileirar repetiria a falha."""
    _instalar(monkeypatch)
    _fila(pasta, monkeypatch, com_worker=False)
    (pasta.parent / "lib" / "Send-WhatsApp.ps1").unlink()

    codigo, _ctx = _rodar(pasta)

    assert codigo == 9


def test_worker_vivo_na_fila_passa_o_preflight_e_segue_o_fluxo(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Modo queue com heartbeat fresco: o pre-flight passa e o lock e adquirido."""
    _instalar(monkeypatch, cli=[(0, "")], whatsapp=[0])
    _fila(pasta, monkeypatch, com_worker=True)

    codigo, ctx = _rodar(pasta)

    assert codigo == 0
    assert "lock" in _passos(ctx)


def test_dry_run_roda_o_extract_mas_nao_envia_nem_confirma(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dry-run: extract real, nenhum e-mail, WhatsApp, alerta ou commit; destinatario mascarado."""
    duplos = _instalar(monkeypatch)

    codigo, ctx = _rodar(pasta, dry_run=True)

    assert codigo == 0
    assert len(duplos.passo.specs) == 1
    assert not duplos.cli.argumentos
    assert not duplos.whatsapp.chamadas
    assert not duplos.alerta.chamadas
    assert not (pasta / "email_state.json").exists()
    assert (pasta / "receitas_state.json.tmp").exists()
    assert not (pasta / "receitas_state.json").exists()
    textos = _mensagens(ctx)
    assert any("[DRY-RUN] E-mail nao enviado" in m for m in textos)
    assert any("[DRY-RUN] Commit de estado nao executado" in m for m in textos)
    assert all(DESTINO not in m for m in textos)


def test_dry_run_com_falha_do_python_nao_envia_alerta(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dry-run com falha definitiva: o alerta e apenas logado, nunca enviado."""
    duplos = _instalar(
        monkeypatch, passo=_PassoFalso(_falha_python(1, nao_repetivel=False))
    )

    codigo, ctx = _rodar(pasta, dry_run=True)

    assert codigo == 3
    assert not duplos.alerta.chamadas
    assert any("[DRY-RUN] Alerta de falha nao enviado" in m for m in _mensagens(ctx))


def test_modo_teste_redireciona_o_to_sem_copia_e_mantem_a_oculta(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Modo teste (TRUE sem diferenciar caixa): To vai ao endereco de teste, sem Cc; Bcc segue."""
    monkeypatch.setenv("ORCHESTRATOR_TEST_MODE", "TRUE")
    _escopo_user(monkeypatch, {"AUTOMACAO_TEST_EMAIL": TESTE})
    config = {
        "email": {"to": ["x@teste.invalid"], "cc": ["y@teste.invalid"], "bcc": [OCULTA]}
    }
    (pasta / "receitas_config.json").write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.delenv("RB_EMAIL_TO")
    duplos = _instalar(monkeypatch, cli=[(0, "")], whatsapp=[0])

    codigo, _ctx = _rodar(pasta)

    assert codigo == 0
    argumentos = duplos.cli.argumentos[0]
    assert _valor(argumentos, "-To") == TESTE
    assert "-Cc" not in argumentos
    assert _valor(argumentos, "-Bcc") == OCULTA


def test_automacao_test_email_so_do_processo_nao_ativa_o_modo_teste(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Como o run.ps1: o .env (ambiente do processo) nao liga o modo teste; so o escopo User."""
    monkeypatch.setenv("AUTOMACAO_TEST_EMAIL", TESTE)
    duplos = _instalar(monkeypatch, cli=[(0, "")], whatsapp=[0])

    codigo, _ctx = _rodar(pasta)

    assert codigo == 0
    assert _valor(duplos.cli.argumentos[0], "-To") == DESTINO


def test_automacao_test_email_do_escopo_user_ativa_o_modo_teste(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem ORCHESTRATOR_TEST_MODE, o AUTOMACAO_TEST_EMAIL do escopo User liga o modo teste."""
    _escopo_user(monkeypatch, {"AUTOMACAO_TEST_EMAIL": TESTE})
    duplos = _instalar(monkeypatch, cli=[(0, "")], whatsapp=[0])

    codigo, _ctx = _rodar(pasta)

    assert codigo == 0
    assert _valor(duplos.cli.argumentos[0], "-To") == TESTE


def test_env_tem_prioridade_sobre_o_config_para_os_destinatarios(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RB_EMAIL_TO e RB_EMAIL_CC do .env vencem o receitas_config.json."""
    monkeypatch.setenv("RB_EMAIL_CC", "envcc@teste.invalid")
    duplos = _instalar(monkeypatch, cli=[(0, "")], whatsapp=[0])

    codigo, _ctx = _rodar(pasta)

    assert codigo == 0
    argumentos = duplos.cli.argumentos[0]
    assert _valor(argumentos, "-To") == DESTINO
    assert _valor(argumentos, "-Cc") == "envcc@teste.invalid"


def test_codigo_anterior_do_whatsapp_e_preservado_quando_o_canal_nao_roda(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """exit_code do WhatsApp gravado antes sobrevive quando so o e-mail e entregue agora."""
    _escrever_estado(
        pasta,
        {
            "last_sent_hash": HASH_NOVO,
            "delivery_status": {
                "email": {"success": False, "sent_at": None},
                "whatsapp": {
                    "success": True,
                    "sent_at": "01/01/2026 10:00:00",
                    "exit_code": 22,
                },
            },
        },
    )
    duplos = _instalar(monkeypatch, cli=[(0, "")])

    codigo, _ctx = _rodar(pasta)

    assert codigo == 0
    assert not duplos.whatsapp.chamadas
    assert _estado(pasta)["delivery_status"]["whatsapp"]["exit_code"] == 22


def test_housekeeping_remove_tmp_orfao_de_mais_de_um_dia(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Antes da execucao, .tmp_*.json com mais de 1 dia sai; o recente fica."""
    _instalar(monkeypatch)
    antigo = pasta / ".tmp_antigo.json"
    recente = pasta / ".tmp_recente.json"
    antigo.write_text("{}", encoding="utf-8")
    recente.write_text("{}", encoding="utf-8")
    instante = time.time() - 3 * 86400
    os.utime(antigo, (instante, instante))

    _rodar(pasta, dry_run=True)

    assert not antigo.exists()
    assert recente.exists()


def test_rotacao_do_log_mantem_quinze_dias(tmp_path: Path) -> None:
    """Invoke-LogRotation -KeepDays 15: eventos mais antigos saem do jsonl; os recentes ficam."""
    log = tmp_path / "ReceitasBloqueadas.jsonl"
    hoje = date.today()
    antigo = (hoje - timedelta(days=30)).isoformat()
    recente = hoje.isoformat()
    linhas = [
        json.dumps({"ts": f"{antigo}T10:00:00", "event": "log"}, separators=(",", ":")),
        json.dumps(
            {"ts": f"{recente}T10:00:00", "event": "log"}, separators=(",", ":")
        ),
    ]
    log.write_text("\n".join(linhas) + "\n", encoding="utf-8")

    rb._rotacionar_log(log)  # pylint: disable=protected-access

    restantes = log.read_text(encoding="utf-8-sig").splitlines()
    assert len(restantes) == 1
    assert recente in restantes[0]


def test_caminhos_usam_os_nomes_de_arquivo_do_run_ps1_antigo(tmp_path: Path) -> None:
    """Os nomes dos arquivos de estado, resultado e scripts sao os mesmos do run.ps1 antigo."""
    caminhos = rb.Caminhos.da_pasta(tmp_path / "RB", tmp_path)

    assert caminhos.processar.name == "processar_receitas.py"
    assert caminhos.html.name == "email_body.html"
    assert caminhos.planilha.name == PLANILHA
    assert caminhos.config_email.name == "receitas_config.json"
    assert caminhos.config_whatsapp.name == "whatsapp-config.json"
    assert caminhos.estado.name == "receitas_state.json"
    assert caminhos.estado_tmp.name == "receitas_state.json.tmp"
    assert caminhos.entrega.name == "email_state.json"
    assert caminhos.resultado.name == "rb_result.json"
    assert caminhos.send_whatsapp == tmp_path / "lib" / "Send-WhatsApp.ps1"
