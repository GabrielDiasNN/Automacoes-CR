"""Testes unitarios de lib/python/hub_runner.py.

Sem rede, sem Outlook e sem Oracle. Os processos filhos sao scripts Python
gravados em tmp_path; a telemetria e um dublê; o mutex usa chave aleatoria de
teste, nunca a chave de producao (RE-03). Nenhum teste grava em Logs/ do repo.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import hub_runner as hr
import pytest

RAIZ_REPO = Path(__file__).resolve().parents[2]
ENVELOPE_ESPERADO = (
    "ts",
    "level",
    "component",
    "event",
    "automation",
    "exec_id",
    "trace_id",
    "message",
)
windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="mutex global e do Windows"
)


@pytest.fixture(autouse=True)
def _sem_trace_herdado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove HUB_TRACE_ID do ambiente para o trace_id ser previsivel."""
    monkeypatch.delenv("HUB_TRACE_ID", raising=False)


class _TelemetriaFalsa:
    """Dublê da telemetria: grava as chamadas e levanta o erro configurado."""

    def __init__(
        self, exec_id: str | None = "TEL_42", erro: Exception | None = None
    ) -> None:
        self._exec_id = exec_id
        self._erro = erro
        self.starts: list[tuple[str, str]] = []
        self.ends: list[tuple[str, str, str | None, str]] = []

    def start(self, automation_name: str, trace_id: str) -> str | None:
        self.starts.append((automation_name, trace_id))
        if self._erro is not None:
            raise self._erro
        return self._exec_id

    def end(self, exec_id: str, status: str, logs: str | None, trace_id: str) -> None:
        self.ends.append((exec_id, status, logs, trace_id))
        if self._erro is not None:
            raise self._erro


class _RespostaFalsa:
    """Resposta minima para o urlopen falso (context manager com read)."""

    def __init__(self, corpo: bytes) -> None:
        self._corpo = corpo

    def read(self) -> bytes:
        return self._corpo

    def __enter__(self) -> _RespostaFalsa:
        return self

    def __exit__(self, *_: object) -> None:
        pass


def _ctx(
    tmp_path: Path,
    *,
    exec_id: str = "EXEC_TESTE",
    non_failure: tuple[int, ...] = (0,),
    telemetry: hr.TelemetryClient | None = None,
) -> hr.HubRunContext:
    spec = hr.AutomationSpec(
        automacao="Automacao Teste",
        slug="AutomacaoTeste",
        trace_slug="teste",
        non_failure_codes=non_failure,
    )
    return hr.create_run_context(
        spec, exec_id=exec_id, telemetry=telemetry, project_root=tmp_path
    )


def _eventos(ctx: hr.HubRunContext) -> list[dict[str, Any]]:
    """Le o jsonl da execucao como lista de eventos."""
    linhas = ctx.log_path.read_text(encoding="utf-8").splitlines()
    return [json.loads(linha) for linha in linhas if linha.strip()]


def _script(tmp_path: Path, nome: str, corpo: str) -> Path:
    caminho = tmp_path / nome
    caminho.write_text(corpo, encoding="utf-8")
    return caminho


def _passo(
    script: Path,
    *,
    max_attempts: int = 3,
    backoff: tuple[int, ...] = (0,),
    input_data: str | None = None,
    stdout_is_data: bool = False,
) -> hr.PythonStepSpec:
    return hr.PythonStepSpec(
        python_exe=sys.executable,
        script_path=str(script),
        operation_name="Operacao teste",
        max_attempts=max_attempts,
        backoff_seconds=backoff,
        input_data=input_data,
        stdout_is_data=stdout_is_data,
    )


def _carregar_validador() -> ModuleType:
    """Carrega Tools/log_event_validator.py por caminho (fonte do contrato)."""
    especificacao = importlib.util.spec_from_file_location(
        "log_event_validator", RAIZ_REPO / "Tools" / "log_event_validator.py"
    )
    assert especificacao is not None and especificacao.loader is not None
    modulo = importlib.util.module_from_spec(especificacao)
    # Registrar antes de executar: o @dataclass do validador consulta sys.modules.
    sys.modules[especificacao.name] = modulo
    especificacao.loader.exec_module(modulo)
    return modulo


# --- Envelope e eventos -----------------------------------------------------


