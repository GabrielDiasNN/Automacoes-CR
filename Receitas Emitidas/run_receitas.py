"""Runner Python da automacao Receitas Emitidas (RE-03), piloto do item 3, parte 2.

Substitui a orquestracao do ``run.ps1`` anterior e reproduz o mesmo fluxo, passo a passo:

1. pre-flight: Oracle Client conforme ORACLE_DRIVER_MODE (so ``queue`` dispensa oci.dll),
   paths, disco e, no modo ``queue``, o worker da fila;
2. lock global ``RE-03``;
3. extract: ``extract_oracle.py`` com stdout como dado, 3 tentativas e backoff 30/60/120;
   exit 2 encerra com 0 por idempotencia, sem e-mail;
4. transform: ``generate_html_report.py`` com o JSON do extract na entrada, backoff 10/30/60;
5. dispatch: e-mail pelo canal ``email`` com ``receitas_state.json``/``.tmp`` e
   ``delivery_state.json``; envio por ``lib/Invoke-OutlookEmail.ps1``, 2 tentativas;
6. commit: ``receitas_state.json.tmp`` promovido a ``receitas_state.json``.

Uso: ``python run_receitas.py [ExecId] [--dry-run]``. O ``run.ps1`` e um shim que resolve
o interpretador, chama este arquivo e repassa o exit code. Com ``--dry-run``, pre-flight,
extract e transform rodam de verdade, mas nenhum e-mail e enviado e o estado nao e
confirmado: a execucao so loga o que faria. Uso manual de validacao.
"""

# pylint: disable=import-error
from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Final

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "python")
)

import hub_runner as hr  # noqa: E402
import oracle_queue as fila  # noqa: E402
from automation_log import ensure_utf8_streams  # noqa: E402

AUTOMACAO: Final[str] = "Receitas Emitidas"
CHAVE_LOCK: Final[str] = "RE-03"
SLUG_LOG: Final[str] = "ReceitasEmitidas"
SLUG_TRACE: Final[str] = "re"
MOTOR_EXTRACAO: Final[str] = "Python (Direct Oracle CTE)"
CANAL_EMAIL: Final[str] = "email"
RE_DIR: Final[Path] = Path(__file__).resolve().parent
RAIZ: Final[Path] = RE_DIR.parent
EXIT_PREFLIGHT: Final[int] = hr.EXIT_PREFLIGHT_FALHA
EXIT_ERRO_FATAL: Final[int] = 1
EXIT_FALHA_EXTRACAO: Final[int] = 3
TENTATIVAS_EXTRACAO: Final[int] = 3
BACKOFF_EXTRACAO: Final[tuple[int, ...]] = (30, 60, 120)
TENTATIVAS_TRANSFORM: Final[int] = 3
BACKOFF_TRANSFORM: Final[tuple[int, ...]] = (10, 30, 60)
TENTATIVAS_EMAIL: Final[int] = 2
BACKOFF_EMAIL: Final[tuple[int, ...]] = (15, 30)
RETENCAO_LOG_DIAS: Final[int] = 15
ESPACO_MINIMO_GB: Final[float] = 1.0
_PADRAO_TS: Final[re.Pattern[str]] = re.compile(
    r'^\{"(?:ts|timestamp)":"(\d{4}-\d{2}-\d{2})T'
)


class _ErroFatal(RuntimeError):
    """Falha que o run.ps1 tratava com throw: vira ERRO FATAL e exit 1."""


@dataclass(frozen=True)
class Caminhos:
    """Arquivos lidos e gravados pela automacao, todos na pasta dela."""

    extract_py: Path
    generate_py: Path
    config: Path
    estado: Path
    estado_tmp: Path
    entrega: Path
    resultado: Path

    @classmethod
    def da_pasta(cls, pasta: Path) -> Caminhos:
        """Caminhos padrao da automacao a partir da pasta dela."""
        return cls(
            extract_py=pasta / "extract_oracle.py",
            generate_py=pasta / "generate_html_report.py",
            config=pasta / "receitas_config.json",
            estado=pasta / "receitas_state.json",
            estado_tmp=pasta / "receitas_state.json.tmp",
            entrega=pasta / "delivery_state.json",
            resultado=pasta / "re_result.json",
        )


@dataclass
class _Sessao:
    """Estado de uma execucao: contexto de log, modo de validacao e resultado fresco."""

    ctx: hr.HubRunContext
    caminhos: Caminhos
    dry_run: bool
    resultado_fresco: bool = False


