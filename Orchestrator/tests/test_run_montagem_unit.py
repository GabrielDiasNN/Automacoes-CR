"""Testes unitarios do runner de Montagem de Terceirizados (Montagem de Terceirizados/run_montagem.py).

Um teste por desfecho do run.ps1 antigo (exit codes 0, 1, 3, 9, 25, 26 e 27, mais o caminho
de envio com copia, preview e telemetria). Sem Oracle, sem Outlook e sem rede. Os passos Python
(hr.run_python_step), a CLI de e-mail (hr.executar_cli_outlook, por onde passa a
hr.send_outlook_email real), o mutex MT-02 (hr.AutomationMutex, que so existe no Windows), o
check Oracle, o disco e o registro do escopo User sao substituidos por dubles. Os arquivos da
automacao vivem em tmp_path: nunca na pasta real Montagem de Terceirizados/ nem em Logs/ do repo.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import hub_runner as hr
import pytest
from tests.carregadores_modulos import carregar_modulo_automacao

# Os dublês de teste sao deliberadamente minimos (um metodo cada).
# pylint: disable=too-few-public-methods
# Os testes exercitam helpers privados do runner (_executor_envio, _mascarar...) de proposito.
# pylint: disable=protected-access

RAIZ_REPO = Path(__file__).resolve().parents[2]
MT_DIR = RAIZ_REPO / "Montagem de Terceirizados"
SHIM = MT_DIR / "run.ps1"
HELPER = MT_DIR.parent / "lib" / "Invoke-OutlookEmail.ps1"
rmt: Any = carregar_modulo_automacao("run_montagem", MT_DIR / "run_montagem.py")

DESTINO = "destino@teste.invalid"
CC = "copia@teste.invalid"
TESTE = "teste@teste.invalid"
OUTRO = "outro@teste.invalid"
ASSUNTO = "Acao necessaria: divergencias NF x OB - Montagem Terceirizados"
HTML = "<html>divergencias</html>"
REGISTROS: list[dict[str, Any]] = [{"NR_OB": "OB-1"}, {"NR_OB": "OB-2"}]
PAYLOAD: dict[str, Any] = {
    "subject": ASSUNTO,
    "html": HTML,
    "tipo_notificacao": "ERRO",
    "total_linhas": 12,
    "total_erros": 3,
    "total_pecas_nf_incorreta": 7,
    "novos": 2,
    "novos_pecas_nf_incorreta": 4,
    "corrigidos": 1,
    "corrigidos_pecas_nf_incorreta": 1,
    "permanentes": 0,
    "permanentes_pecas_nf_incorreta": 0,
}
CONTAGENS_PAYLOAD: dict[str, int] = {
    "read": 12,
    "errors": 3,
    "new": 2,
    "fixed": 1,
    "permanent": 0,
}


class _PassosFalsos:
    """Dublê de hr.run_python_step: devolve o desfecho da etapa, executa um efeito ou levanta."""

    def __init__(self, respostas: dict[str, Any]) -> None:
        self.respostas = respostas
        self.chamadas: list[Any] = []

    def __call__(self, ctx: Any, spec: Any, **_kwargs: object) -> Any:
        self.chamadas.append(spec)
        resposta = self.respostas[spec.step]
        if isinstance(resposta, BaseException):
            raise resposta
        if callable(resposta):
            return resposta(ctx)
        return resposta


def _valor(argumentos: list[str], nome: str) -> str:
    """Valor que segue um switch na lista de argumentos da CLI; vazio quando o switch nao existe."""
    if nome not in argumentos:
        return ""
    return argumentos[argumentos.index(nome) + 1]


@dataclass(frozen=True)
class _ChamadaCli:
    """Uma chamada da CLI de e-mail, como o dublê a recebeu."""

    script: Path
    argumentos: tuple[str, ...]
    para: str
    copia: str
    assunto: str
    html: str
    preview: bool


class _CliFalsa:
    """Dublê de hr.executar_cli_outlook: registra a chamada, com o corpo lido do arquivo temporario."""

    def __init__(self, respostas: list[int]) -> None:
        self.respostas = list(respostas)
        self.chamadas: list[_ChamadaCli] = []

    def __call__(self, script: Path, argumentos: list[str]) -> tuple[int, str]:
        html = Path(_valor(argumentos, "-HtmlBodyFile")).read_text(encoding="utf-8")
        self.chamadas.append(
            _ChamadaCli(
                script=script,
                argumentos=tuple(argumentos),
                para=_valor(argumentos, "-To"),
                copia=_valor(argumentos, "-Cc"),
                assunto=_valor(argumentos, "-Subject"),
                html=html,
                preview="-PreviewOnly" in argumentos,
            )
        )
        return self.respostas.pop(0), ""


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
    """Dublê de um mutex MT-02 ja ocupado por outra execucao."""

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
            "CONCORRENCIA DETECTADA: ja existe um processo com o lock MT-02."
        )

    def __exit__(self, _tipo: object, _valor: object, _rastro: object) -> None:
        return None


class _TelemetriaFalsa:
    """Dublê do cliente de telemetria: registra os status com que a execucao foi fechada."""

    def __init__(self) -> None:
        self.fechamentos: list[str] = []

    def end(self, exec_id: str, status: str, logs: str | None, trace_id: str) -> None:
        """Guarda o status do fechamento."""
        _ = (exec_id, logs, trace_id)
        self.fechamentos.append(status)


@dataclass
class _Duplos:
    """Conjunto de dublês instalado num teste."""

    passos: _PassosFalsos
    cli: _CliFalsa


@pytest.fixture(autouse=True)
def _ambiente_isolado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove variaveis do ambiente real e zera o escopo User (registro) para o teste."""
    for chave in (
        "ORACLE_CONNECT_STRING",
        "ORACLE_QUEUE_DIR",
        "ORACLE_CLIENT_PATH",
        "ORACLE_DRIVER_MODE",
        "ENVIRONMENT",
        "MT_EMAIL_TO",
        "MT_EMAIL_CC",
        "AUTOMACAO_TEST_EMAIL",
        "AUTOMACAO_ALERT_EMAIL",
        "ORCHESTRATOR_TEST_MODE",
        "HUB_TRACE_ID",
    ):
        monkeypatch.delenv(chave, raising=False)
    monkeypatch.setattr(rmt, "_variavel_usuario", lambda _nome: "")


