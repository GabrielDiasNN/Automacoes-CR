"""Runner compartilhado do Hub de Automacoes (fundacao do item 3, parte 1).

Substitui, em Python, a orquestracao feita pelos ``run.ps1``. Reproduz os
contratos dos modulos PowerShell correspondentes:

* ``Lib-Logging.psm1``: telemetria (``Register-ExecutionTelemetry`` e
  ``Close-ExecutionTelemetry``), lock global (``Enter-AutomationLock``),
  caminho do log (``Get-AutomacaoLogPath``) e encerramento
  (``Exit-AutomationWithCode``).
* ``Lib-LogEvent.psm1``: eventos ``execution.start/end``, ``step.start/end``,
  ``retry.attempt`` e ``log``, anexados ao mesmo ``Logs/<slug>.jsonl``.
* ``Lib-Oracle.psm1``: ``run_python_step`` (equivale a
  ``Invoke-OraclePythonScript``) e ``resolve_oracle_failure_exit_code``.
* ``Lib-Idempotency.psm1``: ``delivery_state.json`` e ``*_state.json``, no mesmo
  formato JSON que o PowerShell le e grava.
* ``Lib-Email.psm1`` e ``Lib-Retry.psm1``: alcancados pela CLI
  ``lib/Invoke-OutlookEmail.ps1``.
* ``Lib-Oracle.psm1``, ``Lib-OracleEndpoint.psm1`` e o check Oracle de
  ``Lib-Logging.psm1``: pre-flight Oracle (``oracle_preflight``) e codigo de falha
  (``oracle_preflight_exit_code``), com a mesma decisao do PowerShell.

Os eventos saem de ``automation_log.emit_event`` (envelope de
``docs/log-event.schema.json``): cada um vai para ``stdout`` e e anexado ao
arquivo de log, como faz o ``Write-HubLogEvent``. A telemetria fica atras de
``TelemetryClient``; falha de telemetria nunca interrompe a execucao.
"""

from __future__ import annotations

import contextlib
import ctypes
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import IO, Any, Final, Protocol

import oracle_queue as fila
from automation_log import emit_event, resolve_trace_id

ORCHESTRATOR_URL: Final[str] = "http://localhost:8000"
"""Endereco do Orchestrator local, o mesmo fixo em Lib-Logging.psm1."""

COMPONENTE: Final[str] = "ps_script"
"""Componente do envelope: o runner substitui o run.ps1, entao emite ps_script."""

EXIT_IDEMPOTENTE: Final[int] = 2
EXIT_ORACLE_WORKER_OFFLINE: Final[int] = 26
EXIT_ORACLE_QUEUE_TIMEOUT: Final[int] = 27
NAO_REPETIVEIS_PADRAO: Final[tuple[int, ...]] = (5, 6, 7)
LOCK_TIMEOUT_MS_PADRAO: Final[int] = 5000
TIMEOUT_CLI_OUTLOOK_S: Final[float] = 300.0
RETENCAO_LOG_DIAS_PADRAO: Final[int] = 15
ESPACO_MINIMO_GB_PADRAO: Final[float] = 1.0
STEPS_VALIDOS: Final[frozenset[str]] = frozenset(
    {
        "preflight",
        "lock",
        "extract",
        "transform",
        "dispatch",
        "commit",
        "cleanup",
        "custom",
    }
)
TEXTO_FIM: Final[str] = "FIM - Finalizado. ExitCode={code}"
CAMPOS_ENVELOPE: Final[tuple[str, ...]] = (
    "ts",
    "level",
    "component",
    "event",
    "automation",
    "exec_id",
    "trace_id",
    "message",
)

_WAIT_OBJECT_0: Final[int] = 0x00000000
_WAIT_ABANDONED: Final[int] = 0x00000080
_WAIT_TIMEOUT: Final[int] = 0x00000102
_WAIT_FAILED: Final[int] = 0xFFFFFFFF
_NAO_SEGURO: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9_.-]")
_MARCADOR_NIVEL: Final[re.Pattern[str]] = re.compile(
    r"(?:\[(INFO|WARN|ERROR|ERRO|DEBUG|ALERT)\]|^\s*(WARNING):)", re.IGNORECASE
)
_INTEIRO: Final[re.Pattern[str]] = re.compile(r"^\s*-?\d+\s*$")
_CHAVE_API: Final[re.Pattern[str]] = re.compile(r"^ORCHESTRATOR_API_KEY=(.*)$")
_PADRAO_TS_LOG: Final[re.Pattern[str]] = re.compile(
    r'^\{"(?:ts|timestamp)":"(\d{4}-\d{2}-\d{2})T'
)
_EMISSAO = threading.Lock()


def _extrair_valor_env(bruto: str) -> str:
    """Remove comentario inline (` #...`) fora de aspas e aspas envolventes."""
    texto = bruto.strip()
    aspas: str | None = None
    escapado = False
    for idx, ch in enumerate(texto):
        if escapado:
            escapado = False
            continue
        if ch == "\\" and aspas == '"':
            escapado = True
            continue
        if ch in ('"', "'"):
            if aspas is None:
                aspas = ch
            elif aspas == ch:
                aspas = None
            continue
        if ch == "#" and aspas is None and idx > 0 and texto[idx - 1].isspace():
            texto = texto[:idx].rstrip()
            break
    if len(texto) >= 2 and texto[0] == texto[-1] and texto[0] in ('"', "'"):
        texto = texto[1:-1]
    return texto.strip()


def parse_env_line(linha: str) -> tuple[str, str] | None:
    """Par chave/valor de uma linha do .env, como ConvertFrom-EnvLine."""
    texto = linha.strip()
    if not texto or texto.startswith("#"):
        return None
    partes = texto.split("=", 1)
    if len(partes) != 2:
        return None
    chave = partes[0].strip()
    valor = _extrair_valor_env(partes[1])
    if not chave or not valor:
        return None
    return chave, valor


def load_env_file(raiz: Path) -> str | None:
    """Carrega ``raiz/.env`` no ambiente do processo (como Import-HubEnv).

    Retorna None se o arquivo nao existir ou for lido com sucesso; em erro de E/S,
    devolve a mensagem da excecao para o chamador decidir se loga ou falha.
    """
    caminho = raiz / ".env"
    try:
        if not caminho.exists():
            return None
        conteudo = caminho.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        return str(exc)
    for linha in conteudo.splitlines():
        par = parse_env_line(linha)
        if par is not None:
            os.environ[par[0]] = par[1]
    return None


class TelemetryError(RuntimeError):
    """Falha de comunicacao com a telemetria do Orchestrator. Nunca e fatal."""


class LockTimeoutError(RuntimeError):
    """Mutex global ocupado alem do prazo: outra execucao esta ativa."""


_FALHAS_TELEMETRIA: Final[tuple[type[Exception], ...]] = (TelemetryError, OSError)


class TelemetryClient(Protocol):
    """Contrato injetavel da telemetria. Implementacoes levantam TelemetryError."""

    def start(self, automation_name: str, trace_id: str) -> str | None:
        """Registra a execucao e devolve o exec_id, ou None se nao houver."""

    def end(self, exec_id: str, status: str, logs: str | None, trace_id: str) -> None:
        """Fecha a execucao com status SUCCESS ou ERROR."""