def _aviso(ctx: hr.HubRunContext, step: str | None = None) -> Callable[[str], None]:
    """Repassa avisos das bibliotecas ao log da execucao como evento WARN."""

    def avisar(mensagem: str) -> None:
        hr.log(ctx, mensagem, "WARN", step=step)

    return avisar


def _aguardar(segundos: float) -> None:
    """Espera entre tentativas; isolado para que os testes nao durmam de verdade."""
    time.sleep(segundos)


def _telemetria_padrao(raiz: Path) -> hr.TelemetryClient | None:
    """Cliente HTTP da telemetria quando o .env traz ORCHESTRATOR_API_KEY."""
    chave = hr.read_api_key(raiz)
    return hr.HttpTelemetryClient(chave) if chave else None


def _modo_driver() -> str:
    """ORACLE_DRIVER_MODE normalizado; ausente vale 'auto', o padrao do .env.example."""
    bruto = os.environ.get("ORACLE_DRIVER_MODE", "").strip().lower()
    return bruto or "auto"


def _lib_oracle() -> str:
    """Pasta do Oracle Client: ORACLE_CLIENT_LIB_DIR, com ORACLE_CLIENT_PATH de fallback."""
    lib = os.environ.get("ORACLE_CLIENT_LIB_DIR", "").strip()
    return lib or os.environ.get("ORACLE_CLIENT_PATH", "").strip()


def _reprovar(ctx: hr.HubRunContext, mensagem: str) -> bool:
    """Registra um erro do pre-flight e devolve False."""
    hr.log(ctx, mensagem, "ERRO", step="preflight")
    return False


def _checar_cliente_oracle(ctx: hr.HubRunContext) -> bool:
    """Oracle Client conforme o modo: so 'queue' dispensa oci.dll (PRE-FLIGHT do run.ps1)."""
    modo = _modo_driver()
    if modo == "queue":
        hr.log(
            ctx,
            "PRE-FLIGHT OK: Oracle Driver Mode 'queue' nao exige Oracle Client local.",
            step="preflight",
        )
        return True
    lib = _lib_oracle()
    if not lib:
        return _reprovar(
            ctx,
            "PRE-FLIGHT ERRO: ORACLE_CLIENT_LIB_DIR/ORACLE_CLIENT_PATH nao definido "
            f"para modo '{modo}'.",
        )
    if not Path(lib).exists():
        return _reprovar(
            ctx,
            f"PRE-FLIGHT ERRO: Oracle Client nao encontrado em '{lib}' para modo '{modo}'.",
        )
    if not (Path(lib) / "oci.dll").exists():
        return _reprovar(
            ctx, f"PRE-FLIGHT ERRO: oci.dll ausente em '{lib}' para modo '{modo}'."
        )
    hr.log(
        ctx,
        f"PRE-FLIGHT OK: Oracle Client validado em '{lib}' (modo '{modo}').",
        step="preflight",
    )
    return True


def _espaco_livre_gb(caminho: Path) -> float:
    """Espaco livre, em GB, na unidade que contem o caminho."""
    return shutil.disk_usage(caminho.anchor or str(caminho)).free / (1024**3)


def _linha_disco(raiz: Path) -> str:
    """Linha de disco do pre-flight: ERRO abaixo de 1 GB livre, WARN se nao der para ler."""
    try:
        livre = round(_espaco_livre_gb(raiz), 2)
    except OSError:
        return "WARN: Falha ao ler espaco em disco (Ignorado)"
    if livre < ESPACO_MINIMO_GB:
        return f"ERRO: Disco critico ({livre} GB)"
    return f"OK: Disco estavel ({livre} GB)"


def _linha_caminho(caminho: Path) -> str:
    """Linha de um path do pre-flight (CheckPaths)."""
    if caminho.exists():
        return f"OK: Path: {caminho.name}"
    return f"ERRO: Path inacessivel: {caminho.name}"


def _resultado_oracle() -> hr.OraclePreflight:
    """Check Oracle do pre-flight, com o modo, a conexao e a pasta da fila do ambiente."""
    return hr.oracle_preflight(
        modo=_modo_driver(),
        conexao=os.environ.get("ORACLE_CONNECT_STRING", ""),
        pasta_fila=fila.get_queue_dir(),
    )