def _escopo_user(monkeypatch: pytest.MonkeyPatch, valores: dict[str, str]) -> None:
    """Simula o escopo User do Windows (HKCU\\Environment) com os valores dados."""
    monkeypatch.setattr(rmt, "_variavel_usuario", lambda nome: valores.get(nome, ""))


def _gravar_config(pasta: Path, *, to: str, cc: str) -> None:
    """config.json de teste com os destinatarios oficiais."""
    config = {"email": {"to": to, "cc": cc}, "version": "1.0.0"}
    (pasta / "config.json").write_text(
        json.dumps(config, ensure_ascii=False), encoding="utf-8"
    )


@pytest.fixture(name="pasta")
def _pasta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pasta de automacao falsa: scripts vazios e config com destinatarios de teste."""
    monkeypatch.setattr(hr, "free_disk_gb", lambda _caminho: 10.0)
    (tmp_path / "extract_oracle.py").write_text("# script falso\n", encoding="utf-8")
    (tmp_path / "validate_and_generate_html.py").write_text(
        "# script falso\n", encoding="utf-8"
    )
    _gravar_config(tmp_path, to=DESTINO, cc="")
    return tmp_path


def _instalar(
    monkeypatch: pytest.MonkeyPatch,
    respostas: dict[str, Any],
    respostas_cli: list[int] | None = None,
) -> _Duplos:
    """Substitui os passos, a CLI de e-mail e o mutex pelos dublês."""
    duplos = _Duplos(
        passos=_PassosFalsos(respostas),
        cli=_CliFalsa(respostas_cli or [0]),
    )
    monkeypatch.setattr(hr, "run_python_step", duplos.passos)
    monkeypatch.setattr(hr, "executar_cli_outlook", duplos.cli)
    monkeypatch.setattr(hr, "AutomationMutex", _MutexFalso)
    _MutexFalso.chaves.clear()
    _MutexFalso.saidas.clear()
    return duplos


def _contexto(
    pasta: Path, *, exec_id: str = "EXEC-TESTE-0001", telemetry: Any = None
) -> hr.HubRunContext:
    """Contexto de log da execucao de teste: ExecId fixo, log em tmp."""
    return hr.create_run_context(
        hr.AutomationSpec(
            automacao="Montagem de Terceirizados",
            slug="Montagem_Terceirizados",
            trace_slug="mt",
            lock_key="MT-02",
            log_dir=pasta / "Logs",
            non_failure_codes=(0,),
        ),
        exec_id=exec_id,
        telemetry=telemetry,
        project_root=pasta,
    )


def _resultado(
    *,
    sucesso: bool = True,
    idempotente: bool = False,
    codigo: int = 0,
    saida: str = "",
) -> hr.PythonStepResult:
    """Desfecho de uma etapa Python, no formato de hr.run_python_step."""
    return hr.PythonStepResult(
        success=sucesso,
        idempotent=idempotente,
        non_retryable=False,
        output=saida,
        exit_code=codigo,
        attempts=1,
    )


def _extrai_com_dados(
    registros: list[dict[str, Any]],
) -> Callable[[Any], hr.PythonStepResult]:
    """Dublê do extract: grava o .data_<ExecId>.json como o extract_oracle.py e devolve exit 0."""

    def executar(ctx: Any) -> hr.PythonStepResult:
        texto = json.dumps(registros, ensure_ascii=False)
        Path(ctx.raiz, f".data_{ctx.exec_id}.json").write_text(texto, encoding="utf-8")
        return _resultado()

    return executar


def _valida_com_payload(
    payload: dict[str, Any] | None,
) -> Callable[[Any], hr.PythonStepResult]:
    """Dublê do validate: grava o payload e o cache .tmp, ou nada quando nao ha mudanca."""

    def executar(ctx: Any) -> hr.PythonStepResult:
        if payload is None:
            return _resultado()
        pasta = Path(ctx.raiz)
        texto = json.dumps(payload, ensure_ascii=False)
        (pasta / f".payload_{ctx.exec_id}.json").write_text(texto, encoding="utf-8")
        (pasta / ".cache_erros.json.tmp").write_text(
            json.dumps({"itens": {}}), encoding="utf-8"
        )
        return _resultado()

    return executar


def _feliz() -> dict[str, Any]:
    """Respostas dos passos de um ciclo com divergencias."""
    return {
        "extract": _extrai_com_dados(REGISTROS),
        "transform": _valida_com_payload(PAYLOAD),
    }


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


def _hash(texto: str) -> str:
    """SHA-256 em maiusculas do texto em UTF-8, como o run.ps1 grava no delivery_state."""
    return hashlib.sha256(texto.encode("utf-8")).hexdigest().upper()


def test_fluxo_feliz_envia_pelo_helper_confirma_cache_e_estado(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    duplos = _instalar(monkeypatch, _feliz(), [0])
    ctx = _contexto(pasta)
    caminhos = rmt.Caminhos.da_pasta(pasta)

    codigo = rmt.executar(ctx, caminhos)

    assert codigo == 0
    assert [s.step for s in duplos.passos.chamadas] == ["extract", "transform"]
    extracao = duplos.passos.chamadas[0]
    validacao = duplos.passos.chamadas[1]
    assert extracao.python_exe == sys.executable
    assert extracao.operation_name == "Extracao Oracle (extract_oracle.py)"
    assert extracao.max_attempts == 3
    assert extracao.backoff_seconds == (30, 60, 120)
    assert extracao.stdout_is_data is False
    assert validacao.max_attempts == 2
    assert validacao.backoff_seconds == (15, 30)
    assert validacao.input_data is None
    assert len(duplos.cli.chamadas) == 1
    envio = duplos.cli.chamadas[0]
    assert envio.script == rmt.HELPER_EMAIL
    assert envio.para == DESTINO
    assert envio.copia == ""
    assert envio.assunto == ASSUNTO
    assert envio.html == HTML
    assert envio.preview is False
    assert not caminhos.cache_tmp.exists()
    assert json.loads(caminhos.cache.read_text(encoding="utf-8")) == {"itens": {}}
    entrega = json.loads(caminhos.entrega.read_text(encoding="utf-8"))
    assert entrega["delivery_status"]["email"]["success"] is True
    assert entrega["last_sent_hash"] == _hash(json.dumps(PAYLOAD, ensure_ascii=False))
    assert _MutexFalso.chaves == ["MT-02"]
    assert _MutexFalso.saidas == ["MT-02"]
    eventos = _eventos(ctx)
    assert _passos_iniciados(eventos) == [
        "preflight",
        "lock",
        "extract",
        "transform",
        "dispatch",
    ]
    fim = eventos[-1]
    assert fim["event"] == "execution.end"
    assert fim["outcome_code"] == 0
    assert fim["level"] == "INFO"
    assert fim["record_counts"] == CONTAGENS_PAYLOAD
    assert {e["component"] for e in eventos} == {"ps_script"}
    assert not caminhos.payload("EXEC-TESTE-0001").exists()
    assert not caminhos.dados("EXEC-TESTE-0001").exists()


def test_sem_divergencia_encerra_com_zero_sem_email(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    duplos = _instalar(
        monkeypatch,
        {
            "extract": _extrai_com_dados(REGISTROS),
            "transform": _valida_com_payload(None),
        },
    )
    ctx = _contexto(pasta)

    codigo = rmt.executar(ctx, rmt.Caminhos.da_pasta(pasta))

    assert codigo == 0
    assert not duplos.cli.chamadas
    eventos = _eventos(ctx)
    assert _passos_iniciados(eventos) == ["preflight", "lock", "extract", "transform"]
    assert any("Nenhuma divergencia" in m for m in _mensagens(ctx))
    assert eventos[-1]["record_counts"] == {
        "read": 2,
        "errors": 0,
        "new": 0,
        "fixed": 0,
        "permanent": 0,
    }


def test_conteudo_ja_entregue_suprime_email_e_confirma_cache(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    texto = json.dumps(PAYLOAD, ensure_ascii=False)
    estado_anterior = {
        "last_sent_hash": _hash(texto),
        "delivery_status": {
            "email": {"success": True, "sent_at": "17/11/2026 10:00:00"}
        },
    }
    caminhos = rmt.Caminhos.da_pasta(pasta)
    caminhos.entrega.write_text(json.dumps(estado_anterior), encoding="utf-8")
    duplos = _instalar(monkeypatch, _feliz(), [])
    ctx = _contexto(pasta)

    codigo = rmt.executar(ctx, caminhos)

    assert codigo == 0
    assert not duplos.cli.chamadas
    assert json.loads(caminhos.cache.read_text(encoding="utf-8")) == {"itens": {}}
    assert any("Hash Match" in m for m in _mensagens(ctx))


def test_falha_no_envio_devolve_25_sem_confirmar_estado_nem_cache(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    duplos = _instalar(monkeypatch, _feliz(), [1])
    ctx = _contexto(pasta)
    caminhos = rmt.Caminhos.da_pasta(pasta)

    codigo = rmt.executar(ctx, caminhos)

    assert codigo == 25
    assert len(duplos.cli.chamadas) == 1
    assert not caminhos.cache.exists()
    assert not caminhos.cache_tmp.exists()
    assert not caminhos.entrega.exists()
    assert not caminhos.payload("EXEC-TESTE-0001").exists()
    assert any("O cache NAO sera atualizado" in m for m in _mensagens(ctx))
    fim = _eventos(ctx)[-1]
    assert fim["outcome_code"] == 25
    assert fim["level"] == "WARN"


@pytest.mark.parametrize(
    ("codigo_python", "codigo_saida"),
    [
        (1, 3),
        # Exit 2 do extract nao vira sucesso: o run.ps1 nao trata idempotencia (Success = false).
        (2, 3),
        # Exit 5 e nao repetivel, mas o codigo canonico continua o default 3.
        (5, 3),
        (6, 26),
        (7, 27),
    ],
)
def test_falha_definitiva_da_extracao_usa_o_codigo_canonico(
    pasta: Path,
    monkeypatch: pytest.MonkeyPatch,
    codigo_python: int,
    codigo_saida: int,
) -> None:
    resposta = _resultado(
        sucesso=False,
        idempotente=codigo_python == 2,
        codigo=codigo_python,
    )
    duplos = _instalar(monkeypatch, {"extract": resposta})
    ctx = _contexto(pasta)

    codigo = rmt.executar(ctx, rmt.Caminhos.da_pasta(pasta))

    assert codigo == codigo_saida
    assert [s.step for s in duplos.passos.chamadas] == ["extract"]
    assert not duplos.cli.chamadas
    fim = _eventos(ctx)[-1]
    assert fim["outcome_code"] == codigo_saida
    assert f"PythonExit={codigo_python}" in fim["outcome_reason"]


def test_extracao_sem_arquivo_de_dados_vira_erro_fatal(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    duplos = _instalar(monkeypatch, {"extract": _resultado()})
    ctx = _contexto(pasta)

    codigo = rmt.executar(ctx, rmt.Caminhos.da_pasta(pasta))

    assert codigo == 1
    assert [s.step for s in duplos.passos.chamadas] == ["extract"]
    fim = _eventos(ctx)[-1]
    assert fim["outcome_code"] == 1
    assert "arquivo de dados nao foi gerado" in fim["outcome_reason"]


def test_arquivo_de_dados_com_json_invalido_vira_erro_fatal(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def extrai_corrompido(ctx: Any) -> hr.PythonStepResult:
        Path(ctx.raiz, f".data_{ctx.exec_id}.json").write_text(
            "{nao e json", encoding="utf-8"
        )
        return _resultado()

    duplos = _instalar(monkeypatch, {"extract": extrai_corrompido})
    ctx = _contexto(pasta)

    codigo = rmt.executar(ctx, rmt.Caminhos.da_pasta(pasta))

    assert codigo == 1
    assert [s.step for s in duplos.passos.chamadas] == ["extract"]
    assert "contem JSON invalido" in _eventos(ctx)[-1]["outcome_reason"]


def test_falha_na_validacao_vira_erro_fatal_sem_enviar(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    duplos = _instalar(
        monkeypatch,
        {
            "extract": _extrai_com_dados(REGISTROS),
            "transform": _resultado(sucesso=False, codigo=1),
        },
    )
    ctx = _contexto(pasta)

    codigo = rmt.executar(ctx, rmt.Caminhos.da_pasta(pasta))

    assert codigo == 1
    assert [s.step for s in duplos.passos.chamadas] == ["extract", "transform"]
    assert not duplos.cli.chamadas
    assert (
        "Falha definitiva na validacao Python apos 2 tentativas."
        in _eventos(ctx)[-1]["outcome_reason"]
    )


def test_lock_ocupado_aborta_com_1_sem_executar_etapas(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    duplos = _instalar(monkeypatch, {})
    monkeypatch.setattr(hr, "AutomationMutex", _MutexBloqueado)
    ctx = _contexto(pasta)

    codigo = rmt.executar(ctx, rmt.Caminhos.da_pasta(pasta))

    assert codigo == 1
    assert not duplos.passos.chamadas
    eventos = _eventos(ctx)
    assert _passos_iniciados(eventos) == ["preflight", "lock"]
    assert "Falha ao adquirir lock global" in eventos[-1]["outcome_reason"]


def test_preflight_com_script_ausente_devolve_9_antes_do_lock(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (pasta / "validate_and_generate_html.py").unlink()
    duplos = _instalar(monkeypatch, {})
    ctx = _contexto(pasta)

    codigo = rmt.executar(ctx, rmt.Caminhos.da_pasta(pasta))

    assert codigo == 9
    assert not duplos.passos.chamadas
    assert not _MutexFalso.chaves
    eventos = _eventos(ctx)
    assert _passos_iniciados(eventos) == ["preflight"]
    assert eventos[-1]["outcome_code"] == 9
    assert eventos[-1]["outcome_reason"] == (
        "FALHA NO PRE-FLIGHT (Python/Oracle/Paths)."
    )
    assert any(
        "ERRO: Path inacessivel: validate_and_generate_html.py" in m
        for m in _mensagens(ctx)
    )


@pytest.mark.parametrize(
    ("script_ausente", "codigo_esperado"), [(False, 26), (True, 9)]
)
def test_modo_queue_com_worker_offline_devolve_26_so_se_o_resto_passa(
    pasta: Path,
    monkeypatch: pytest.MonkeyPatch,
    script_ausente: bool,
    codigo_esperado: int,
) -> None:
    status = hr.StatusFila(
        alive=False,
        reachable=True,
        queue_dir="fila-x",
        reason="heartbeat expirado ha 300s (limite 45s)",
    )
    oraculo = hr.OraclePreflight(
        modo="queue",
        linhas=(
            "ERRO: Oracle Queue (fila-x) Worker Offline (heartbeat expirado ha 300s (limite 45s))",
        ),
        status=status,
    )
    monkeypatch.setattr(hr, "oracle_preflight", lambda **_kwargs: oraculo)
    if script_ausente:
        (pasta / "extract_oracle.py").unlink()
    duplos = _instalar(monkeypatch, {})
    ctx = _contexto(pasta)

    codigo = rmt.executar(ctx, rmt.Caminhos.da_pasta(pasta))

    assert codigo == codigo_esperado
    assert not duplos.passos.chamadas
    assert _eventos(ctx)[-1]["outcome_code"] == codigo_esperado


def test_excecao_inesperada_no_fluxo_vira_erro_fatal_e_libera_o_lock(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _instalar(monkeypatch, {"extract": RuntimeError("falha inesperada")})
    ctx = _contexto(pasta)

    codigo = rmt.executar(ctx, rmt.Caminhos.da_pasta(pasta))

    assert codigo == 1
    assert _MutexFalso.saidas == ["MT-02"]
    fim = _eventos(ctx)[-1]
    assert fim["event"] == "execution.end"
    assert fim["outcome_code"] == 1
    assert fim["outcome_reason"] == "ERRO FATAL NA EXECUCAO NATIVA: falha inesperada"


def test_modo_teste_pelo_escopo_user_redireciona_sem_copia(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _gravar_config(pasta, to=DESTINO, cc=CC)
    _escopo_user(monkeypatch, {"AUTOMACAO_TEST_EMAIL": TESTE})
    duplos = _instalar(monkeypatch, _feliz(), [0])
    ctx = _contexto(pasta)

    codigo = rmt.executar(ctx, rmt.Caminhos.da_pasta(pasta))

    assert codigo == 0
    assert duplos.cli.chamadas[0].para == TESTE
    assert duplos.cli.chamadas[0].copia == ""
    # O log_masking da camada de eventos mascara o e-mail em qualquer mensagem; o envio
    # real recebe o endereco completo (asserto acima).
    assert any(
        m.startswith("MODO TESTE ATIVO: Redirecionando para t***@teste.invalid")
        for m in _mensagens(ctx)
    )


def test_variavel_so_no_ambiente_do_processo_nao_ativa_o_modo_teste(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O run.ps1 le AUTOMACAO_TEST_EMAIL do escopo User, nao do processo (que tambem carrega o .env)."""
    monkeypatch.setenv("AUTOMACAO_TEST_EMAIL", TESTE)
    duplos = _instalar(monkeypatch, _feliz(), [0])
    ctx = _contexto(pasta)

    codigo = rmt.executar(ctx, rmt.Caminhos.da_pasta(pasta))

    assert codigo == 0
    assert duplos.cli.chamadas[0].para == DESTINO
    assert all("MODO TESTE ATIVO" not in m for m in _mensagens(ctx))