class HttpTelemetryClient:
    """Telemetria do Orchestrator por urllib, com os mesmos endpoints do PowerShell."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = ORCHESTRATOR_URL,
        timeout_s: float = 3.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    def start(self, automation_name: str, trace_id: str) -> str | None:
        """Chama telemetry/start e devolve o exec_id recebido."""
        resposta = self._post(
            "/api/executions/telemetry/start",
            {"automation_name": automation_name},
            trace_id,
        )
        exec_id = resposta.get("exec_id")
        return exec_id if isinstance(exec_id, str) and exec_id else None

    def end(self, exec_id: str, status: str, logs: str | None, trace_id: str) -> None:
        """Chama telemetry/end com o conteudo do log e o exit_code derivado."""
        corpo: dict[str, object] = {
            "status": status,
            "logs": logs,
            "exit_code": 0 if status == "SUCCESS" else 1,
        }
        self._post(f"/api/executions/telemetry/end/{exec_id}", corpo, trace_id)

    def _post(
        self, caminho: str, corpo: Mapping[str, object], trace_id: str
    ) -> dict[str, object]:
        requisicao = urllib.request.Request(
            self._base_url + caminho,
            data=json.dumps(corpo, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-API-Key": self._api_key,
                "X-Trace-Id": trace_id,
            },
        )
        try:
            with urllib.request.urlopen(  # nosec B310
                requisicao, timeout=self._timeout_s
            ) as resposta:
                bruto = resposta.read()
        except OSError as exc:
            raise TelemetryError(f"Orchestrator indisponivel: {exc}") from exc
        try:
            carga = json.loads(bruto.decode("utf-8") or "{}")
        except ValueError as exc:
            raise TelemetryError("resposta de telemetria fora do JSON") from exc
        return carga if isinstance(carga, dict) else {}


def user_environment_variable(nome: str) -> str:
    """Variavel do escopo User do Windows (HKCU\\Environment): GetEnvironmentVariable(nome, 'User').

    E o registro, nao o ambiente do processo. Os run.ps1 decidiam o modo teste por esse
    valor; o ambiente do processo tambem carrega o .env, entao um AUTOMACAO_TEST_EMAIL do
    .env nao pode ativar o teste. Fora do Windows, ou sem a chave, devolve vazio.
    """
    if sys.platform != "win32":
        return ""
    import winreg  # pylint: disable=import-outside-toplevel

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as chave:
            valor, tipo = winreg.QueryValueEx(chave, nome)
    except OSError:
        return ""
    texto = str(valor)
    return os.path.expandvars(texto) if tipo == winreg.REG_EXPAND_SZ else texto


def read_api_key(raiz: Path) -> str:
    """Le ORCHESTRATOR_API_KEY do .env da raiz (regra de Get-AutomacaoApiKey)."""
    try:
        linhas = (raiz / ".env").read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return ""
    for linha in linhas:
        casamento = _CHAVE_API.match(linha)
        if casamento is not None:
            return casamento.group(1).strip()
    return ""


def new_exec_id() -> str:
    """Id local no formato de New-ExecId: yyyyMMdd_HHmmss_NNNN."""
    sufixo = secrets.randbelow(9000) + 1000
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{sufixo}"


def nome_mutex(chave: str) -> str:
    """Nome do mutex global, com o mesmo saneamento de Enter-AutomationLock."""
    return "Global\\AutomationHub_" + _NAO_SEGURO.sub("_", chave)


def _carregar_kernel32() -> ctypes.CDLL:
    """Carrega kernel32 com as assinaturas usadas pelo mutex (somente Windows)."""
    if sys.platform != "win32":
        raise OSError("Mutex global do Hub so e suportado no Windows.")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    kernel32.ReleaseMutex.argtypes = [ctypes.c_void_p]
    kernel32.ReleaseMutex.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    return kernel32


class AutomationMutex:
    """Mutex nomeado do Windows, compativel com Enter-AutomationLock.

    Uso: ``with AutomationMutex("RE-03"): ...``. O nome e o mesmo do
    ``System.Threading.Mutex`` do PowerShell, entao os dois runtimes se excluem.
    Quando a posse anterior foi abandonada (processo morto), o lock e adquirido
    com aviso, como faz o PowerShell.
    """

    def __init__(
        self,
        chave: str,
        *,
        timeout_ms: int = LOCK_TIMEOUT_MS_PADRAO,
        on_warning: Callable[[str], None] | None = None,
    ) -> None:
        self.nome = nome_mutex(chave)
        self._timeout_ms = timeout_ms
        self._on_warning = on_warning
        self._kernel32: ctypes.CDLL | None = None
        self._handle: int | None = None

    def __enter__(self) -> AutomationMutex:
        kernel32 = _carregar_kernel32()
        handle = kernel32.CreateMutexW(None, False, self.nome)
        if not handle:
            raise OSError(ctypes.get_last_error(), f"CreateMutexW falhou: {self.nome}")
        resultado = int(kernel32.WaitForSingleObject(handle, self._timeout_ms))
        if resultado in (_WAIT_OBJECT_0, _WAIT_ABANDONED):
            if resultado == _WAIT_ABANDONED and self._on_warning is not None:
                self._on_warning(
                    "Mutex anterior foi abandonado. Reciclando lock "
                    f"(Mutex: {self.nome})."
                )
            self._kernel32 = kernel32
            self._handle = int(handle)
            return self
        kernel32.CloseHandle(handle)
        if resultado == _WAIT_TIMEOUT:
            raise LockTimeoutError(
                "CONCORRENCIA DETECTADA: ja existe um processo com o lock "
                f"{self.nome}. Abortando para evitar corrupcao."
            )
        raise OSError(
            ctypes.get_last_error(),
            f"WaitForSingleObject falhou: {self.nome} (resultado={resultado}).",
        )

    def __exit__(
        self,
        _tipo: type[BaseException] | None,
        _erro: BaseException | None,
        _rastreio: TracebackType | None,
    ) -> None:
        if self._kernel32 is None or self._handle is None:
            return
        # ReleaseMutex falha se a thread nao for a dona; CloseHandle solta a
        # referencia de qualquer forma.
        self._kernel32.ReleaseMutex(self._handle)
        self._kernel32.CloseHandle(self._handle)
        self._kernel32 = None
        self._handle = None


@dataclass(frozen=True)
class AutomationSpec:
    """Identidade fixa de uma automacao (as variaveis no topo de cada run.ps1)."""

    automacao: str
    slug: str
    trace_slug: str
    lock_key: str = ""
    log_dir: Path | None = None
    non_failure_codes: tuple[int, ...] = (0,)


@dataclass
class HubRunContext:  # pylint: disable=too-many-instance-attributes
    # Campos espelham o estado que o run.ps1 guarda em variaveis de escopo.
    """Estado de uma execucao: ids, log, telemetria e a timeline de etapas."""

    automacao: str
    exec_id: str
    trace_id: str
    log_path: Path
    lock_key: str
    raiz: Path
    non_failure_codes: tuple[int, ...]
    telemetry: TelemetryClient | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)
    step_ativo: str | None = None
    step_nome: str | None = None
    step_inicio: float | None = None
    inicio: float = field(default_factory=time.perf_counter)

    def ambiente(self) -> dict[str, str]:
        """Variaveis HUB_* que os filhos herdam (o run.ps1 as exporta no inicio)."""
        return {
            "HUB_AUTOMATION": self.automacao,
            "HUB_EXEC_ID": self.exec_id,
            "HUB_TRACE_ID": self.trace_id,
        }


def _raiz_padrao() -> Path:
    """Raiz do repositorio: lib/python/hub_runner.py fica dois niveis abaixo."""
    return Path(__file__).resolve().parents[2]


def _registrar_telemetria(
    telemetry: TelemetryClient | None, automacao: str, trace_id: str
) -> str:
    """Pede o exec_id ao Orchestrator; sem ele, cai para o id local."""
    if telemetry is not None:
        try:
            registrado = telemetry.start(automacao, trace_id)
        except _FALHAS_TELEMETRIA as exc:
            _avisar(f"Falha ao registrar telemetria (Orquestrador offline?): {exc}")
            registrado = None
        if registrado:
            return registrado
    return new_exec_id()


def _caminho_log(slug: str, log_dir: Path | None, raiz: Path) -> Path:
    """Caminho do jsonl da automacao; pasta relativa resolve a partir da raiz."""
    pasta = raiz / "Logs" if log_dir is None else log_dir
    if not pasta.is_absolute():
        pasta = raiz / pasta
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta / f"{slug}.jsonl"


def create_run_context(
    spec: AutomationSpec,
    *,
    exec_id: str = "",
    telemetry: TelemetryClient | None = None,
    project_root: Path | None = None,
) -> HubRunContext:
    """Cria o contexto. Sem exec_id, registra a telemetria (fallback local)."""
    raiz = _raiz_padrao() if project_root is None else project_root
    trace_id = resolve_trace_id(spec.trace_slug)
    exec_resolvido = exec_id.strip() or _registrar_telemetria(
        telemetry, spec.automacao, trace_id
    )
    return HubRunContext(
        automacao=spec.automacao,
        exec_id=exec_resolvido,
        trace_id=trace_id,
        log_path=_caminho_log(spec.slug, spec.log_dir, raiz),
        lock_key=spec.lock_key or exec_resolvido,
        raiz=raiz,
        non_failure_codes=spec.non_failure_codes,
        telemetry=telemetry,
    )


def _avisar(mensagem: str) -> None:
    """Aviso do proprio runner, no stderr (nao e canal de eventos)."""
    sys.stderr.write(f"[hub_runner] {mensagem}\n")


def _anexar_linha(caminho: Path, linha: str) -> None:
    """Anexa um evento ao jsonl em CRLF, como o Write-HubLogEvent do PowerShell."""
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with caminho.open("a", encoding="utf-8", newline="\r\n") as arquivo:
            arquivo.write(linha + "\n")
    except OSError as exc:
        _avisar(f"Falha ao persistir evento de log: {exc}")


def _ler_log(caminho: Path) -> str | None:
    """Conteudo do jsonl para a telemetria; None quando o arquivo nao existe."""
    try:
        return caminho.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None


def _validar_step(step: str) -> None:
    """Espelha o ValidateSet do enum de etapa (docs/logging-standard.md, decisao 11)."""
    if step not in STEPS_VALIDOS:
        raise ValueError(f"step invalido: {step!r}")


def _emitir(
    ctx: HubRunContext,
    evento: str,
    nivel: str,
    mensagem: str,
    campos: Mapping[str, Any] | None = None,
) -> None:
    """Emite um evento no envelope do runner e o anexa ao log da execucao."""
    dados = dict(campos or {})
    step = dados.pop("step", None)
    step_name = dados.pop("step_name", None)
    ambiente = os.environ.get("ENVIRONMENT", "").strip() or "PRD"
    if ambiente != "PRD":
        dados.setdefault("env", ambiente)
    with _EMISSAO:
        linha = emit_event(
            evento,
            nivel,
            mensagem,
            automation=ctx.automacao,
            exec_id=ctx.exec_id,
            trace_id=ctx.trace_id,
            step=step,
            step_name=step_name,
            extra=dados or None,
            component=COMPONENTE,
        )
        _anexar_linha(ctx.log_path, linha)


def _nivel_do_desfecho(code: int) -> str:
    """Nivel do execution.end pelo exit code (docs/logging-standard.md, secao 5)."""
    if code in (0, 2, 22):
        return "INFO"
    if code in (24, 25):
        return "WARN"
    return "ERRO"


def _ms_desde(inicio: float | None) -> int:
    """Milissegundos decorridos desde um instante de time.perf_counter()."""
    if inicio is None:
        return 0
    return int((time.perf_counter() - inicio) * 1000)


def execution_start(ctx: HubRunContext, mensagem: str = "Inicio da execucao") -> None:
    """Emite execution.start e zera a timeline (equivale a Write-HubExecutionStart)."""
    ctx.steps.clear()
    _emitir(ctx, "execution.start", "INFO", mensagem)


def log(
    ctx: HubRunContext, mensagem: str, nivel: str = "INFO", *, step: str | None = None
) -> None:
    """Emite um evento log (equivale a Write-HubLogEvent -Event log)."""
    _emitir(ctx, "log", nivel, mensagem, {"step": step})


def start_step(
    ctx: HubRunContext,
    step: str,
    *,
    step_name: str | None = None,
    mensagem: str = "",
) -> None:
    """Abre uma etapa e emite step.start (equivale a Start-HubStep)."""
    _validar_step(step)
    ctx.step_ativo = step
    ctx.step_nome = step_name
    ctx.step_inicio = time.perf_counter()
    _emitir(ctx, "step.start", "INFO", mensagem, {"step": step, "step_name": step_name})


def complete_step(ctx: HubRunContext, *, ok: bool = True, mensagem: str = "") -> None:
    """Fecha a etapa aberta, se houver (equivale a Complete-HubStep)."""
    if ctx.step_ativo is None:
        return
    passo = ctx.step_ativo
    nome = ctx.step_nome
    duracao = _ms_desde(ctx.step_inicio)
    entrada: dict[str, Any] = {"step": passo, "ok": ok, "duration_ms": duracao}
    if nome:
        entrada["step_name"] = nome
    ctx.steps.append(entrada)
    _emitir(
        ctx,
        "step.end",
        "INFO" if ok else "WARN",
        mensagem,
        {"step": passo, "step_name": nome, "ok": ok, "duration_ms": duracao},
    )
    ctx.step_ativo = None
    ctx.step_nome = None
    ctx.step_inicio = None


# O evento retry.attempt tem seis atributos (step, tentativa, total, nivel, texto,
# contexto) e espelha Write-HubRetryAttempt. Agrupar em objeto so esconderia isso.
# pylint: disable=too-many-arguments
def retry_attempt(
    ctx: HubRunContext,
    step: str,
    *,
    attempt: int,
    max_attempts: int,
    nivel: str = "WARN",
    mensagem: str = "",
) -> None:
    """Emite retry.attempt com attempt e max_attempts (Write-HubRetryAttempt)."""
    _validar_step(step)
    _emitir(
        ctx,
        "retry.attempt",
        nivel,
        mensagem,
        {"step": step, "attempt": attempt, "max_attempts": max_attempts},
    )


# pylint: enable=too-many-arguments


def finish(
    ctx: HubRunContext,
    code: int,
    msg: str = "",
    record_counts_path: Path | None = None,
) -> int:
    """Encerra a execucao: execution.end e telemetria. Devolve o exit code.

    Equivale a Exit-AutomationWithCode. Quem chama faz ``sys.exit(finish(...))``.
    Uma etapa ainda aberta e fechada antes, como em Write-HubExecutionEnd.
    """
    if ctx.step_ativo is not None:
        complete_step(
            ctx,
            ok=_nivel_do_desfecho(code) == "INFO",
            mensagem=f"Etapa encerrada pelo fim da execucao (outcome_code={code}).",
        )
    contagens = (
        read_record_counts(record_counts_path)
        if record_counts_path is not None
        else None
    )
    campos: dict[str, Any] = {
        "outcome_code": code,
        "outcome_reason": msg or TEXTO_FIM.format(code=code),
        "duration_ms": _ms_desde(ctx.inicio),
        "steps": list(ctx.steps),
    }
    if contagens:
        campos["record_counts"] = contagens
    _emitir(
        ctx,
        "execution.end",
        _nivel_do_desfecho(code),
        TEXTO_FIM.format(code=code),
        campos,
    )
    if ctx.exec_id.startswith("TEL_"):
        sucesso = code in ctx.non_failure_codes
        _fechar_telemetria(ctx, "SUCCESS" if sucesso else "ERROR")
    return code


def _fechar_telemetria(ctx: HubRunContext, status: str) -> None:
    """Fecha a telemetria; so vale para exec_id TEL_ (guarda de Close-ExecutionTelemetry)."""
    if ctx.telemetry is None:
        return
    try:
        ctx.telemetry.end(ctx.exec_id, status, _ler_log(ctx.log_path), ctx.trace_id)
    except _FALHAS_TELEMETRIA as exc:
        _avisar(f"Falha ao fechar telemetria: {exc}")


def _como_inteiro(valor: object) -> int | None:
    """Converte um contador de record_counts; bool e texto nao numerico viram None."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    if isinstance(valor, str) and _INTEIRO.match(valor):
        return int(valor)
    return None