def _pre_flight_automacao(
    ctx: hr.HubRunContext,
    caminhos: Sequence[Path],
    *,
    checar_oracle: bool,
    oracle: hr.OraclePreflight | None = None,
) -> bool:
    """Test-AutomationPreFlight: disco, paths e, se pedido, as linhas do check Oracle."""
    hr.log(ctx, "Iniciando Pre-Flight Check...", step="preflight")
    resultados = [_linha_disco(ctx.raiz)]
    resultados.extend(_linha_caminho(caminho) for caminho in caminhos)
    if checar_oracle and oracle is not None:
        resultados.extend(oracle.linhas)
    ok = not any(linha.startswith(("ERRO:", "FAIL:")) for linha in resultados)
    hr.log(
        ctx,
        "Pre-Flight: " + " | ".join(resultados),
        "INFO" if ok else "ERRO",
        step="preflight",
    )
    return ok


def _caminhos_preflight(caminhos: Caminhos) -> tuple[Path, ...]:
    """Interpretador e scripts que o pre-flight confere (CheckPaths do run.ps1)."""
    return (
        Path(sys.executable),
        caminhos.extract_py,
        caminhos.generate_py,
        caminhos.config,
    )


def _codigo_falha_preflight(
    ctx: hr.HubRunContext, caminhos: Sequence[Path], oracle: hr.OraclePreflight | None
) -> int:
    """Get-OraclePreFlightExitCode: 26 so no modo queue, com worker offline e o resto ok.

    Sem check Oracle (cliente local reprovado), o codigo e 9: so o modo queue pode dar 26.
    """
    if oracle is None:
        return EXIT_PREFLIGHT
    return hr.oracle_preflight_exit_code(
        oracle,
        outros_checks=lambda: _pre_flight_automacao(ctx, caminhos, checar_oracle=False),
    )


def _preflight(sessao: _Sessao) -> int | None:
    """Etapa preflight. Devolve o exit code de falha, ou None quando o pre-flight passa."""
    ctx = sessao.ctx
    caminhos = _caminhos_preflight(sessao.caminhos)
    hr.start_step(
        ctx, "preflight", mensagem="Oracle Client e ambiente (Oracle/Python/paths)"
    )
    # Como no run.ps1: o check Oracle so roda com o cliente local validado.
    oracle = _resultado_oracle() if _checar_cliente_oracle(ctx) else None
    passou = oracle is not None and _pre_flight_automacao(
        ctx, caminhos, checar_oracle=True, oracle=oracle
    )
    hr.complete_step(ctx, ok=passou)
    return None if passou else _codigo_falha_preflight(ctx, caminhos, oracle)


def _linha_expirada(linha: str, corte: date) -> bool:
    """True quando o ts do evento e anterior ao corte da retencao."""
    casamento = _PADRAO_TS.match(linha)
    if casamento is None:
        return False
    try:
        return date.fromisoformat(casamento.group(1)) < corte
    except ValueError:
        return False


def _rotacionar_log(caminho: Path, dias: int = RETENCAO_LOG_DIAS) -> None:
    """Remove do jsonl os eventos anteriores a retencao (Invoke-LogRotation)."""
    if not caminho.exists():
        return
    corte = date.today() - timedelta(days=dias)
    with contextlib.suppress(OSError, ValueError):
        conteudo = caminho.read_text(encoding="utf-8-sig")
        linhas = [linha.rstrip("\r") for linha in conteudo.split("\n") if linha.strip()]
        mantidas = [linha for linha in linhas if not _linha_expirada(linha, corte)]
        if len(mantidas) == len(linhas):
            return
        temporario = caminho.with_name(caminho.name + ".tmp")
        with temporario.open("w", encoding="utf-8-sig", newline="\r\n") as arquivo:
            arquivo.write("".join(f"{linha}\n" for linha in mantidas))
        os.replace(temporario, caminho)


def _remover(caminho: Path) -> None:
    """Remove um arquivo se existir; falha de remocao e ignorada, como no run.ps1."""
    with contextlib.suppress(OSError):
        caminho.unlink(missing_ok=True)


def _extrair(sessao: _Sessao) -> hr.PythonStepResult:
    """Etapa extract: extract_oracle.py, com stdout como dado (IPC stdio)."""
    ctx = sessao.ctx
    hr.start_step(ctx, "extract", mensagem=f"Extraindo dados via {MOTOR_EXTRACAO}")
    spec = hr.PythonStepSpec(
        python_exe=sys.executable,
        script_path=str(sessao.caminhos.extract_py),
        operation_name="Extracao Oracle",
        step="extract",
        max_attempts=TENTATIVAS_EXTRACAO,
        backoff_seconds=BACKOFF_EXTRACAO,
        stdout_is_data=True,
    )
    resultado = hr.run_python_step(ctx, spec)
    ok = resultado.success or resultado.idempotent
    if ok:
        sessao.resultado_fresco = True
    hr.complete_step(ctx, ok=ok)
    return resultado