def test_email_to_test_ativa_o_modo_teste_com_o_destinatario_dado(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _gravar_config(pasta, to=DESTINO, cc=CC)
    duplos = _instalar(monkeypatch, _feliz(), [0])
    ctx = _contexto(pasta)

    codigo = rmt.executar(ctx, rmt.Caminhos.da_pasta(pasta), email_to_test=OUTRO)

    assert codigo == 0
    assert duplos.cli.chamadas[0].para == OUTRO
    assert duplos.cli.chamadas[0].copia == ""


def test_orchestrator_test_mode_false_forca_o_modo_oficial(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _escopo_user(monkeypatch, {"AUTOMACAO_TEST_EMAIL": TESTE})
    monkeypatch.setenv("ORCHESTRATOR_TEST_MODE", "false")
    duplos = _instalar(monkeypatch, _feliz(), [0])
    ctx = _contexto(pasta)

    codigo = rmt.executar(ctx, rmt.Caminhos.da_pasta(pasta))

    assert codigo == 0
    assert duplos.cli.chamadas[0].para == DESTINO


def test_copia_do_config_e_enviada_com_cc_pelo_helper(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regressao: com copia configurada, o envio acontece e a copia vai em -Cc (como o run.ps1)."""
    _gravar_config(pasta, to=DESTINO, cc=CC)
    duplos = _instalar(monkeypatch, _feliz(), [0])
    ctx = _contexto(pasta)
    caminhos = rmt.Caminhos.da_pasta(pasta)

    codigo = rmt.executar(ctx, caminhos)

    assert codigo == 0
    assert len(duplos.cli.chamadas) == 1
    envio = duplos.cli.chamadas[0]
    assert envio.para == DESTINO
    assert envio.copia == CC
    assert envio.script == rmt.HELPER_EMAIL
    assert json.loads(caminhos.cache.read_text(encoding="utf-8")) == {"itens": {}}
    assert caminhos.entrega.exists()


def test_falha_do_envio_com_copia_devolve_25_depois_de_tentar(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _gravar_config(pasta, to=DESTINO, cc=CC)
    duplos = _instalar(monkeypatch, _feliz(), [1])
    ctx = _contexto(pasta)
    caminhos = rmt.Caminhos.da_pasta(pasta)

    codigo = rmt.executar(ctx, caminhos)

    assert codigo == 25
    assert len(duplos.cli.chamadas) == 1
    assert duplos.cli.chamadas[0].copia == CC
    assert not caminhos.cache.exists()
    assert not caminhos.entrega.exists()


def test_mt_email_to_do_env_tem_prioridade_sobre_o_config(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MT_EMAIL_TO", OUTRO)
    duplos = _instalar(monkeypatch, _feliz(), [0])
    ctx = _contexto(pasta)

    codigo = rmt.executar(ctx, rmt.Caminhos.da_pasta(pasta))

    assert codigo == 0
    assert duplos.cli.chamadas[0].para == OUTRO


def test_preview_passa_previewonly_e_grava_o_estado_como_o_run_ps1(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Com -EmailPreviewOnly, Send-OutlookEmail devolve $true sem enviar: o run.ps1 ainda grava o estado."""
    duplos = _instalar(monkeypatch, _feliz(), [0])
    ctx = _contexto(pasta)
    caminhos = rmt.Caminhos.da_pasta(pasta)

    codigo = rmt.executar(ctx, caminhos, email_preview_only=True)

    assert codigo == 0
    assert duplos.cli.chamadas[0].preview is True
    entrega = json.loads(caminhos.entrega.read_text(encoding="utf-8"))
    assert entrega["delivery_status"]["email"]["success"] is True


def test_dry_run_roda_extract_e_transform_mas_nao_envia_nem_confirma(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    duplos = _instalar(monkeypatch, _feliz(), [])
    ctx = _contexto(pasta)
    caminhos = rmt.Caminhos.da_pasta(pasta)

    codigo = rmt.executar(ctx, caminhos, dry_run=True)

    assert codigo == 0
    assert [s.step for s in duplos.passos.chamadas] == ["extract", "transform"]
    assert not duplos.cli.chamadas
    assert not caminhos.entrega.exists()
    assert not caminhos.cache.exists()
    assert not caminhos.cache_tmp.exists()
    mensagens = _mensagens(ctx)
    assert any(
        "[DRY-RUN] E-mail nao enviado" in m and "d***@teste.invalid" in m
        for m in mensagens
    )
    assert any("[DRY-RUN] Commit de estado nao executado" in m for m in mensagens)
    assert all(DESTINO not in m for m in mensagens)


def test_dry_run_com_copia_nao_chama_a_cli_e_mascara_a_copia(
    pasta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _gravar_config(pasta, to=DESTINO, cc=CC)
    duplos = _instalar(monkeypatch, _feliz(), [])
    ctx = _contexto(pasta)

    codigo = rmt.executar(ctx, rmt.Caminhos.da_pasta(pasta), dry_run=True)

    assert codigo == 0
    assert not duplos.cli.chamadas
    mensagens = _mensagens(ctx)
    assert any("copia=c***@teste.invalid" in m for m in mensagens)
    assert all(CC not in m for m in mensagens)


@pytest.mark.parametrize(
    ("resposta_cli", "codigo_esperado", "status_esperado"),
    [(0, 0, "SUCCESS"), (1, 25, "ERROR")],
)
def test_telemetria_fecha_uma_vez_com_o_status_do_desfecho(
    pasta: Path,
    monkeypatch: pytest.MonkeyPatch,
    resposta_cli: int,
    codigo_esperado: int,
    status_esperado: str,
) -> None:
    telemetria = _TelemetriaFalsa()
    _instalar(monkeypatch, _feliz(), [resposta_cli])
    ctx = _contexto(pasta, exec_id="TEL_9001", telemetry=telemetria)

    codigo = rmt.executar(ctx, rmt.Caminhos.da_pasta(pasta))

    assert codigo == codigo_esperado
    assert telemetria.fechamentos == [status_esperado]


def test_executor_envio_acrescenta_cc_e_previewonly_ao_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chamadas: list[tuple[Path, list[str]]] = []

    def cli_falsa(script: Path, argumentos: list[str]) -> tuple[int, str]:
        chamadas.append((script, argumentos))
        return 0, ""

    monkeypatch.setattr(hr, "executar_cli_outlook", cli_falsa)
    executor = rmt._executor_envio(CC, preview=True)  # pylint: disable=protected-access

    codigo, _saida = executor(
        Path("lib/Invoke-OutlookEmail.ps1"), ["-To", DESTINO, "-ExecId", "X"]
    )

    assert codigo == 0
    assert chamadas == [
        (
            rmt.HELPER_EMAIL,
            ["-To", DESTINO, "-ExecId", "X", "-Cc", CC, "-PreviewOnly"],
        )
    ]


def test_executor_envio_sem_copia_nem_preview_so_repassa_os_argumentos_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chamadas: list[list[str]] = []

    def cli_falsa(_script: Path, argumentos: list[str]) -> tuple[int, str]:
        chamadas.append(argumentos)
        return 1, "falhou"

    monkeypatch.setattr(hr, "executar_cli_outlook", cli_falsa)
    executor = rmt._executor_envio(
        "", preview=False
    )  # pylint: disable=protected-access

    codigo, saida = executor(Path("x.ps1"), ["-To", DESTINO])

    assert (codigo, saida) == (1, "falhou")
    assert chamadas == [["-To", DESTINO]]


@pytest.mark.parametrize(
    ("argumentos", "esperado"),
    [
        ([], {}),
        (["EXEC-1"], {"exec_id": "EXEC-1"}),
        (["EXEC-1", "--dry-run"], {"exec_id": "EXEC-1", "dry_run": True}),
        (
            [
                "--email-preview-only",
                "--email-to-test",
                OUTRO,
                "--email-cc-test",
                CC,
                "EXEC-2",
            ],
            {
                "exec_id": "EXEC-2",
                "email_preview_only": True,
                "email_to_test": OUTRO,
                "email_cc_test": CC,
            },
        ),
    ],
)
def test_interpretar_argumentos_aceita_os_switches_do_run_ps1(
    argumentos: list[str], esperado: dict[str, object]
) -> None:
    opcoes = rmt.interpretar_argumentos(argumentos)

    for campo, valor in esperado.items():
        assert getattr(opcoes, campo) == valor
    assert opcoes.exec_id == esperado.get("exec_id", "")
    assert opcoes.dry_run is esperado.get("dry_run", False)


def test_limpeza_remove_so_temporarios_orfaos_com_mais_de_um_dia(
    tmp_path: Path,
) -> None:
    antigo = tmp_path / ".data_ANTIGO.json"
    antigo.write_text("[]", encoding="utf-8")
    recente = tmp_path / ".payload_RECENTE.json"
    recente.write_text("{}", encoding="utf-8")
    anteontem = time.time() - 2 * 86400
    os.utime(antigo, (anteontem, anteontem))

    rmt._limpar_temporarios_orfaos(tmp_path)  # pylint: disable=protected-access

    assert not antigo.exists()
    assert recente.exists()


def test_hash_do_payload_e_sha256_em_maiusculas_do_texto_utf8() -> None:
    texto = '{"subject": "Acao"}'
    assert rmt._hash_payload(texto) == _hash(texto)  # pylint: disable=protected-access


def test_mascara_destinatarios_para_o_log_do_dry_run() -> None:
    mascara = rmt._mascarar  # pylint: disable=protected-access
    assert mascara("fulano@empresa.com; beltrana@empresa.com,x") == (
        "f***@empresa.com; b***@empresa.com; ***"
    )
    assert mascara("") == ""


def test_shim_run_ps1_delega_ao_runner_e_repassa_os_switches_de_email() -> None:
    conteudo = SHIM.read_bytes()
    assert conteudo.startswith(b"\xef\xbb\xbf"), "run.ps1 deve ser UTF-8 com BOM"
    fonte = conteudo.decode("utf-8-sig")
    assert "run_montagem.py" in fonte
    assert "Invoke-HubPythonRunner" in fonte
    assert "exit $exitCode" in fonte
    assert "Write-Log" not in fonte
    assert "Invoke-OraclePythonScript" not in fonte
    assert not re.search(r"catch\s*\{", fonte)
    assert not re.search(r"[A-Za-z]:\\", fonte), "run.ps1 nao pode ter caminho absoluto"
    for switch in ("--email-preview-only", "--email-to-test", "--email-cc-test"):
        assert switch in fonte, f"run.ps1 deve repassar {switch} ao runner"
    codigo = fonte.split("#>", 1)[1]
    linhas_de_codigo = [
        linha
        for linha in codigo.splitlines()
        if linha.strip() and not linha.strip().startswith("#")
    ]
    assert len(linhas_de_codigo) <= 40


def test_cli_de_email_da_lib_repassa_cc_bcc_anexos_e_previewonly() -> None:
    conteudo = HELPER.read_bytes()
    assert conteudo.startswith(b"\xef\xbb\xbf"), "helper deve ser UTF-8 com BOM"
    fonte = conteudo.decode("utf-8-sig")
    assert "Send-OutlookEmail -To $To -CC $Cc -BCC $Bcc" in fonte
    assert "-Attachments $anexos" in fonte
    assert "-PreviewOnly:$PreviewOnly" in fonte
    assert not re.search(r"[A-Za-z]:\\", fonte), "helper nao pode ter caminho absoluto"
    assert not re.search(r"catch\s*\{", fonte)


def test_excecoes_genericas_do_runner_tem_justificativa_residual() -> None:
    linhas = (MT_DIR / "run_montagem.py").read_text(encoding="utf-8").splitlines()
    genericas = [i for i, linha in enumerate(linhas) if "except Exception" in linha]
    assert genericas, "o runner deveria ter o catch-all de ERRO FATAL"
    for i in genericas:
        janela = "\n".join(linhas[max(0, i - 4) : i + 1])
        assert "Residual:" in janela