def test_eventos_seguem_o_envelope_do_powershell(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    hr.execution_start(ctx, "INICIO - Automacao Teste")
    hr.start_step(ctx, "extract", mensagem="Extracao")
    hr.log(ctx, "linha informativa", step="extract")
    hr.complete_step(ctx, ok=True, mensagem="ok")
    hr.retry_attempt(
        ctx, "extract", attempt=2, max_attempts=3, nivel="WARN", mensagem="t 2/3"
    )
    hr.finish(ctx, 0)

    eventos = _eventos(ctx)
    assert [e["event"] for e in eventos] == [
        "execution.start",
        "step.start",
        "log",
        "step.end",
        "retry.attempt",
        "execution.end",
    ]
    for evento in eventos:
        assert set(ENVELOPE_ESPERADO) <= set(evento)
        assert evento["component"] == "ps_script"
        assert evento["automation"] == "Automacao Teste"
        assert evento["exec_id"] == "EXEC_TESTE"
        assert evento["trace_id"] == ctx.trace_id
    fim_etapa = eventos[3]
    assert fim_etapa["ok"] is True
    assert fim_etapa["step"] == "extract"
    assert isinstance(fim_etapa["duration_ms"], int) and fim_etapa["duration_ms"] >= 0
    assert (eventos[4]["attempt"], eventos[4]["max_attempts"]) == (2, 3)
    fim = eventos[5]
    assert fim["outcome_code"] == 0
    assert fim["level"] == "INFO"
    assert fim["outcome_reason"] == "FIM - Finalizado. ExitCode=0"
    assert fim["steps"] == [
        {"step": "extract", "ok": True, "duration_ms": fim_etapa["duration_ms"]}
    ]
    assert isinstance(fim["duration_ms"], int)
    assert ctx.log_path.read_bytes().count(b"\r\n") == len(eventos)


def test_eventos_passam_no_validador_do_schema(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    hr.execution_start(ctx)
    hr.start_step(ctx, "dispatch")
    hr.complete_step(ctx)
    hr.finish(ctx, 2)
    assert _carregar_validador().main([str(ctx.log_path)]) == 0


@pytest.mark.parametrize(
    ("codigo", "nivel"),
    [(0, "INFO"), (2, "INFO"), (22, "INFO"), (24, "WARN"), (25, "WARN"), (3, "ERRO")],
)
def test_nivel_do_execution_end_segue_o_exit_code(
    tmp_path: Path, codigo: int, nivel: str
) -> None:
    ctx = _ctx(tmp_path)
    hr.finish(ctx, codigo)
    assert _eventos(ctx)[-1]["level"] == nivel


def test_etapa_aberta_e_fechada_pelo_finish(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    hr.start_step(ctx, "transform")
    hr.finish(ctx, 3, "falha")
    eventos = _eventos(ctx)
    fim_etapa = next(e for e in eventos if e["event"] == "step.end")
    assert fim_etapa["ok"] is False
    assert fim_etapa["level"] == "WARN"
    assert "outcome_code=3" in fim_etapa["message"]
    fim = eventos[-1]
    assert fim["level"] == "ERRO"
    assert fim["outcome_reason"] == "falha"
    assert fim["steps"][0]["ok"] is False


def test_etapa_fora_do_enum_e_rejeitada(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        hr.start_step(_ctx(tmp_path), "etapa_inventada")


def test_record_counts_do_resultado_entram_no_execution_end(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    resultado = tmp_path / "re_result.json"
    resultado.write_text(
        json.dumps(
            {
                "record_counts": {
                    "read": 5,
                    "validated": "4",
                    "flag": True,
                    "texto": "abc",
                    "decimal": 2.5,
                    "inteiro_float": 2.0,
                }
            }
        ),
        encoding="utf-8",
    )
    esperado = {"read": 5, "validated": 4, "inteiro_float": 2}
    assert hr.read_record_counts(resultado) == esperado
    assert hr.read_record_counts(tmp_path / "ausente.json") is None
    hr.finish(ctx, 0, record_counts_path=resultado)
    assert _eventos(ctx)[-1]["record_counts"] == esperado


# --- Telemetria ----------------------------------------------------------------


def test_create_registra_telemetria_quando_exec_id_vazio(tmp_path: Path) -> None:
    telemetria = _TelemetriaFalsa(exec_id="TEL_42")
    spec = hr.AutomationSpec(
        automacao="Automacao Teste", slug="AutomacaoTeste", trace_slug="teste"
    )
    ctx = hr.create_run_context(spec, telemetry=telemetria, project_root=tmp_path)
    assert ctx.exec_id == "TEL_42"
    # Sem lock_key explicita, o mutex usa o exec_id, como o PowerShell.
    assert ctx.lock_key == "TEL_42"
    assert telemetria.starts == [("Automacao Teste", ctx.trace_id)]


def test_falha_no_start_cai_para_exec_id_local(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    telemetria = _TelemetriaFalsa(erro=hr.TelemetryError("offline"))
    ctx = _ctx(tmp_path, exec_id="", telemetry=telemetria)
    assert re.fullmatch(r"\d{8}_\d{6}_\d{4}", ctx.exec_id)
    assert "Falha ao registrar telemetria" in capsys.readouterr().err


def test_finish_fecha_telemetria_so_para_exec_id_tel(tmp_path: Path) -> None:
    telemetria = _TelemetriaFalsa()
    ctx = _ctx(tmp_path, exec_id="TEL_7", telemetry=telemetria)
    hr.log(ctx, "primeira linha")
    hr.finish(ctx, 0)
    exec_id, status, logs, trace_id = telemetria.ends[0]
    assert (exec_id, status, trace_id) == ("TEL_7", "SUCCESS", ctx.trace_id)
    assert logs is not None and "execution.end" in logs


def test_status_da_telemetria_respeita_non_failure_codes(tmp_path: Path) -> None:
    telemetria = _TelemetriaFalsa()
    ctx = _ctx(tmp_path, exec_id="TEL_8", non_failure=(0, 2), telemetry=telemetria)
    hr.finish(ctx, 2)
    hr.finish(ctx, 3)
    assert [status for _, status, _, _ in telemetria.ends] == ["SUCCESS", "ERROR"]


def test_exec_id_local_nao_chama_telemetria_no_end(tmp_path: Path) -> None:
    telemetria = _TelemetriaFalsa()
    ctx = _ctx(tmp_path, exec_id="EXEC_LOCAL", telemetry=telemetria)
    hr.finish(ctx, 0)
    assert not telemetria.ends


@pytest.mark.parametrize(
    "erro", [hr.TelemetryError("sem rede"), OSError("conexao recusada")]
)
def test_falha_de_telemetria_no_end_nao_propaga(
    tmp_path: Path, erro: Exception, capsys: pytest.CaptureFixture[str]
) -> None:
    ctx = _ctx(tmp_path, exec_id="TEL_9", telemetry=_TelemetriaFalsa(erro=erro))
    assert hr.finish(ctx, 0) == 0
    assert _eventos(ctx)[-1]["event"] == "execution.end"
    assert "Falha ao fechar telemetria" in capsys.readouterr().err


def test_cliente_http_monta_requisicao_de_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capturadas: list[urllib.request.Request] = []
    timeouts: list[float | None] = []

    def urlopen_falso(
        requisicao: urllib.request.Request, timeout: float | None = None
    ) -> _RespostaFalsa:
        capturadas.append(requisicao)
        timeouts.append(timeout)
        return _RespostaFalsa(b'{"exec_id": "TEL_99"}')

    monkeypatch.setattr(urllib.request, "urlopen", urlopen_falso)
    cliente = hr.HttpTelemetryClient("chave-de-teste")
    assert cliente.start("Automacao Teste", "trace-1") == "TEL_99"
    # Timeout curto por padrao: telemetria nao pode travar a execucao.
    assert timeouts == [3.0]
    requisicao = capturadas[0]
    assert requisicao.full_url == (
        "http://localhost:8000/api/executions/telemetry/start"
    )
    assert requisicao.get_method() == "POST"
    assert requisicao.get_header("X-api-key") == "chave-de-teste"
    assert requisicao.get_header("X-trace-id") == "trace-1"
    corpo = requisicao.data
    assert isinstance(corpo, bytes)
    assert json.loads(corpo) == {"automation_name": "Automacao Teste"}


def test_cliente_http_converte_erro_de_rede_em_telemetry_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def urlopen_recusado(
        _requisicao: urllib.request.Request, timeout: float | None = None
    ) -> _RespostaFalsa:
        raise urllib.error.URLError(f"conexao recusada (timeout={timeout})")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen_recusado)
    with pytest.raises(hr.TelemetryError):
        hr.HttpTelemetryClient("chave").start("A", "T")


def test_read_api_key_le_a_linha_do_env(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "OUTRA=1\nORCHESTRATOR_API_KEY=abc123  \n", encoding="utf-8"
    )
    assert hr.read_api_key(tmp_path) == "abc123"
    assert hr.read_api_key(tmp_path / "inexistente") == ""


def test_new_exec_id_segue_o_formato_do_powershell() -> None:
    assert re.fullmatch(r"\d{8}_\d{6}_\d{4}", hr.new_exec_id())


# --- Lock global -----------------------------------------------------------------


def test_nome_mutex_sanitiza_como_o_powershell() -> None:
    assert hr.nome_mutex("RE-03") == "Global\\AutomationHub_RE-03"
    assert hr.nome_mutex("A B/ç") == "Global\\AutomationHub_A_B__"


def _chave_de_teste() -> str:
    return f"TESTE-HUB-{secrets.token_hex(4)}"


@windows_only
def test_mutex_mesmo_nome_bloqueia_outra_thread_ate_o_prazo() -> None:
    chave = _chave_de_teste()
    resultado: list[object] = []

    def tentar() -> None:
        try:
            with hr.AutomationMutex(chave, timeout_ms=200):
                resultado.append("adquirido")
        except hr.LockTimeoutError as exc:
            resultado.append(exc)

    with hr.AutomationMutex(chave, timeout_ms=200):
        fio = threading.Thread(target=tentar)
        fio.start()
        fio.join()
    assert len(resultado) == 1
    assert isinstance(resultado[0], hr.LockTimeoutError)


@windows_only
def test_mutex_nomes_diferentes_nao_conflitam() -> None:
    chave_a = _chave_de_teste()
    chave_b = _chave_de_teste()
    resultado: list[str] = []

    def outra() -> None:
        with hr.AutomationMutex(chave_b, timeout_ms=200):
            resultado.append("ok")

    with hr.AutomationMutex(chave_a, timeout_ms=200):
        fio = threading.Thread(target=outra)
        fio.start()
        fio.join()
    assert resultado == ["ok"]


@windows_only
def test_mutex_abandonado_e_adquirido_com_aviso() -> None:
    chave = _chave_de_teste()
    avisos: list[str] = []

    def abandonar() -> None:
        mutex = hr.AutomationMutex(chave, timeout_ms=200)
        mutex.__enter__()  # pylint: disable=unnecessary-dunder-call
        # Sai sem __exit__: o Windows marca o mutex como abandonado.

    fio = threading.Thread(target=abandonar)
    fio.start()
    fio.join()
    with hr.AutomationMutex(chave, timeout_ms=2000, on_warning=avisos.append):
        pass
    assert len(avisos) == 1
    assert "abandonado" in avisos[0]


# --- run_python_step -------------------------------------------------------------


def test_passo_sucesso_captura_stdout_sem_repetir(tmp_path: Path) -> None:
    script = _script(tmp_path, "ok.py", "print('dados ok')\n")
    esperas: list[float] = []
    resultado = hr.run_python_step(_ctx(tmp_path), _passo(script), sleep=esperas.append)
    assert resultado.success is True
    assert (resultado.idempotent, resultado.non_retryable, resultado.exit_code) == (
        False,
        False,
        0,
    )
    assert resultado.output == "dados ok\n"
    assert resultado.attempts == 1
    assert not esperas


def test_idempotente_exit_2_nao_repete(tmp_path: Path) -> None:
    script = _script(tmp_path, "idem.py", "import sys\nsys.exit(2)\n")
    esperas: list[float] = []
    resultado = hr.run_python_step(_ctx(tmp_path), _passo(script), sleep=esperas.append)
    assert (resultado.success, resultado.idempotent, resultado.attempts) == (
        False,
        True,
        1,
    )
    assert not esperas


def test_falha_repete_ate_esgotar_com_backoff(tmp_path: Path) -> None:
    script = _script(tmp_path, "falha.py", "import sys\nsys.exit(1)\n")
    esperas: list[float] = []
    ctx = _ctx(tmp_path)
    resultado = hr.run_python_step(
        ctx, _passo(script, max_attempts=3, backoff=(1, 2)), sleep=esperas.append
    )
    assert (resultado.success, resultado.non_retryable, resultado.attempts) == (
        False,
        False,
        3,
    )
    assert resultado.exit_code == 1
    assert esperas == [1, 2]
    retries = [e for e in _eventos(ctx) if e["event"] == "retry.attempt"]
    assert retries[-1]["level"] == "ERRO"
    assert "todas as 3 tentativas falharam" in retries[-1]["message"]


def test_recupera_na_segunda_tentativa(tmp_path: Path) -> None:
    marca = tmp_path / "marca.txt"
    script = _script(
        tmp_path,
        "duas.py",
        "import pathlib, sys\n"
        f"marca = pathlib.Path({str(marca)!r})\n"
        "if marca.exists():\n"
        "    print('segunda ok')\n"
        "    sys.exit(0)\n"
        "marca.write_text('x', encoding='utf-8')\n"
        "sys.exit(1)\n",
    )
    esperas: list[float] = []
    ctx = _ctx(tmp_path)
    resultado = hr.run_python_step(
        ctx, _passo(script, backoff=(0,)), sleep=esperas.append
    )
    assert (resultado.success, resultado.attempts) == (True, 2)
    assert resultado.output == "segunda ok\n"
    assert esperas == [0]
    retries = [e for e in _eventos(ctx) if e["event"] == "retry.attempt"]
    assert any(
        e["level"] == "INFO" and "sucesso apos 2 tentativa(s)" in e["message"]
        for e in retries
    )


def test_nao_repetivel_exit_5_falha_sem_retry(tmp_path: Path) -> None:
    script = _script(tmp_path, "bloqueado.py", "import sys\nsys.exit(5)\n")
    esperas: list[float] = []
    ctx = _ctx(tmp_path)
    resultado = hr.run_python_step(ctx, _passo(script), sleep=esperas.append)
    assert (
        resultado.success,
        resultado.non_retryable,
        resultado.attempts,
        resultado.exit_code,
    ) == (False, True, 1, 5)
    assert not esperas
    ultimo = [e for e in _eventos(ctx) if e["event"] == "retry.attempt"][-1]
    assert ultimo["level"] == "ERRO"
    assert "nao-transitorio" in ultimo["message"]


def test_stdin_e_repassado_ao_filho(tmp_path: Path) -> None:
    script = _script(
        tmp_path, "eco.py", "import sys\nprint(sys.stdin.read().upper())\n"
    )
    resultado = hr.run_python_step(
        _ctx(tmp_path),
        _passo(script, input_data="dados de entrada"),
        sleep=lambda _: None,
    )
    assert resultado.output == "DADOS DE ENTRADA\n"


def test_stdout_de_dados_nao_vira_log_e_stderr_vira_log(tmp_path: Path) -> None:
    script = _script(
        tmp_path,
        "dados.py",
        "import sys\n"
        "print('PAYLOAD-SEM-LOG')\n"
        "print('[WARN] cuidado com o estoque', file=sys.stderr)\n"
        "print('[ERRO] falhou algo', file=sys.stderr)\n",
    )
    ctx = _ctx(tmp_path)
    resultado = hr.run_python_step(
        ctx, _passo(script, stdout_is_data=True), sleep=lambda _: None
    )
    assert resultado.output == "PAYLOAD-SEM-LOG\n"
    logs = [e for e in _eventos(ctx) if e["event"] == "log"]
    niveis = {e["message"]: e["level"] for e in logs}
    assert "PAYLOAD-SEM-LOG" not in niveis
    assert niveis["[WARN] cuidado com o estoque"] == "WARN"
    assert niveis["[ERRO] falhou algo"] == "ERRO"
    assert all(e["step"] == "extract" for e in logs)


def test_envelope_do_filho_e_encaminhado_sem_reembrulhar(tmp_path: Path) -> None:
    envelope = {
        "ts": "2026-11-18T10:00:00Z",
        "level": "INFO",
        "component": "python_domain",
        "event": "log",
        "automation": "Automacao Teste",
        "exec_id": "EXEC_FILHO",
        "trace_id": "t-filho",
        "message": "vindo do filho",
    }
    linha = json.dumps(envelope, ensure_ascii=False)
    script = _script(
        tmp_path,
        "envelope.py",
        f"import sys\nsys.stderr.write({linha!r} + '\\n')\n",
    )
    ctx = _ctx(tmp_path)
    hr.run_python_step(ctx, _passo(script), sleep=lambda _: None)
    do_filho = [e for e in _eventos(ctx) if e["message"] == "vindo do filho"]
    assert len(do_filho) == 1
    assert do_filho[0]["trace_id"] == "t-filho"
    assert do_filho[0]["component"] == "python_domain"


# --- Idempotencia de entrega --------------------------------------------------------


def test_le_delivery_state_gravado_pelo_powershell_com_bom(tmp_path: Path) -> None:
    caminho = tmp_path / "delivery_state.json"
    conteudo = json.dumps(
        {
            "last_sent_hash": "abc123",
            "delivery_status": {
                "email": {"success": True, "sent_at": "11/11/2026 09:00:00"}
            },
        }
    )
    caminho.write_bytes(b"\xef\xbb\xbf" + conteudo.encode("utf-8"))
    estado = hr.read_delivery_state(caminho, ["email", "whatsapp"])
    assert estado["last_sent_hash"] == "abc123"
    assert estado["delivery_status"]["email"] == {
        "success": True,
        "sent_at": "11/11/2026 09:00:00",
    }
    assert estado["delivery_status"]["whatsapp"] == {"success": False, "sent_at": None}
    assert hr.delivery_pending(estado, "email", "abc123") is False
    assert hr.delivery_pending(estado, "email", "novo") is True
    assert hr.update_delivery_state_hash(estado, "novo") is True
    assert hr.delivery_pending(estado, "email", "novo") is True


def test_grava_e_le_delivery_state_no_mesmo_formato(tmp_path: Path) -> None:
    caminho = tmp_path / "delivery_state.json"
    estado = hr.new_delivery_state(["email", "whatsapp"])
    assert hr.update_delivery_state_hash(estado, "h1") is True
    hr.set_delivery_success(estado, "email")
    hr.save_delivery_state(estado, caminho)
    assert not (tmp_path / "delivery_state.json.tmp").exists()
    assert not caminho.read_bytes().startswith(b"\xef\xbb\xbf")
    relido = hr.read_delivery_state(caminho, ["email", "whatsapp"])
    assert relido["last_sent_hash"] == "h1"
    email = relido["delivery_status"]["email"]
    assert email["success"] is True
    assert re.fullmatch(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}", email["sent_at"])
    assert relido["delivery_status"]["whatsapp"]["success"] is False
    assert hr.delivery_pending(relido, "email", "h1") is False


def test_delivery_state_corrompido_reinicia_com_aviso(tmp_path: Path) -> None:
    caminho = tmp_path / "delivery_state.json"
    caminho.write_text("{json truncado", encoding="utf-8")
    avisos: list[str] = []
    estado = hr.read_delivery_state(caminho, ["email"], on_warning=avisos.append)
    assert estado == hr.new_delivery_state(["email"])
    assert len(avisos) == 1
    assert "reiniciado" in avisos[0]


def test_hash_prefere_tmp_e_nao_cai_para_o_definitivo_se_ilegivel(
    tmp_path: Path,
) -> None:
    arquivo_tmp = tmp_path / "receitas_state.json.tmp"
    definitivo = tmp_path / "receitas_state.json"
    definitivo.write_text(json.dumps({"last_hash": "antigo"}), encoding="utf-8")
    arquivo_tmp.write_text(json.dumps({"last_hash": "novo"}), encoding="utf-8")
    assert hr.get_last_content_hash(arquivo_tmp, definitivo) == "novo"
    arquivo_tmp.unlink()
    assert hr.get_last_content_hash(arquivo_tmp, definitivo) == "antigo"
    arquivo_tmp.write_text("{ilegivel", encoding="utf-8")
    avisos: list[str] = []
    assert hr.get_last_content_hash(arquivo_tmp, definitivo, avisos.append) == ""
    assert len(avisos) == 1


def test_hash_vazio_nao_reseta_o_estado() -> None:
    estado = hr.new_delivery_state(["email"])
    estado["last_sent_hash"] = "h0"
    estado["delivery_status"]["email"]["success"] = True
    assert hr.update_delivery_state_hash(estado, "") is False
    assert estado["delivery_status"]["email"]["success"] is True
    assert hr.delivery_pending(estado, "sms") is True


# --- Mapeamento Oracle --------------------------------------------------------------


@pytest.mark.parametrize(("entrada", "esperado"), [(6, 26), (7, 27), (5, 3), (1, 3)])
def test_resolve_oracle_failure_exit_code(entrada: int, esperado: int) -> None:
    assert hr.resolve_oracle_failure_exit_code(entrada) == esperado


def test_resolve_oracle_failure_exit_code_usa_default_informado() -> None:
    assert hr.resolve_oracle_failure_exit_code(5, default_exit_code=9) == 9


# --- Email e alerta pela CLI ----------------------------------------------------------


def test_send_outlook_email_monta_argumentos_e_grava_corpo_utf8(
    tmp_path: Path,
) -> None:
    chamadas: list[tuple[Path, list[str], str]] = []

    def executor_falso(script: Path, argumentos: list[str]) -> tuple[int, str]:
        arquivo_corpo = Path(argumentos[argumentos.index("-HtmlBodyFile") + 1])
        chamadas.append((script, argumentos, arquivo_corpo.read_text(encoding="utf-8")))
        return 0, "[INFO] [ExecId:EXEC_TESTE] E-mail enviado com sucesso."

    ctx = _ctx(tmp_path)
    enviado = hr.send_outlook_email(
        ctx,
        to="destinatario@exemplo.invalid",
        subject="Assunto de teste",
        html_body="<p>Olá</p>",
        executor=executor_falso,
    )
    assert enviado is True
    script, argumentos, corpo = chamadas[0]
    assert script == tmp_path / "lib" / "Invoke-OutlookEmail.ps1"
    assert argumentos[argumentos.index("-To") + 1] == "destinatario@exemplo.invalid"
    assert argumentos[argumentos.index("-Subject") + 1] == "Assunto de teste"
    assert argumentos[argumentos.index("-ExecId") + 1] == "EXEC_TESTE"
    assert corpo == "<p>Olá</p>"
    assert not Path(argumentos[argumentos.index("-HtmlBodyFile") + 1]).exists()
    ultimo_log = [e for e in _eventos(ctx) if e["event"] == "log"][-1]
    assert ultimo_log["level"] == "INFO"
    assert ultimo_log["step"] == "dispatch"


def test_send_outlook_email_retorna_false_quando_cli_falha(tmp_path: Path) -> None:
    def executor_falho(_script: Path, _argumentos: list[str]) -> tuple[int, str]:
        return 1, "[ERRO] ERRO ao enviar e-mail: Outlook indisponivel"

    ctx = _ctx(tmp_path)
    enviado = hr.send_outlook_email(
        ctx,
        to="destinatario@exemplo.invalid",
        subject="s",
        html_body="<p/>",
        executor=executor_falho,
    )
    assert enviado is False
    assert [e for e in _eventos(ctx) if e["event"] == "log"][-1]["level"] == "ERRO"


def test_send_failure_alert_passa_o_switch_de_alerta(tmp_path: Path) -> None:
    recebidos: list[list[str]] = []

    def executor_falso(_script: Path, argumentos: list[str]) -> tuple[int, str]:
        recebidos.append(argumentos)
        return 0, ""

    enviado = hr.send_failure_alert(
        _ctx(tmp_path),
        task_name="Automacao Teste",
        ultimo_erro="Oracle caiu",
        tentativas=3,
        executor=executor_falso,
    )
    assert enviado is True
    argumentos = recebidos[0]
    assert argumentos[0] == "-Alerta"
    assert argumentos[argumentos.index("-Tentativas") + 1] == "3"
    assert argumentos[argumentos.index("-TaskName") + 1] == "Automacao Teste"


def test_executar_cli_trata_timeout_como_falha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run_expirado(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="powershell.exe", timeout=1)

    monkeypatch.setattr(subprocess, "run", run_expirado)
    codigo, saida = hr.executar_cli_outlook(tmp_path / "x.ps1", ["-Alerta"])
    assert codigo == 1
    assert "excedeu" in saida


def test_user_environment_variable_fora_do_windows_devolve_vazio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sem registro do Windows nao ha escopo User: o modo teste nunca liga por acidente."""
    monkeypatch.setattr(sys, "platform", "linux")
    assert hr.user_environment_variable("AUTOMACAO_TEST_EMAIL") == ""


@pytest.mark.skipif(sys.platform != "win32", reason="escopo User so existe no Windows")
def test_user_environment_variable_ignora_o_ambiente_do_processo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uma variavel so do processo (como as do .env) nao aparece no escopo User."""
    nome = "HUB_TESTE_SO_NO_PROCESSO_7F3A"
    monkeypatch.setenv(nome, "valor-do-processo")
    assert hr.user_environment_variable(nome) == ""


def test_ambiente_filho_injeta_hub_log_structured_e_remove_quando_stdout_is_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stdout_is_data=False injeta HUB_LOG_STRUCTURED=1; stdout_is_data=True remove da env."""
    script = _script(
        tmp_path,
        "env_dump.py",
        "import os, sys\n"
        "val = os.environ.get('HUB_LOG_STRUCTURED', 'AUSENTE')\n"
        "sys.stderr.write(f'STRUCT={val}\\n')\n",
    )
    ctx_log = _ctx(tmp_path)
    monkeypatch.delenv("HUB_LOG_STRUCTURED", raising=False)
    hr.run_python_step(
        ctx_log, _passo(script, stdout_is_data=False), sleep=lambda _: None
    )
    assert any(
        e.get("event") == "log" and e.get("message") == "STRUCT=1"
        for e in _eventos(ctx_log)
    )

    monkeypatch.setenv("HUB_LOG_STRUCTURED", "1")
    ctx_dados = _ctx(tmp_path)
    hr.run_python_step(
        ctx_dados, _passo(script, stdout_is_data=True), sleep=lambda _: None
    )
    assert any(
        e.get("event") == "log" and e.get("message") == "STRUCT=AUSENTE"
        for e in _eventos(ctx_dados)
    )


def test_nivel_da_linha_reconhece_warning_prefixado_e_alert() -> None:
    nivel = hr._nivel_da_linha  # pylint: disable=protected-access
    assert nivel("WARNING: rota lenta", "INFO") == "WARN"
    assert nivel("[ALERT] disco baixo", "INFO") == "WARN"


def test_run_python_script_executa_em_cwd_com_log_estruturado(tmp_path: Path) -> None:
    subdir = tmp_path / "sub"
    subdir.mkdir()
    script = _script(
        subdir,
        "fmt.py",
        "import os, pathlib\n"
        "print(f'CWD={pathlib.Path.cwd().name}|STRUCT={os.environ.get(\"HUB_LOG_STRUCTURED\")}')\n",
    )
    ctx = _ctx(tmp_path)
    codigo = hr.run_python_script(
        ctx, python_exe=sys.executable, script_path=script, step="transform", cwd=subdir
    )
    assert codigo == 0
    assert any(
        e.get("message") == "CWD=sub|STRUCT=1" and e.get("step") == "transform"
        for e in _eventos(ctx)
    )


def test_load_env_file_carrega_e_tolera_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HUB_TESTE_LOAD_ENV_93", raising=False)
    (tmp_path / ".env").write_text(
        "HUB_TESTE_LOAD_ENV_93=ok # nota\n", encoding="utf-8-sig"
    )
    assert hr.load_env_file(tmp_path) is None
    assert os.environ["HUB_TESTE_LOAD_ENV_93"] == "ok"

    pasta_como_arquivo = tmp_path / "nao_arquivo"
    pasta_como_arquivo.mkdir()
    (pasta_como_arquivo / ".env").mkdir()
    aviso = hr.load_env_file(pasta_como_arquivo)
    assert aviso is not None


def test_rotate_log_remove_expirados_e_grava_utf8_sem_bom(tmp_path: Path) -> None:
    caminho = tmp_path / "Exec.jsonl"
    antigo = (date.today() - timedelta(days=30)).isoformat()
    hoje = date.today().isoformat()
    caminho.write_text(
        f'{{"ts":"{antigo}T10:00:00Z","message":"antigo"}}\r\n'
        f'{{"timestamp":"{antigo}T11:00:00Z","message":"antigo_ts2"}}\r\n'
        f'{{"ts":"{hoje}T10:00:00Z","message":"recente_1"}}\r\n'
        f'{{"timestamp":"{hoje}T12:00:00Z","message":"recente_2"}}\r\n',
        encoding="utf-8-sig",
    )
    assert caminho.read_bytes().startswith(b"\xef\xbb\xbf")

    hr.rotate_log(caminho, dias=15)

    bruto = caminho.read_bytes()
    assert not bruto.startswith(b"\xef\xbb\xbf"), "rotate_log nao pode gravar BOM"
    mantidas = bruto.decode("utf-8").splitlines()
    assert len(mantidas) == 2
    assert "recente_1" in mantidas[0]
    assert "recente_2" in mantidas[1]


def test_rotate_log_limpa_bom_preexistente_mesmo_sem_linhas_expiradas(
    tmp_path: Path,
) -> None:
    caminho = tmp_path / "Bom.jsonl"
    hoje = date.today().isoformat()
    caminho.write_text(
        f'{{"ts":"{hoje}T10:00:00Z","message":"ok"}}\r\n',
        encoding="utf-8-sig",
    )
    assert caminho.read_bytes().startswith(b"\xef\xbb\xbf")

    hr.rotate_log(caminho)

    bruto = caminho.read_bytes()
    assert not bruto.startswith(b"\xef\xbb\xbf")
    assert len(bruto.decode("utf-8").splitlines()) == 1


def test_write_json_atomic_grava_utf8_sem_bom_e_sem_tmp_residual(
    tmp_path: Path,
) -> None:
    destino = tmp_path / "estado.json"
    hr.write_json_atomic(destino, {"ok": True, "texto": "ação"})

    bruto = destino.read_bytes()
    assert not bruto.startswith(b"\xef\xbb\xbf")
    assert json.loads(bruto.decode("utf-8")) == {"ok": True, "texto": "ação"}
    assert [p.name for p in tmp_path.iterdir()] == ["estado.json"]


def test_run_preflight_verifica_disco_paths_e_oracle(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    existente = tmp_path / "existe.py"
    existente.write_text("# ok\n", encoding="utf-8")
    oracle = hr.OraclePreflight(modo="auto", linhas=("OK: Oracle On",))

    assert hr.run_preflight(ctx, (existente,), oracle) is True
    assert hr.run_preflight(ctx, (existente, tmp_path / "falta.py"), oracle) is False