def _falha_extracao(sessao: _Sessao, extracao: hr.PythonStepResult) -> int:
    """Falha definitiva da extracao: alerta por e-mail e codigo canonico do Orchestrator."""
    codigo = hr.resolve_oracle_failure_exit_code(
        extracao.exit_code, default_exit_code=EXIT_FALHA_EXTRACAO
    )
    tentativas = 1 if extracao.non_retryable else TENTATIVAS_EXTRACAO
    ultimo_erro = f"Falha na extracao Oracle (PythonExit={extracao.exit_code})."
    if sessao.dry_run:
        hr.log(
            sessao.ctx,
            "[DRY-RUN] Alerta de falha nao enviado: " + ultimo_erro,
            "WARN",
            step="extract",
        )
    else:
        hr.send_failure_alert(
            sessao.ctx,
            task_name=AUTOMACAO,
            ultimo_erro=ultimo_erro,
            tentativas=tentativas,
        )
    return _encerrar(
        sessao,
        codigo,
        f"Falha definitiva na extracao Oracle ({MOTOR_EXTRACAO}) "
        f"(PythonExit={extracao.exit_code}).",
    )


def _transformar(sessao: _Sessao, entrada: str) -> str:
    """Etapa transform: generate_html_report.py recebe o JSON do extract pela entrada."""
    ctx = sessao.ctx
    hr.start_step(ctx, "transform", mensagem="Gerando HTML visual moderno")
    spec = hr.PythonStepSpec(
        python_exe=sys.executable,
        script_path=str(sessao.caminhos.generate_py),
        operation_name="Geracao HTML",
        step="transform",
        max_attempts=TENTATIVAS_TRANSFORM,
        backoff_seconds=BACKOFF_TRANSFORM,
        input_data=entrada,
        stdout_is_data=True,
    )
    resultado = hr.run_python_step(ctx, spec)
    hr.complete_step(ctx, ok=resultado.success)
    if not resultado.success:
        raise _ErroFatal("Falha definitiva na geracao do HTML.")
    if not resultado.output.strip():
        raise _ErroFatal("Geracao HTML retornou conteudo vazio.")
    return resultado.output


def _ler_config(caminho: Path) -> dict[str, Any]:
    """Le receitas_config.json (ConvertFrom-Json)."""
    dados: object = json.loads(caminho.read_text(encoding="utf-8-sig"))
    if not isinstance(dados, dict):
        raise _ErroFatal(f"{caminho.name} invalido: a raiz nao e um objeto JSON.")
    return dados


def _dados_email(config: dict[str, Any]) -> tuple[str, str, str]:
    """Prefixo do assunto, texto de introducao e destinatario de fallback do bloco 'email'."""
    email = config.get("email")
    if not isinstance(email, dict):
        raise _ErroFatal("receitas_config.json sem o bloco 'email'.")
    return (
        str(email.get("subject_prefix", "")),
        str(email.get("intro_text", "")),
        str(email.get("to", "")),
    )


def _tentar_envio(
    ctx: hr.HubRunContext, *, to: str, subject: str, html_body: str
) -> str | None:
    """Uma tentativa de envio pela CLI. None quando confirmado; senao, a causa."""
    try:
        enviado = hr.send_outlook_email(
            ctx, to=to, subject=subject, html_body=html_body
        )
    except OSError as exc:
        return f"excecao no envio: {exc}"
    return None if enviado else "Send-OutlookEmail retornou false."