def read_record_counts(caminho: Path) -> dict[str, int] | None:
    """Le o bloco record_counts de um *_result.json (equivale a Get-HubRecordCounts)."""
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(dados, dict):
        return None
    bloco = dados.get("record_counts")
    if not isinstance(bloco, dict):
        return None
    contagens: dict[str, int] = {}
    for chave, valor in bloco.items():
        inteiro = _como_inteiro(valor)
        if inteiro is not None:
            contagens[str(chave)] = inteiro
    return contagens or None


def resolve_oracle_failure_exit_code(exit_code: int, default_exit_code: int = 3) -> int:
    """Mapeia o exit code Python da camada Oracle para o canonico do Orchestrator."""
    if exit_code == 6:
        return EXIT_ORACLE_WORKER_OFFLINE
    if exit_code == 7:
        return EXIT_ORACLE_QUEUE_TIMEOUT
    return default_exit_code


@dataclass(frozen=True)
class PythonStepSpec:  # pylint: disable=too-many-instance-attributes
    # Um campo por parametro de Invoke-OraclePythonScript; agrupar os esconderia.
    """Parametros de uma etapa Python (os de Invoke-OraclePythonScript)."""

    python_exe: str
    script_path: str
    operation_name: str
    step: str = "extract"
    max_attempts: int = 3
    backoff_seconds: tuple[int, ...] = (30, 60, 120)
    input_data: str | None = None
    stdout_is_data: bool = False
    non_retryable_exit_codes: tuple[int, ...] = NAO_REPETIVEIS_PADRAO


@dataclass(frozen=True)
class PythonStepResult:
    """Desfecho de run_python_step (o objeto que o PowerShell devolve)."""

    success: bool
    idempotent: bool
    non_retryable: bool
    output: str
    exit_code: int
    attempts: int


@dataclass(frozen=True)
class _Tentativa:
    """Uma execucao do processo filho: exit code e stdout capturado."""

    exit_code: int
    output: str