def _enviar_com_retry(
    ctx: hr.HubRunContext, *, to: str, subject: str, html_body: str
) -> bool:
    """Envio com 2 tentativas e backoff 15/30 (Invoke-WithRetry do run.ps1)."""
    operacao = "Envio E-mail Outlook"
    for tentativa in range(1, TENTATIVAS_EMAIL + 1):
        if tentativa > 1:
            hr.retry_attempt(
                ctx,
                "dispatch",
                attempt=tentativa,
                max_attempts=TENTATIVAS_EMAIL,
                nivel="WARN",
                mensagem=f"{operacao} - tentativa {tentativa}/{TENTATIVAS_EMAIL}",
            )
        falha = _tentar_envio(ctx, to=to, subject=subject, html_body=html_body)
        if falha is None:
            if tentativa > 1:
                hr.retry_attempt(
                    ctx,
                    "dispatch",
                    attempt=tentativa,
                    max_attempts=TENTATIVAS_EMAIL,
                    nivel="INFO",
                    mensagem=f"{operacao} - sucesso apos {tentativa} tentativa(s)",
                )
            return True
        if tentativa >= TENTATIVAS_EMAIL:
            hr.retry_attempt(
                ctx,
                "dispatch",
                attempt=tentativa,
                max_attempts=TENTATIVAS_EMAIL,
                nivel="ERRO",
                mensagem=(
                    f"{operacao} - todas as {TENTATIVAS_EMAIL} tentativas falharam. "
                    f"Ultimo erro: {falha}"
                ),
            )
            return False
        espera = BACKOFF_EMAIL[min(tentativa - 1, len(BACKOFF_EMAIL) - 1)]
        hr.retry_attempt(
            ctx,
            "dispatch",
            attempt=tentativa,
            max_attempts=TENTATIVAS_EMAIL,
            nivel="WARN",
            mensagem=(
                f"{operacao} - falha na tentativa {tentativa}/{TENTATIVAS_EMAIL}: "
                f"{falha} Aguardando {espera}s."
            ),
        )
        _aguardar(espera)
    return False


def _despachar(sessao: _Sessao, html: str) -> None:
    """Etapa dispatch: idempotencia granular por canal e envio do e-mail oficial."""
    ctx = sessao.ctx
    caminhos = sessao.caminhos
    hr.log(
        ctx,
        "Verificando estado de notificacoes (Idempotencia Granular)...",
        step="dispatch",
    )
    hash_atual = hr.get_last_content_hash(
        caminhos.estado_tmp, caminhos.estado, on_warning=_aviso(ctx)
    )
    estado = hr.read_delivery_state(
        caminhos.entrega, [CANAL_EMAIL], on_warning=_aviso(ctx)
    )
    if hr.update_delivery_state_hash(estado, hash_atual):
        hr.log(
            ctx,
            f"Novo Hash detectado ({hash_atual}). Resetando status de entrega.",
            step="dispatch",
        )
    if not hr.delivery_pending(estado, CANAL_EMAIL, hash_atual):
        hr.log(
            ctx,
            "Conteudo identico ao ultimo envio e ja entregue. Suprimindo.",
            step="dispatch",
        )
        return
    hr.log(ctx, "Enviando e-mail oficial via Outlook COM...", step="dispatch")
    prefixo, intro, destino_config = _dados_email(_ler_config(caminhos.config))
    assunto = f"{prefixo} - {datetime.now():%d/%m/%Y}"
    # RE_EMAIL_TO do .env tem prioridade; config.json e apenas fallback/placeholder.
    destinatario = os.environ.get("RE_EMAIL_TO", "").strip() or destino_config
    corpo = f"<p>{intro}</p>{html}"
    if sessao.dry_run:
        hr.log(
            ctx,
            f"[DRY-RUN] E-mail nao enviado. Destinatario={destinatario}; assunto={assunto}.",
            step="dispatch",
        )
        return
    if not _enviar_com_retry(ctx, to=destinatario, subject=assunto, html_body=corpo):
        raise _ErroFatal("Falha definitiva no envio do e-mail.")
    hr.log(
        ctx, "E-mail enviado com sucesso. Consolidando estado parcial.", step="dispatch"
    )
    hr.set_delivery_success(estado, CANAL_EMAIL)
    hr.save_delivery_state(estado, caminhos.entrega)


def _confirmar_estado(sessao: _Sessao) -> None:
    """Etapa commit: promove o .tmp a receitas_state.json (nao roda em dry-run)."""
    ctx = sessao.ctx
    hr.start_step(ctx, "commit", mensagem="Confirmando compromisso de estado")
    tmp = sessao.caminhos.estado_tmp
    if tmp.exists():
        if sessao.dry_run:
            hr.log(
                ctx,
                "[DRY-RUN] Commit de estado nao executado: o .tmp seria promovido "
                "a receitas_state.json.",
                step="commit",
            )
        else:
            hr.log(
                ctx,
                "Confirmando compromisso de estado (Commit Success)...",
                step="commit",
            )
            os.replace(tmp, sessao.caminhos.estado)
    hr.complete_step(ctx)


def _encerrar(sessao: _Sessao, codigo: int, mensagem: str) -> int:
    """Unico ponto de saida: fecha a execucao e a telemetria, como Exit-WithCode."""
    resultado = sessao.caminhos.resultado if sessao.resultado_fresco else None
    return hr.finish(sessao.ctx, codigo, mensagem, record_counts_path=resultado)


def _fluxo(sessao: _Sessao) -> int:
    """Etapas extract, transform, dispatch e commit, executadas dentro do lock."""
    ctx = sessao.ctx
    _rotacionar_log(ctx.log_path)
    _remover(sessao.caminhos.resultado)
    extracao = _extrair(sessao)
    if extracao.idempotent:
        hr.log(
            ctx,
            "Extrator detectou que nao ha alteracoes relevantes (Idempotencia). Encerrando.",
        )
        return _encerrar(sessao, 0, "Processo finalizado (Idempotencia Extrator).")
    if not extracao.success:
        return _falha_extracao(sessao, extracao)
    if not extracao.output.strip():
        raise _ErroFatal("Extracao retornou dados vazios.")
    html = _transformar(sessao, extracao.output)
    hr.start_step(ctx, "dispatch", mensagem="E-mail oficial via Outlook COM")
    _despachar(sessao, html)
    hr.complete_step(ctx, ok=True)
    _confirmar_estado(sessao)
    return _encerrar(sessao, 0, "Processo concluido com sucesso.")


def _com_lock(sessao: _Sessao) -> int:
    """Executa o fluxo protegido pelo mutex RE-03 (Enter/Exit-AutomationLock)."""
    ctx = sessao.ctx
    hr.start_step(ctx, "lock", mensagem="Adquirindo lock global")
    with hr.AutomationMutex(CHAVE_LOCK, on_warning=_aviso(ctx, "lock")):
        hr.log(
            ctx,
            f"Lock global adquirido com sucesso (Mutex: {hr.nome_mutex(CHAVE_LOCK)}).",
            "DEBUG",
            step="lock",
        )
        hr.complete_step(ctx)
        return _fluxo(sessao)


def executar(
    ctx: hr.HubRunContext, caminhos: Caminhos, *, dry_run: bool = False
) -> int:
    """Roda o fluxo completo e devolve o exit code (quem chama faz sys.exit)."""
    sessao = _Sessao(ctx=ctx, caminhos=caminhos, dry_run=dry_run)
    tmp_existia = caminhos.estado_tmp.exists()
    hr.execution_start(ctx, f"INICIO — {AUTOMACAO} (RE-03). ExecId={ctx.exec_id}")
    if dry_run:
        hr.log(
            ctx,
            "[DRY-RUN] Validacao manual: nenhum e-mail sera enviado e o estado "
            "nao sera confirmado.",
            "WARN",
        )
    try:
        codigo_preflight = _preflight(sessao)
        if codigo_preflight is not None:
            return _encerrar(
                sessao,
                codigo_preflight,
                "FALHA NO PRE-FLIGHT CHECK. Abortando execucao.",
            )
        return _com_lock(sessao)
    # Residual: as falhas esperadas (_ErroFatal, LockTimeoutError, OSError, ValueError) e
    # qualquer outra (KeyError, RuntimeError...) recebem o mesmo fim do catch
    # [System.Exception] do run.ps1: ERRO FATAL, exit 1 e fechamento da execucao. Sem isso a
    # excecao escapa sem execution.end nem telemetria. O lock ja foi liberado pelo with.
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return _encerrar(sessao, EXIT_ERRO_FATAL, f"ERRO FATAL: {exc}")
    finally:
        if dry_run and not tmp_existia:
            _remover(caminhos.estado_tmp)


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada: ``run_receitas.py [ExecId] [--dry-run]``. Devolve o exit code."""
    ensure_utf8_streams()
    argumentos = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in argumentos
    posicionais = [arg for arg in argumentos if arg != "--dry-run"]
    hr.load_env_file(RAIZ)
    ctx = hr.create_run_context(
        hr.AutomationSpec(
            automacao=AUTOMACAO,
            slug=SLUG_LOG,
            trace_slug=SLUG_TRACE,
            lock_key=CHAVE_LOCK,
            log_dir=RE_DIR / "Logs",
            non_failure_codes=(0,),
        ),
        exec_id=posicionais[0] if posicionais else "",
        telemetry=_telemetria_padrao(RAIZ),
        project_root=RAIZ,
    )
    return executar(ctx, Caminhos.da_pasta(RE_DIR), dry_run=dry_run)


if __name__ == "__main__":
    sys.exit(main())