def _ambiente_filho(
    ctx: HubRunContext, step: str, *, stdout_is_data: bool = False
) -> dict[str, str]:
    """Ambiente do filho: UTF-8 de ponta a ponta, HUB_* e HUB_LOG_STRUCTURED controlado.

    Quando ``stdout_is_data`` e False, injeta ``HUB_LOG_STRUCTURED=1`` para que os filhos
    emitam envelope JSON (``component="python_domain"``). Quando True, remove
    ``HUB_LOG_STRUCTURED`` do ambiente para proteger o canal de dados em stdout (ex.: RE-03).
    """
    ambiente = dict(os.environ)
    ambiente.update(ctx.ambiente())
    ambiente.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "HUB_STEP": step})
    if stdout_is_data:
        ambiente.pop("HUB_LOG_STRUCTURED", None)
    else:
        ambiente["HUB_LOG_STRUCTURED"] = "1"
    return ambiente


def _e_envelope(linha: str) -> bool:
    """True quando a linha ja e um evento completo do envelope (Test-HubLogEnvelope)."""
    texto = linha.strip()
    if not texto.startswith("{"):
        return False
    try:
        obj = json.loads(texto)
    except ValueError:
        return False
    return isinstance(obj, dict) and all(campo in obj for campo in CAMPOS_ENVELOPE)


def _nivel_da_linha(linha: str, padrao: str) -> str:
    """Nivel pelo marcador [INFO]/[WARN]/[ERRO]/[ERROR]/[DEBUG]/[ALERT] ou ^WARNING:."""
    casamento = _MARCADOR_NIVEL.search(linha)
    if casamento is None:
        return padrao
    marcador = (casamento.group(1) or casamento.group(2)).upper()
    return {
        "ERROR": "ERRO",
        "ERRO": "ERRO",
        "WARN": "WARN",
        "WARNING": "WARN",
        "ALERT": "WARN",
        "DEBUG": "DEBUG",
    }.get(marcador, "INFO")


def forward_line(ctx: HubRunContext, linha: str, nivel_padrao: str, step: str) -> None:
    """Encaminha uma linha de filho: envelope verbatim, texto vira evento log."""
    if not linha.strip():
        return
    if _e_envelope(linha):
        texto = linha.strip()
        with _EMISSAO:
            _anexar_linha(ctx.log_path, texto)
            sys.stdout.write(texto + "\n")
            sys.stdout.flush()
        return
    log(ctx, linha, _nivel_da_linha(linha, nivel_padrao), step=step)


_encaminhar_linha = forward_line


def _iniciar_leitor(fluxo: IO[str], tratar: Callable[[str], None]) -> threading.Thread:
    """Le um fluxo do filho linha a linha, em thread, sem bloquear o pipe."""

    def ler() -> None:
        for linha in fluxo:
            tratar(linha.rstrip("\r\n"))

    leitor = threading.Thread(target=ler, daemon=True)
    leitor.start()
    return leitor


def _enviar_entrada(fluxo: IO[str], dados: str) -> None:
    """Grava a entrada e fecha o stdin. O filho pode sair antes de ler: o exit code decide."""
    try:
        with contextlib.suppress(OSError):
            fluxo.write(dados)
    finally:
        with contextlib.suppress(OSError):
            fluxo.close()


def run_python_script(  # pylint: disable=too-many-arguments
    ctx: HubRunContext,
    *,
    python_exe: str,
    script_path: str | Path,
    step: str,
    cwd: Path | None = None,
    args: Sequence[str] | None = None,
) -> int:
    """Executa um script Python uma unica vez, encaminhando stdout/stderr ao log."""
    _validar_step(step)
    argv = [
        python_exe,
        str(script_path),
        *(args if args is not None else (ctx.exec_id,)),
    ]
    resultado = subprocess.run(
        argv,
        cwd=cwd,
        env=_ambiente_filho(ctx, step, stdout_is_data=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
        check=False,
    )
    for linha in resultado.stdout.splitlines():
        forward_line(ctx, linha, "INFO", step)
    for linha in resultado.stderr.splitlines():
        forward_line(ctx, linha, "WARN", step)
    return int(resultado.returncode)


def _executar_processo(ctx: HubRunContext, spec: PythonStepSpec) -> _Tentativa:
    """Roda o filho uma vez: stdin opcional, stdout como dado e stderr encaminhado."""
    argv = [spec.python_exe, spec.script_path, ctx.exec_id]
    saida: list[str] = []

    def tratar_saida(linha: str) -> None:
        saida.append(linha)
        if not spec.stdout_is_data:
            forward_line(ctx, linha, "INFO", spec.step)

    def tratar_erro(linha: str) -> None:
        forward_line(ctx, linha, "WARN", spec.step)

    with subprocess.Popen(
        argv,
        stdin=subprocess.PIPE if spec.input_data else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_ambiente_filho(ctx, spec.step, stdout_is_data=spec.stdout_is_data),
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
    ) as processo:
        fluxos = [(processo.stdout, tratar_saida), (processo.stderr, tratar_erro)]
        leitores = [
            _iniciar_leitor(fluxo, tratar)
            for fluxo, tratar in fluxos
            if fluxo is not None
        ]
        if spec.input_data and processo.stdin is not None:
            _enviar_entrada(processo.stdin, spec.input_data)
        processo.wait()
        for leitor in leitores:
            leitor.join()
        return _Tentativa(
            exit_code=int(processo.returncode),
            output="".join(f"{linha}\n" for linha in saida),
        )


def _espera_apos(backoff: Sequence[int], tentativa: int) -> int:
    """Espera apos a tentativa que falhou; o indice satura no ultimo valor."""
    if not backoff:
        return 0
    return backoff[min(tentativa - 1, len(backoff) - 1)]


def run_python_step(
    ctx: HubRunContext,
    spec: PythonStepSpec,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> PythonStepResult:
    """Executa um script Python com retry, forward de log e idempotencia.

    Equivale a Invoke-OraclePythonScript sobre Invoke-WithRetry: exit 0 e sucesso;
    exit 2 e idempotente (sem retry); exit em ``non_retryable_exit_codes`` falha
    sem retry; demais codigos repetem com backoff ate ``max_attempts``.
    """
    _validar_step(spec.step)
    ultimo = _Tentativa(exit_code=-1, output="")
    for tentativa in range(1, spec.max_attempts + 1):
        if tentativa > 1:
            retry_attempt(
                ctx,
                spec.step,
                attempt=tentativa,
                max_attempts=spec.max_attempts,
                nivel="WARN",
                mensagem=f"{spec.operation_name} - tentativa {tentativa}/{spec.max_attempts}",
            )
        ultimo = _executar_processo(ctx, spec)
        if ultimo.exit_code in (0, EXIT_IDEMPOTENTE):
            if tentativa > 1:
                retry_attempt(
                    ctx,
                    spec.step,
                    attempt=tentativa,
                    max_attempts=spec.max_attempts,
                    nivel="INFO",
                    mensagem=f"{spec.operation_name} - sucesso apos {tentativa} tentativa(s)",
                )
            return PythonStepResult(
                success=ultimo.exit_code == 0,
                idempotent=ultimo.exit_code == EXIT_IDEMPOTENTE,
                non_retryable=False,
                output=ultimo.output,
                exit_code=ultimo.exit_code,
                attempts=tentativa,
            )
        nome = Path(spec.script_path).name
        falha = f"Python '{nome}' retornou ExitCode={ultimo.exit_code}."
        if ultimo.exit_code in spec.non_retryable_exit_codes:
            retry_attempt(
                ctx,
                spec.step,
                attempt=tentativa,
                max_attempts=spec.max_attempts,
                nivel="ERRO",
                mensagem=(
                    f"{spec.operation_name} - erro nao-transitorio na tentativa "
                    f"{tentativa}/{spec.max_attempts} (retry abortado): {falha}"
                ),
            )
            return PythonStepResult(
                success=False,
                idempotent=False,
                non_retryable=True,
                output=ultimo.output,
                exit_code=ultimo.exit_code,
                attempts=tentativa,
            )
        if tentativa >= spec.max_attempts:
            retry_attempt(
                ctx,
                spec.step,
                attempt=tentativa,
                max_attempts=spec.max_attempts,
                nivel="ERRO",
                mensagem=(
                    f"{spec.operation_name} - todas as {spec.max_attempts} tentativas "
                    f"falharam. Ultimo erro: {falha}"
                ),
            )
            break
        espera = _espera_apos(spec.backoff_seconds, tentativa)
        retry_attempt(
            ctx,
            spec.step,
            attempt=tentativa,
            max_attempts=spec.max_attempts,
            nivel="WARN",
            mensagem=(
                f"{spec.operation_name} - falha na tentativa "
                f"{tentativa}/{spec.max_attempts}: {falha} Aguardando {espera}s."
            ),
        )
        sleep(espera)
    return PythonStepResult(
        success=False,
        idempotent=False,
        non_retryable=False,
        output=ultimo.output,
        exit_code=ultimo.exit_code,
        attempts=spec.max_attempts,
    )


def _mesmo_hash(a: str, b: str) -> bool:
    """Comparacao de hash sem caixa, como o -eq do PowerShell."""
    return a.casefold() == b.casefold()


def get_last_content_hash(
    state_tmp_path: Path | None,
    state_path: Path | None,
    on_warning: Callable[[str], None] | None = None,
) -> str:
    """Hash do conteudo: o .tmp da execucao, senao o definitivo (Get-LastContentHash).

    Arquivo presente e ilegivel devolve "" sem consultar o definitivo, para nao
    suprimir a entrega com um hash antigo.
    """
    for candidato in (state_tmp_path, state_path):
        if candidato is None or not candidato.exists():
            continue
        try:
            dados = json.loads(candidato.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            _alertar(
                on_warning,
                f"State de conteudo '{candidato}' esta ilegivel. Hash tratado como "
                f"ausente (a entrega prossegue). Motivo: {exc}",
            )
            return ""
        hash_atual = dados.get("last_hash") if isinstance(dados, dict) else None
        if hash_atual:
            return str(hash_atual)
        _alertar(
            on_warning,
            f"State de conteudo '{candidato}' nao traz 'last_hash'. Hash tratado como "
            "ausente (a entrega prossegue).",
        )
        return ""
    return ""


def _alertar(on_warning: Callable[[str], None] | None, mensagem: str) -> None:
    """Repassa um aviso ao chamador, se ele pediu."""
    if on_warning is not None:
        on_warning(mensagem)


def new_delivery_state(canais: Sequence[str]) -> dict[str, Any]:
    """Estado de entrega zerado para os canais (New-DeliveryState)."""
    return {
        "last_sent_hash": "",
        "delivery_status": {
            canal: {"success": False, "sent_at": None} for canal in canais
        },
    }


def read_delivery_state(
    caminho: Path,
    canais: Sequence[str],
    on_warning: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Carrega o delivery_state tolerante a arquivo ausente ou corrompido.

    Aceita arquivo com BOM (o PowerShell 5.1 grava UTF-8 com BOM). Canal ausente
    no arquivo mantem o default zerado (Read-DeliveryState).
    """
    estado = new_delivery_state(canais)
    if not caminho.exists():
        return estado
    try:
        salvo = json.loads(caminho.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        _alertar(
            on_warning,
            f"Falha ao ler '{caminho}'. Estado de entrega reiniciado. Motivo: {exc}",
        )
        return estado
    if not isinstance(salvo, dict):
        return estado
    ultimo_hash = salvo.get("last_sent_hash")
    if ultimo_hash:
        estado["last_sent_hash"] = str(ultimo_hash)
    status_salvo = salvo.get("delivery_status")
    if not isinstance(status_salvo, dict):
        return estado
    for canal in canais:
        canal_salvo = status_salvo.get(canal)
        if not isinstance(canal_salvo, dict) or not canal_salvo:
            continue
        destino = estado["delivery_status"][canal]
        if "success" in canal_salvo:
            destino["success"] = bool(canal_salvo["success"])
        if "sent_at" in canal_salvo:
            destino["sent_at"] = canal_salvo["sent_at"]
    return estado


def update_delivery_state_hash(estado: dict[str, Any], hash_atual: str | None) -> bool:
    """Zera o sucesso dos canais quando o conteudo mudou (Update-DeliveryStateHash).

    Hash vazio nao zera: sem hash nao ha como afirmar que o conteudo mudou.
    """
    if hash_atual is None or not hash_atual.strip():
        return False
    if _mesmo_hash(hash_atual, str(estado["last_sent_hash"])):
        return False
    estado["last_sent_hash"] = hash_atual
    for canal in estado["delivery_status"].values():
        canal["success"] = False
    return True


def delivery_pending(
    estado: dict[str, Any], canal: str, hash_atual: str | None = None
) -> bool:
    """True quando o canal ainda precisa entregar (Test-DeliveryPending).

    Canal desconhecido conta como pendente. Com ``hash_atual`` informado, um hash
    diferente do ultimo entregue tambem deixa o canal pendente.
    """
    status = estado["delivery_status"]
    if canal not in status:
        return True
    if not bool(status[canal]["success"]):
        return True
    return hash_atual is not None and not _mesmo_hash(
        hash_atual, str(estado["last_sent_hash"])
    )


def set_delivery_success(estado: dict[str, Any], canal: str) -> None:
    """Marca o canal como entregue, com carimbo dd/MM/yyyy HH:mm:ss (Set-DeliverySuccess)."""
    status = estado["delivery_status"]
    if canal not in status:
        status[canal] = {"success": False, "sent_at": None}
    status[canal]["success"] = True
    status[canal]["sent_at"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def save_delivery_state(estado: dict[str, Any], caminho: Path) -> None:
    """Grava o delivery_state em UTF-8 sem BOM, por troca atomica (Save-DeliveryState)."""
    temporario = caminho.with_name(caminho.name + ".tmp")
    temporario.write_text(
        json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporario, caminho)


def executar_cli_outlook(script: Path, argumentos: list[str]) -> tuple[int, str]:
    """Roda a CLI de e-mail em powershell.exe e devolve (exit code, saida).

    Timeout ou falha de execucao contam como exit 1, para o chamador nao travar.
    """
    comando = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        *argumentos,
    ]
    try:
        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
            timeout=TIMEOUT_CLI_OUTLOOK_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 1, f"CLI de e-mail excedeu {TIMEOUT_CLI_OUTLOOK_S:.0f}s."
    except OSError as exc:
        return 1, f"Falha ao iniciar powershell.exe: {exc}"
    return resultado.returncode, resultado.stdout + resultado.stderr


def _rodar_cli(
    ctx: HubRunContext,
    argumentos: list[str],
    executor: Callable[[Path, list[str]], tuple[int, str]],
    step: str | None,
) -> bool:
    """Chama a CLI (lib/Invoke-OutlookEmail.ps1) e encaminha a saida ao log."""
    script = ctx.raiz / "lib" / "Invoke-OutlookEmail.ps1"
    codigo, saida = executor(script, argumentos)
    for linha in saida.splitlines():
        if linha.strip():
            log(ctx, linha, _nivel_da_linha(linha, "INFO"), step=step)
    return codigo == 0


def send_outlook_email(
    ctx: HubRunContext,
    *,
    to: str,
    subject: str,
    html_body: str,
    executor: Callable[[Path, list[str]], tuple[int, str]] = executar_cli_outlook,
) -> bool:
    """Envia o e-mail pelo Outlook COM, via a CLI PowerShell. True se confirmado."""
    fd, caminho = tempfile.mkstemp(prefix="hub_email_", suffix=".html")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as arquivo:
            arquivo.write(html_body)
        argumentos = [
            "-To",
            to,
            "-Subject",
            subject,
            "-HtmlBodyFile",
            caminho,
            "-ExecId",
            ctx.exec_id,
            "-LogPath",
            str(ctx.log_path),
        ]
        return _rodar_cli(ctx, argumentos, executor, step="dispatch")
    finally:
        Path(caminho).unlink(missing_ok=True)


def send_failure_alert(
    ctx: HubRunContext,
    *,
    task_name: str,
    ultimo_erro: str,
    tentativas: int,
    executor: Callable[[Path, list[str]], tuple[int, str]] = executar_cli_outlook,
) -> bool:
    """Envia o alerta de falha definitiva (Send-AlertaFalhaDefinitiva) pela CLI.

    Retorna True quando a CLI terminou sem excecao. O PowerShell nao devolve
    confirmacao de envio neste caminho.
    """
    argumentos = [
        "-Alerta",
        "-TaskName",
        task_name,
        "-UltimoErro",
        ultimo_erro,
        "-Tentativas",
        str(tentativas),
        "-ExecId",
        ctx.exec_id,
        "-LogPath",
        str(ctx.log_path),
    ]
    return _rodar_cli(ctx, argumentos, executor, step=None)


# ---------------------------------------------------------------------------
# Check Oracle do pre-flight: Test-AutomationPreFlight -CheckOracle e
# Get-OraclePreFlightExitCode (Lib-Logging.psm1, Lib-Oracle.psm1 e
# Lib-OracleEndpoint.psm1). A decisao e a do PowerShell; as sondas e a leitura do
# heartbeat ficam atras de parametros, para teste com dubles.
# ---------------------------------------------------------------------------

EXIT_PREFLIGHT_FALHA: Final[int] = 9
"""PREFLIGHT_FAILED: falha de ambiente que exige revisao antes de reenfileirar."""

MODO_FILA: Final[str] = "queue"
PORTA_SMB: Final[int] = 445
PRAZO_SONDA_SMB_S: Final[float] = 1.5
"""Espera da sonda TCP da porta 445 da pasta UNC (WaitOne(1500) no PS)."""
PRAZO_SONDA_ORACLE_S: Final[float] = 3.0
"""Espera da porta TCP do Oracle (Test-OracleTcpEndpoint, TimeoutMs 3000 no PS)."""
PORTA_ORACLE_PADRAO: Final[int] = 1521
MAX_IDADE_HEARTBEAT_S: Final[float] = fila.HEARTBEAT_MAX_AGE_SECONDS
"""Idade maxima do heartbeat parado: -MaxAgeSeconds 45 no PS (mesmo valor do cliente)."""
MAX_IDADE_HEARTBEAT_OCUPADO_S: Final[float] = fila.BUSY_HEARTBEAT_MAX_AGE_SECONDS
"""Idade maxima com worker ocupado ou com .proc ativo: -BusyMaxAgeSeconds 240 no PS."""
SINAIS_LEGADOS: Final[frozenset[str]] = frozenset(
    {"_worker_sinal_a.txt", "_worker_sinal_b.txt"}
)
_UNC_HOST: Final[re.Pattern[str]] = re.compile(r"^\\\\([^\\]+)\\")
_PROTOCOLO: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://")
_BARRAS_INICIAIS: Final[re.Pattern[str]] = re.compile(r"^//")
_SEPARADOR_HOST: Final[re.Pattern[str]] = re.compile(r"[:/]")
_EZ_CONNECT: Final[re.Pattern[str]] = re.compile(
    r"^(//)?(?P<host>[A-Za-z0-9.\-_]+)(:(?P<porta>\d+))?(/[^/\s]*)?$"
)
_HOST_TNS: Final[re.Pattern[str]] = re.compile(r"HOST\s*=\s*([^\)\s]+)", re.IGNORECASE)
_PORTA_TNS: Final[re.Pattern[str]] = re.compile(r"PORT\s*=\s*(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class WorkerHeartbeat:
    """Leitura do _worker_heartbeat.json: idade pelo mtime (escala do servidor) e conteudo."""

    idade_s: float
    estado: str = ""
    versao: str = ""


@dataclass(frozen=True)
class StatusFila:
    """Vivacidade do worker na fila: os campos que o pre-flight do PowerShell usa."""

    alive: bool
    reachable: bool
    queue_dir: str
    source: str = "none"
    versao: str = ""
    reason: str = "worker offline"


@dataclass(frozen=True)
class OracleEndpoint:
    """Servidor e porta do Oracle, de alias do tnsnames.ora ou de EZ Connect."""

    servidor: str
    porta: int


@dataclass(frozen=True)
class OraclePreflight:
    """Check Oracle do pre-flight: linhas para o log e o status da fila (modo queue)."""

    modo: str
    linhas: tuple[str, ...]
    status: StatusFila | None = None

    @property
    def ok(self) -> bool:
        """True quando nenhuma linha reprova (ERRO/FAIL), o mesmo criterio do $allOk do PS."""
        return not any(linha.startswith(("ERRO:", "FAIL:")) for linha in self.linhas)


type SondaTcp = Callable[[str, int, float], bool]
"""(host, porta, prazo em segundos) -> True quando a conexao TCP abre."""
type LeitorHeartbeat = Callable[[Path], WorkerHeartbeat | None]
"""Pasta da fila -> heartbeat, ou None quando o arquivo nao existe. OSError: falha de leitura."""


def tcp_probe(host: str, porta: int, prazo_s: float) -> bool:
    """True quando a conexao TCP abre dentro do prazo. Falha de nome ou de rede e False."""
    try:
        with socket.create_connection((host, porta), timeout=prazo_s):
            return True
    except (OSError, ValueError):
        return False


def relogio_servidor(pasta: Path) -> float:
    """Agora na escala de relogio do servidor da fila: o mtime de uma sonda gravada na pasta.

    Igual ao Get-OracleQueueServerNowUtc do PS. Sem escrita na pasta, cai no relogio local.
    """
    sonda = pasta / f"_clock_probe_{os.getpid()}_{secrets.token_hex(4)}.tmp"
    try:
        sonda.write_bytes(b"clock-probe")
        return sonda.stat().st_mtime
    except OSError:
        return time.time()
    finally:
        with contextlib.suppress(OSError):
            sonda.unlink(missing_ok=True)


def _existe(caminho: Path) -> bool:
    """Path.exists sem excecao: erro de acesso conta como ausente, como Test-Path."""
    try:
        return caminho.exists()
    except OSError:
        return False


def _e_diretorio(caminho: Path) -> bool:
    """Path.is_dir sem excecao: erro de acesso conta como ausente, como Test-Path."""
    try:
        return caminho.is_dir()
    except OSError:
        return False


def _texto(valor: object) -> str:
    """Campo do JSON como texto, como [string] do PS: null vira vazio."""
    return "" if valor is None else str(valor)


def _campos_heartbeat(caminho: Path) -> tuple[str, str]:
    """state e version do conteudo; vazios quando ilegivel, em branco ou fora de um objeto."""
    try:
        bruto = caminho.read_text(encoding="cp1252", errors="replace")
    except OSError:
        return "", ""
    if not bruto.strip():
        return "", ""
    try:
        dados: object = json.loads(bruto)
    except ValueError:
        return "", ""
    if not isinstance(dados, dict):
        return "", ""
    return _texto(dados.get("state")), _texto(dados.get("version"))


def read_worker_heartbeat(
    pasta: Path, *, relogio: Callable[[Path], float] = relogio_servidor
) -> WorkerHeartbeat | None:
    """Le _worker_heartbeat.json como Test-OracleQueueWorkerAlive. None quando nao existe.

    A idade e arredondada a 1 casa (como [math]::Round do PS) antes da comparacao com o
    limite. Conteudo ilegivel (regravacao em curso) mantem so a idade, com estado vazio.
    OSError quando o stat falha: quem chama trata como falha de leitura do heartbeat.
    """
    caminho = pasta / fila.WORKER_HEARTBEAT_FILENAME
    if not _existe(caminho):
        return None
    idade = round(relogio(pasta) - caminho.stat().st_mtime, 1)
    estado, versao = _campos_heartbeat(caminho)
    return WorkerHeartbeat(idade_s=idade, estado=estado, versao=versao)


def _num(valor: float) -> str:
    """Numero no texto do log, sem casa decimal quando inteiro."""
    return str(int(valor)) if valor.is_integer() else str(valor)


def _motivo_fila_inacessivel(base: str, sonda: SondaTcp) -> str | None:
    """Motivo de a pasta da fila nao estar alcancavel, ou None (alcance do PS)."""
    casamento = _UNC_HOST.match(base)
    if casamento is not None:
        host = casamento.group(1)
        if not sonda(host, PORTA_SMB, PRAZO_SONDA_SMB_S):
            return f"servidor SMB {host} inacessivel (porta 445)"
    if not _e_diretorio(Path(base)):
        return f"pasta inacessivel ({base})"
    return None


def _nomes_na_pasta(caminho: Path) -> list[str]:
    """Nomes dos itens da pasta; lista vazia quando a listagem falha (sem erro, como no PS)."""
    try:
        with os.scandir(caminho) as entradas:
            return [entrada.name for entrada in entradas]
    except OSError:
        return []


def _status_com_heartbeat(
    base: str, heartbeat: WorkerHeartbeat, procs: int
) -> StatusFila:
    """Decisao pelo heartbeat: vivo se a idade cabe no limite (240 s com worker ocupado)."""
    ocupado = heartbeat.estado.lower() == "busy" or procs > 0
    limite = MAX_IDADE_HEARTBEAT_OCUPADO_S if ocupado else MAX_IDADE_HEARTBEAT_S
    idade = _num(heartbeat.idade_s)
    if heartbeat.idade_s <= limite:
        motivo = f"heartbeat ativo ({idade}s, state={heartbeat.estado})"
    else:
        motivo = f"heartbeat expirado ha {idade}s (limite {_num(limite)}s)"
    return StatusFila(
        alive=heartbeat.idade_s <= limite,
        reachable=True,
        queue_dir=base,
        source="heartbeat",
        versao=heartbeat.versao,
        reason=motivo,
    )


def _status_sem_heartbeat(
    base: str, nomes: list[str], procs: int, falha: str | None
) -> StatusFila:
    """Decisao sem heartbeat utilizavel: .proc ativo, sinal legado, ou offline."""
    if procs > 0:
        return StatusFila(
            alive=True,
            reachable=True,
            queue_dir=base,
            source="proc",
            reason=f"{procs} requisicao(oes) em processamento",
        )
    if SINAIS_LEGADOS.intersection(nomes):
        return StatusFila(
            alive=True,
            reachable=True,
            queue_dir=base,
            source="signal",
            reason="arquivo de sinal legado presente (sem heartbeat v2.6+)",
        )
    motivo = (
        "sem heartbeat nem sinal do worker na fila"
        if falha is None
        else f"{falha}; sem sinal do worker na fila"
    )
    return StatusFila(alive=False, reachable=True, queue_dir=base, reason=motivo)


def queue_worker_status(
    pasta: str,
    *,
    sonda_tcp: SondaTcp | None = None,
    ler_heartbeat: LeitorHeartbeat | None = None,
) -> StatusFila:
    """Vivacidade do worker Oracle pela pasta da fila (Test-OracleQueueWorkerAlive do PS).

    Ordem do PS: alcance (porta 445 e pasta), heartbeat (decide quando existe e le),
    .proc ativo e, por ultimo, sinal legado.
    """
    base = pasta.strip()
    if not base:
        return StatusFila(
            alive=False,
            reachable=False,
            queue_dir="",
            reason="ORACLE_QUEUE_DIR nao configurado",
        )
    inacessivel = _motivo_fila_inacessivel(base, sonda_tcp or tcp_probe)
    if inacessivel is not None:
        return StatusFila(
            alive=False, reachable=False, queue_dir=base, reason=inacessivel
        )
    caminho = Path(base)
    nomes = _nomes_na_pasta(caminho)
    procs = sum(
        1 for nome in nomes if nome.startswith("req_") and nome.endswith(".proc")
    )
    leitor: LeitorHeartbeat = ler_heartbeat or read_worker_heartbeat
    try:
        heartbeat = leitor(caminho)
    except OSError as exc:
        return _status_sem_heartbeat(
            base, nomes, procs, f"falha ao ler heartbeat: {exc}"
        )
    if heartbeat is None:
        return _status_sem_heartbeat(base, nomes, procs, None)
    return _status_com_heartbeat(base, heartbeat, procs)


def _linha_fila(status: StatusFila) -> str:
    """Linha do pre-flight para a fila, no formato de Test-AutomationPreFlight."""
    if not status.reachable:
        return f"ERRO: Oracle Queue ({status.queue_dir}) Off ({status.reason})"
    if not status.alive:
        return (
            f"ERRO: Oracle Queue ({status.queue_dir}) Worker Offline ({status.reason})"
        )
    sufixo = f" worker {status.versao}" if status.versao.strip() else ""
    return f"OK: Oracle Queue ({status.queue_dir}) On ({status.reason}{sufixo})"


def oracle_host(conexao: str) -> str:
    """Host de ORACLE_CONNECT_STRING, extraido como Test-AutomationPreFlight extrai."""
    sem_protocolo = _BARRAS_INICIAIS.sub(
        "", _PROTOCOLO.sub("", conexao, count=1), count=1
    )
    return _SEPARADOR_HOST.split(sem_protocolo, maxsplit=1)[0].strip()


def find_tnsnames() -> Path | None:
    """tnsnames.ora na ordem do cliente Oracle: TNS_ADMIN, ORACLE_CLIENT_LIB_DIR e ORACLE_CLIENT_PATH."""
    pastas: list[Path] = []
    tns_admin = os.environ.get("TNS_ADMIN", "").strip()
    if tns_admin:
        pastas.append(Path(tns_admin))
    for env_cliente in ("ORACLE_CLIENT_LIB_DIR", "ORACLE_CLIENT_PATH"):
        cliente = os.environ.get(env_cliente, "").strip()
        if cliente:
            pastas.append(Path(cliente) / "network" / "admin")
    for pasta in pastas:
        if _existe(pasta / "tnsnames.ora"):
            return pasta / "tnsnames.ora"
    return None


def _bloco_tns(alvo: str) -> re.Pattern[str]:
    """Bloco 'ALIAS = ...' do tnsnames.ora, sem diferenciar caixa.

    Sufixo de dominio no arquivo casa com o alias sem ele (DBPRD casa DBPRD.WORLD).
    """
    return re.compile(
        rf"^\s*{re.escape(alvo)}(\.[A-Za-z0-9_\-]+)*\s*=(?P<corpo>.*?)"
        r"(?=^\s*[A-Za-z0-9_.\-]+\s*=|\Z)",
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )


def _endpoint_tnsnames(alvo: str) -> OracleEndpoint | None:
    """HOST e PORT do bloco do alias (porta 1521 quando ausente). None sem alias ou sem HOST."""
    arquivo = find_tnsnames()
    if arquivo is None:
        return None
    try:
        conteudo = arquivo.read_text(encoding="cp1252", errors="replace")
    except OSError:
        return None
    bloco = _bloco_tns(alvo).search(conteudo)
    if bloco is None:
        return None
    corpo = bloco.group("corpo")
    host = _HOST_TNS.search(corpo)
    if host is None:
        return None
    porta = _PORTA_TNS.search(corpo)
    return OracleEndpoint(
        servidor=host.group(1),
        porta=int(porta.group(1)) if porta is not None else PORTA_ORACLE_PADRAO,
    )


def _endpoint_ez_connect(alvo: str) -> OracleEndpoint | None:
    """Host e porta de EZ Connect (host[:porta][/servico]); sem ':' nem '/' nao e endereco."""
    endereco = _PROTOCOLO.sub("", alvo, count=1).split("?", 1)[0]
    if not _SEPARADOR_HOST.search(endereco):
        return None
    casamento = _EZ_CONNECT.match(endereco)
    if casamento is None:
        return None
    porta = casamento.group("porta")
    return OracleEndpoint(
        servidor=casamento.group("host"),
        porta=int(porta) if porta is not None else PORTA_ORACLE_PADRAO,
    )


def resolve_oracle_endpoint(conexao: str) -> OracleEndpoint | None:
    """Servidor e porta de um alias do tnsnames.ora ou de EZ Connect (Resolve-OracleEndpoint).

    O alias do tnsnames vem primeiro. Alias sem ':' nem '/' que nao esta no tnsnames
    devolve None: nao vira host (o PS fazia o mesmo).
    """
    alvo = conexao.strip()
    if not alvo:
        return None
    via_tns = _endpoint_tnsnames(alvo)
    return via_tns if via_tns is not None else _endpoint_ez_connect(alvo)


def _linhas_conexao_oracle(conexao: str, sonda: SondaTcp | None) -> tuple[str, ...]:
    """Check Oracle fora do modo queue: so informa. Falha vira WARN, nunca ERRO (como no PS)."""
    host = oracle_host(conexao)
    if not host:
        return ("WARN: Oracle host nao configurado (ORACLE_CONNECT_STRING ausente)",)
    endpoint = resolve_oracle_endpoint(conexao)
    if endpoint is None:
        return (
            f"WARN: Oracle ({host}) sem endpoint resolvido (alias ausente no tnsnames.ora)",
        )
    destino = f"{host} -> {endpoint.servidor}:{endpoint.porta}"
    if (sonda or tcp_probe)(endpoint.servidor, endpoint.porta, PRAZO_SONDA_ORACLE_S):
        return (f"OK: Oracle ({destino}) On",)
    return (f"WARN: Oracle ({destino}) Off (porta TCP sem resposta em 3 s)",)


def oracle_preflight(
    *,
    modo: str,
    conexao: str = "",
    pasta_fila: str = "",
    sonda_tcp: SondaTcp | None = None,
    ler_heartbeat: LeitorHeartbeat | None = None,
) -> OraclePreflight:
    """Check Oracle do pre-flight (Test-AutomationPreFlight -CheckOracle), sem log.

    Modo queue: vivacidade do worker na pasta da fila. Demais modos: host de ``conexao``
    e sonda TCP do endpoint, com falha em WARN. ``modo`` chega normalizado (strip e lower),
    como o $driverModeNormalized do run.ps1.

    Divergencias com o PowerShell (a decisao final e a mesma):
    * Test-AutomationPreFlight compara ORACLE_DRIVER_MODE cru (-eq, sem trim); com espaco
      em volta do valor, o PS tratava o check como nao-fila. Aqui vale o normalizado.
    * tnsnames.ora ilegivel: o PS deixa a excecao subir; aqui vira alias sem endpoint (WARN).
    * lib/python/oracle_queue.check_worker_liveness compara a idade sem arredondar, cacheia
      a sonda de relogio por 10 min e nao tem a regra de busy como parametro. Esta leitura
      arredonda a idade antes de comparar (como o PS), mede o relogio a cada chamada e usa
      os limiares 45 s e 240 s do PS. Nao reutiliza aquela funcao por isso.
    """
    if modo != MODO_FILA:
        return OraclePreflight(
            modo=modo, linhas=_linhas_conexao_oracle(conexao, sonda_tcp)
        )
    if not pasta_fila.strip():
        return OraclePreflight(
            modo=modo,
            linhas=(
                "ERRO: Oracle Queue (DEFAULT_QUEUE_DIR nao encontrado em "
                "lib/python/oracle_queue.py; defina ORACLE_QUEUE_DIR)",
            ),
        )
    status = queue_worker_status(
        pasta_fila, sonda_tcp=sonda_tcp, ler_heartbeat=ler_heartbeat
    )
    return OraclePreflight(modo=modo, linhas=(_linha_fila(status),), status=status)


def _outros_checks_ok(outros_checks: Callable[[], bool]) -> bool:
    """Test-OraclePreFlightOutrosChecksOk: so True conta como ok; excecao reprova."""
    try:
        return outros_checks() is True
    # Residual: os checks vem do chamador (disco, paths, log). Excecao deles reprova, como no
    # PS, em vez de sair do pre-flight sem o codigo de falha.
    except Exception:  # pylint: disable=broad-exception-caught
        return False


def oracle_preflight_exit_code(
    preflight: OraclePreflight, outros_checks: Callable[[], bool] | None = None
) -> int:
    """Get-OraclePreFlightExitCode: codigo de falha do pre-flight.

    26 (ORACLE_WORKER_OFFLINE, reenfileirado quando o heartbeat voltar) so no modo queue,
    com a pasta resolvida, o worker parado e os demais checks ok. Todo o resto e 9,
    inclusive falha deterministica somada ao worker parado (reenfileirar a repetiria).

    O PS reavalia o worker nesta etapa; aqui vale o status ja lido pelo preflight (mesma
    leitura, sem segunda sonda). ``outros_checks`` so roda com o worker parado.
    """
    status = preflight.status
    if preflight.modo != MODO_FILA or status is None or status.alive:
        return EXIT_PREFLIGHT_FALHA
    if outros_checks is not None and not _outros_checks_ok(outros_checks):
        return EXIT_PREFLIGHT_FALHA
    return EXIT_ORACLE_WORKER_OFFLINE


# ---------------------------------------------------------------------------
# Helpers comuns aos runners (pre-flight, telemetria, log, limpeza, JSON)
# ---------------------------------------------------------------------------


def default_telemetry(raiz: Path) -> TelemetryClient | None:
    """Cliente HTTP da telemetria quando o ``.env`` traz ``ORCHESTRATOR_API_KEY``."""
    chave = read_api_key(raiz)
    return HttpTelemetryClient(chave) if chave else None


def driver_mode() -> str:
    """``ORACLE_DRIVER_MODE`` normalizado; ausente vale ``auto``."""
    bruto = os.environ.get("ORACLE_DRIVER_MODE", "").strip().lower()
    return bruto or "auto"


def oracle_preflight_from_env() -> OraclePreflight:
    """Check Oracle do pre-flight a partir de ``ORACLE_DRIVER_MODE``, ``ORACLE_CONNECT_STRING`` e fila."""
    return oracle_preflight(
        modo=driver_mode(),
        conexao=os.environ.get("ORACLE_CONNECT_STRING", ""),
        pasta_fila=fila.get_queue_dir(),
    )


def free_disk_gb(caminho: Path) -> float:
    """Espaco livre, em GB, na unidade que contem ``caminho``."""
    return shutil.disk_usage(caminho.anchor or str(caminho)).free / (1024**3)


def disk_preflight_line(raiz: Path, minimo_gb: float = ESPACO_MINIMO_GB_PADRAO) -> str:
    """Linha de disco do pre-flight: ``ERRO`` abaixo de ``minimo_gb``, ``WARN`` em erro de E/S."""
    try:
        livre = round(free_disk_gb(raiz), 2)
    except OSError:
        return "WARN: Falha ao ler espaco em disco (Ignorado)"
    if livre < minimo_gb:
        return f"ERRO: Disco critico ({livre} GB)"
    return f"OK: Disco estavel ({livre} GB)"


def path_preflight_line(caminho: Path) -> str:
    """Linha de existencia de caminho do pre-flight (CheckPaths)."""
    if caminho.exists():
        return f"OK: Path: {caminho.name}"
    return f"ERRO: Path inacessivel: {caminho.name}"


def run_preflight(
    ctx: HubRunContext,
    caminhos: Sequence[Path],
    oracle: OraclePreflight | None = None,
    *,
    minimo_gb: float = ESPACO_MINIMO_GB_PADRAO,
    step: str | None = "preflight",
) -> bool:
    """Check de disco, paths e linhas Oracle (Test-AutomationPreFlight)."""
    log(ctx, "Iniciando Pre-Flight Check...", step=step)
    resultados = [disk_preflight_line(ctx.raiz, minimo_gb=minimo_gb)]
    resultados.extend(path_preflight_line(caminho) for caminho in caminhos)
    if oracle is not None:
        resultados.extend(oracle.linhas)
    ok = not any(linha.startswith(("ERRO:", "FAIL:")) for linha in resultados)
    log(
        ctx,
        "Pre-Flight: " + " | ".join(resultados),
        "INFO" if ok else "ERRO",
        step=step,
    )
    return ok


def _linha_log_expirada(linha: str, corte: date) -> bool:
    casamento = _PADRAO_TS_LOG.match(linha)
    if casamento is None:
        return False
    try:
        return date.fromisoformat(casamento.group(1)) < corte
    except ValueError:
        return False


def rotate_log(caminho: Path, dias: int = RETENCAO_LOG_DIAS_PADRAO) -> None:
    """Remove do ``.jsonl`` os eventos anteriores a ``dias`` e garante UTF-8 sem BOM."""
    if not caminho.exists():
        return
    corte = date.today() - timedelta(days=dias)
    with contextlib.suppress(OSError, ValueError):
        bruto = caminho.read_bytes()
        tinha_bom = bruto.startswith(b"\xef\xbb\xbf")
        conteudo = bruto.decode("utf-8-sig")
        linhas = [linha.rstrip("\r") for linha in conteudo.split("\n") if linha.strip()]
        mantidas = [linha for linha in linhas if not _linha_log_expirada(linha, corte)]
        if len(mantidas) == len(linhas) and not tinha_bom:
            return
        temporario = caminho.with_name(caminho.name + ".tmp")
        with temporario.open("w", encoding="utf-8", newline="\r\n") as arquivo:
            arquivo.write("".join(f"{linha}\n" for linha in mantidas))
        os.replace(temporario, caminho)


def remove_quietly(caminho: Path) -> None:
    """Remove um arquivo se existir; falhas de E/S sao ignoradas."""
    with contextlib.suppress(OSError):
        caminho.unlink(missing_ok=True)


def warn_logger(ctx: HubRunContext, step: str | None = None) -> Callable[[str], None]:
    """Devolve um callback ``Callable[[str], None]`` que emite eventos ``WARN`` no log."""

    def avisar(mensagem: str) -> None:
        log(ctx, mensagem, "WARN", step=step)

    return avisar


def write_json_atomic(caminho: Path, dados: object, *, indent: int = 2) -> None:
    """Grava JSON UTF-8 sem BOM de forma atomica (``.tmp`` no mesmo diretorio + ``os.replace``)."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conteudo = json.dumps(dados, ensure_ascii=False, indent=indent)
    fd, nome_tmp = tempfile.mkstemp(
        prefix=f".{caminho.name}.", suffix=".tmp", dir=str(caminho.parent)
    )
    temporario = Path(nome_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as arquivo:
            arquivo.write(conteudo)
        os.replace(temporario, caminho)
    except Exception:
        remove_quietly(temporario)
        raise
