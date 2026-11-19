"""Motor compartilhado dos runners de OBs paginadas em cards PNG (OFST-06 e ORB-07).

Reproduz o fluxo comum sobre ``hub_runner`` e ``hub_whatsapp``:
1. pre-flight (disco, paths, Oracle em queue/endpoint e whatsapp-config.json);
2. lock global por automacao, rotacao UTF-8 sem BOM do log e limpeza de artefatos;
3. extract (3 tentativas; exit 2 reconcilia ``.tmp`` sem enviar e sai com 2);
4. transform (``format_message.py`` sem retry e leitura do ``cards_manifest.json``);
5. dispatch (AUTO com 1 card, BATCH com varios + reconciliacao parcial);
6. commit (``<prefixo>_state.json.tmp`` -> ``<prefixo>_state.json``).
"""

# pylint: disable=import-error
from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import hub_runner as hr
import hub_whatsapp as hw
from automation_log import ensure_utf8_streams

EXIT_ERRO_FATAL_PREFLIGHT: Final[int] = 1
EXIT_NADA_A_NOTIFICAR: Final[int] = 2
EXIT_FALHA_EXTRACAO: Final[int] = 3
EXIT_FALHA_ORQUESTRACAO: Final[int] = 4
EXIT_REAUTENTICACAO: Final[int] = 21
EXIT_ADIADO: Final[int] = 22
CODIGOS_SEM_FALHA: Final[tuple[int, ...]] = (0, EXIT_NADA_A_NOTIFICAR, EXIT_ADIADO)
TENTATIVAS_EXTRACAO: Final[int] = 3
BACKOFF_EXTRACAO: Final[tuple[int, ...]] = (30, 60, 120)
RETENCAO_LOG_DIAS: Final[int] = hr.RETENCAO_LOG_DIAS_PADRAO
MODO_UNICO: Final[str] = "AUTO"
MODO_LOTE: Final[str] = "BATCH"


@dataclass(frozen=True)
class ObsCardsSpec:
    """Parametros que distinguem cada automacao de cards (OFST-06 ou ORB-07)."""

    automacao: str
    chave_lock: str
    slug_log: str
    slug_trace: str
    prefixo: str


@dataclass(frozen=True)
class Caminhos:  # pylint: disable=too-many-instance-attributes
    """Arquivos lidos e gravados pela automacao na sua pasta e envio na raiz."""

    pasta: Path
    extract_py: Path
    format_py: Path
    config_wa: Path
    send_wa: Path
    estado: Path
    estado_tmp: Path
    resultado: Path
    manifesto: Path
    mensagem: Path
    card: Path
    batch_input: Path
    batch_result: Path

    @classmethod
    def da_pasta(cls, pasta: Path, raiz: Path, *, prefixo: str) -> Caminhos:
        """Caminhos padrao da automacao a partir da pasta, raiz e prefixo de arquivo."""
        return cls(
            pasta=pasta,
            extract_py=pasta / f"extract_{prefixo}.py",
            format_py=pasta / "format_message.py",
            config_wa=pasta / "whatsapp-config.json",
            send_wa=raiz / "lib" / "Send-WhatsApp.ps1",
            estado=pasta / f"{prefixo}_state.json",
            estado_tmp=pasta / f"{prefixo}_state.json.tmp",
            resultado=pasta / f"{prefixo}_result.json",
            manifesto=pasta / "cards_manifest.json",
            mensagem=pasta / "message.txt",
            card=pasta / "card.png",
            batch_input=pasta / "batch_input.json",
            batch_result=pasta / "batch_result.json",
        )


@dataclass
class _Sessao:  # pylint: disable=too-many-instance-attributes
    """Estado de uma execucao: contexto de log, spec, arquivos e confirmacao."""

    ctx: hr.HubRunContext
    caminhos: Caminhos
    spec: ObsCardsSpec = ObsCardsSpec("", "", "", "", "")
    dry_run: bool = False
    resultado_fresco: bool = False
    estado_confirmado: bool = False
    encerrada: bool = False
    config_wa: dict[str, Any] = field(default_factory=dict)
    destino_mascarado: str = ""
    cards: tuple[hw.CardPagina, ...] = ()


def mascarar_destino(valor: str) -> str:
    """Destinatario para o log de dry-run: so os 4 ultimos caracteres aparecem."""
    return "***" + valor[-4:] if len(valor) > 4 else "***"


def _caminhos_preflight(caminhos: Caminhos) -> tuple[Path, ...]:
    """Interpretador e scripts/configs que o pre-flight confere."""
    return (
        Path(sys.executable),
        caminhos.extract_py,
        caminhos.format_py,
        caminhos.config_wa,
    )


def _checar_whatsapp(sessao: _Sessao) -> bool:
    """Pre-flight do WhatsApp: config legivel e destino resolvido."""
    caminho = sessao.caminhos.config_wa
    try:
        config = hw.read_whatsapp_config(caminho)
        destino = hw.resolve_whatsapp_target(config.get("target"), caminho)
    except (OSError, ValueError) as exc:
        hr.log(
            sessao.ctx, f"Pre-Flight WhatsApp falhou: {exc}", "ERRO", step="preflight"
        )
        return False
    sessao.config_wa = config
    sessao.destino_mascarado = mascarar_destino(destino)
    return True


def _demais_checks(sessao: _Sessao, caminhos: Caminhos) -> bool:
    """Outros checks do pre-flight sem o worker Oracle (paths, disco e WhatsApp)."""
    return hr.run_preflight(sessao.ctx, _caminhos_preflight(caminhos)) and (
        _checar_whatsapp(sessao)
    )


def _preflight(sessao: _Sessao) -> int | None:
    """Etapa preflight: devolve exit code de falha ou None se passar."""
    ctx = sessao.ctx
    caminhos = _caminhos_preflight(sessao.caminhos)
    hr.start_step(ctx, "preflight", mensagem="Oracle, Python e WhatsApp configurados")
    oracle = hr.oracle_preflight_from_env()
    passou = hr.run_preflight(ctx, caminhos, oracle) and _checar_whatsapp(sessao)
    hr.complete_step(ctx, ok=passou)
    if passou:
        return None
    return hr.oracle_preflight_exit_code(
        oracle, outros_checks=lambda: _demais_checks(sessao, sessao.caminhos)
    )


def _limpar_artefatos(caminhos: Caminhos) -> None:
    """Remove artefatos residuais antes da extracao (dentro do lock)."""
    for arquivo in (
        caminhos.resultado,
        caminhos.estado_tmp,
        caminhos.mensagem,
        caminhos.card,
        caminhos.manifesto,
        caminhos.batch_input,
        caminhos.batch_result,
    ):
        hr.remove_quietly(arquivo)
    for cartao in caminhos.pasta.glob("card_*.png"):
        hr.remove_quietly(cartao)


def _encerrar(sessao: _Sessao, codigo: int, mensagem: str) -> int:
    """Unico ponto de saida: fecha a execucao e a telemetria."""
    sessao.encerrada = True
    resultado = sessao.caminhos.resultado if sessao.resultado_fresco else None
    return hr.finish(sessao.ctx, codigo, mensagem, record_counts_path=resultado)


def _promover_state(sessao: _Sessao) -> None:
    """Promove ``.tmp`` ao arquivo de estado definitivo (somente fora do dry-run)."""
    os.replace(sessao.caminhos.estado_tmp, sessao.caminhos.estado)


def _avisar_commit_dry_run(sessao: _Sessao) -> None:
    """Dry-run: informa que o commit do state foi pulado."""
    hr.log(
        sessao.ctx,
        "[DRY-RUN] Commit de estado nao executado: o .tmp seria promovido a "
        f"{sessao.caminhos.estado.name}.",
        step="commit",
    )


def _encerrar_idempotente(sessao: _Sessao) -> int:
    """Extract idempotente (exit 2): reconcilia o ``.tmp`` sem envio e sai com 2."""
    ctx = sessao.ctx
    if sessao.caminhos.estado_tmp.exists():
        hr.start_step(ctx, "commit", mensagem="Reconciliando state sem envio")
        if sessao.dry_run:
            _avisar_commit_dry_run(sessao)
        else:
            _promover_state(sessao)
            hr.log(ctx, "State reconciliado sem necessidade de envio.", step="commit")
        hr.complete_step(ctx)
    return _encerrar(
        sessao,
        EXIT_NADA_A_NOTIFICAR,
        "Nenhuma OB nova com estoque suficiente — nada a notificar.",
    )


def _etapa_extracao(sessao: _Sessao) -> int | None:
    """Etapa extract: ``extract_<prefixo>.py`` com 3 tentativas. None segue ao transform."""
    ctx = sessao.ctx
    hr.start_step(ctx, "extract", mensagem="Extracao Oracle + validacao de estoque")
    resultado = hr.run_python_step(
        ctx,
        hr.PythonStepSpec(
            python_exe=sys.executable,
            script_path=str(sessao.caminhos.extract_py),
            operation_name=f"Extracao {sessao.spec.automacao} ({sessao.caminhos.extract_py.name})",
            step="extract",
            max_attempts=TENTATIVAS_EXTRACAO,
            backoff_seconds=BACKOFF_EXTRACAO,
        ),
    )
    ok = resultado.success or resultado.idempotent
    if ok:
        sessao.resultado_fresco = True
    hr.complete_step(ctx, ok=ok)
    if resultado.idempotent:
        return _encerrar_idempotente(sessao)
    if not resultado.success:
        codigo = hr.resolve_oracle_failure_exit_code(
            resultado.exit_code, default_exit_code=EXIT_FALHA_EXTRACAO
        )
        return _encerrar(
            sessao,
            codigo,
            f"Falha definitiva na extracao Oracle (PythonExit={resultado.exit_code}).",
        )
    return None


def executar_formatador(ctx: hr.HubRunContext, caminhos: Caminhos) -> int:
    """Roda ``format_message.py`` como processo filho via ``hub_runner.run_python_script``."""
    return hr.run_python_script(
        ctx,
        python_exe=sys.executable,
        script_path=caminhos.format_py,
        step="transform",
        cwd=caminhos.pasta,
    )


def _etapa_formatacao(sessao: _Sessao) -> int | None:
    """Etapa transform: cards PNG e manifesto. None segue para o dispatch."""
    ctx = sessao.ctx
    caminhos = sessao.caminhos
    hr.start_step(
        ctx,
        "transform",
        mensagem="Gerando card(s) PNG e cards_manifest.json (format_message.py)",
    )
    codigo = executar_formatador(ctx, caminhos)
    if codigo == EXIT_NADA_A_NOTIFICAR:
        hr.complete_step(ctx, ok=True)
        return _encerrar(
            sessao,
            EXIT_NADA_A_NOTIFICAR,
            "Nenhuma OB qualificada — mensagem nao gerada.",
        )
    if codigo != 0:
        hr.complete_step(ctx, ok=False)
        return _encerrar(
            sessao,
            EXIT_FALHA_ORQUESTRACAO,
            f"Falha em format_message.py. ExitCode={codigo}",
        )
    manifesto = hw.read_cards_manifest(
        caminhos.manifesto,
        caminhos.pasta,
        message_file=str(caminhos.mensagem),
        card_file=str(caminhos.card),
    )
    hr.complete_step(ctx, ok=manifesto.valid)
    if not manifesto.valid:
        return _encerrar(sessao, EXIT_FALHA_ORQUESTRACAO, manifesto.error)
    sessao.cards = manifesto.cards
    return None


def _avisar_envio_desabilitado(sessao: _Sessao) -> int:
    """WhatsApp desabilitado na configuracao: nada enviado, sem commit (exit 2)."""
    ctx = sessao.ctx
    hr.log(
        ctx,
        "Envio WhatsApp desabilitado na configuracao "
        f"({sessao.caminhos.config_wa}). State NAO commitado.",
        "WARN",
        step="dispatch",
    )
    hr.complete_step(ctx, ok=True)
    return _encerrar(
        sessao,
        EXIT_NADA_A_NOTIFICAR,
        "Envio WhatsApp desabilitado na configuracao — nada enviado e state preservado.",
    )


def _dry_run_envio(sessao: _Sessao) -> int:
    """Dry-run do dispatch: prepara lote sem enviar, loga o que faria e nao commita."""
    ctx = sessao.ctx
    cards = sessao.cards
    modo = MODO_LOTE if len(cards) > 1 else MODO_UNICO
    if modo == MODO_LOTE:
        hw.write_whatsapp_batch_input(
            cards, sessao.caminhos.pasta, sessao.caminhos.batch_input
        )
    hr.log(
        ctx,
        f"[DRY-RUN] Envio WhatsApp nao executado: enviaria {len(cards)} card(s) em "
        f"modo {modo} ao destino {sessao.destino_mascarado}.",
        step="dispatch",
    )
    hr.complete_step(ctx)
    hr.start_step(ctx, "commit", mensagem="Confirmando compromisso de estado")
    if sessao.caminhos.estado_tmp.exists():
        _avisar_commit_dry_run(sessao)
    hr.complete_step(ctx)
    return _encerrar(
        sessao,
        0,
        "[DRY-RUN] Validacao manual concluida: nenhum envio e nenhum commit de estado.",
    )


def _enviar_whatsapp(sessao: _Sessao, modo: str) -> int:
    """Aciona ``Send-WhatsApp.ps1`` e devolve o exit code."""
    caminhos = sessao.caminhos
    lote = modo == MODO_LOTE
    return hw.send_whatsapp(
        sessao.ctx,
        script=caminhos.send_wa,
        work_dir=caminhos.pasta,
        mode=modo,
        config_path=caminhos.config_wa,
        batch_input_file=caminhos.batch_input if lote else None,
        batch_result_file=caminhos.batch_result if lote else None,
        step="dispatch",
    )


def _saida_reauth_ou_adiado(sessao: _Sessao, codigo: int) -> int | None:
    """Exit 21 (reautenticacao) e 22 (adiado por lock/cooldown). None nos demais."""
    if codigo == EXIT_REAUTENTICACAO:
        return _encerrar(sessao, EXIT_REAUTENTICACAO, "WhatsApp requer reautenticacao.")
    if codigo == EXIT_ADIADO:
        return _encerrar(
            sessao,
            EXIT_ADIADO,
            "WhatsApp adiado por lock ou cooldown da sessao hub-global.",
        )
    return None


def _commit_idempotencia(sessao: _Sessao) -> int:
    """Commit da idempotencia somente apos envio confirmado (exit 0)."""
    ctx = sessao.ctx
    hr.start_step(ctx, "commit", mensagem="Commit da idempotencia")
    if sessao.caminhos.estado_tmp.exists():
        _promover_state(sessao)
        hr.log(ctx, "State de OBs notificadas commitado.", step="commit")
    hr.complete_step(ctx)
    return _encerrar(
        sessao, 0, f"Execucao concluida com sucesso ({len(sessao.cards)} card(s))."
    )


def _envio_unico(sessao: _Sessao) -> int:
    """Um card: ``Send-WhatsApp.ps1`` em modo AUTO."""
    ctx = sessao.ctx
    codigo = _enviar_whatsapp(sessao, MODO_UNICO)
    hr.log(ctx, f"Motor WhatsApp ExitCode={codigo}", step="dispatch")
    hr.complete_step(ctx, ok=codigo in (0, EXIT_ADIADO))
    saida = _saida_reauth_ou_adiado(sessao, codigo)
    if saida is not None:
        return saida
    if codigo != 0:
        return _encerrar(
            sessao,
            EXIT_FALHA_ORQUESTRACAO,
            f"Falha no envio WhatsApp (ExitCode={codigo}). State NAO commitado — "
            "as OBs serao reavaliadas na proxima execucao.",
        )
    sessao.estado_confirmado = True
    return _commit_idempotencia(sessao)


def _envio_parcial(sessao: _Sessao, entrega: hw.EntregaWhatsApp, codigo: int) -> int:
    """Envio parcial do lote: commit parcial do state e ajuste de ``record_counts``."""
    ctx = sessao.ctx
    caminhos = sessao.caminhos
    if caminhos.estado_tmp.exists():
        hr.start_step(ctx, "commit", mensagem="Commit parcial da idempotencia")
        _promover_state(sessao)
        sessao.estado_confirmado = True
        hr.log(
            ctx,
            f"State parcial commitado: {entrega.sent_count}/{entrega.total_count} "
            f"pagina(s) entregue(s); {entrega.failed_ob_count} OB(s) mantida(s) para reenvio.",
            "WARN",
            step="commit",
        )
        hr.complete_step(ctx)
    try:
        hw.update_whatsapp_result_record_counts(
            caminhos.resultado,
            entrega.delivered_ob_count,
            entrega.sent_count,
            entrega.total_count,
        )
    except (OSError, ValueError) as exc:
        hr.log(
            ctx,
            f"Aviso: falha ao ajustar record_counts parcial em {caminhos.resultado}: {exc}",
            "WARN",
            step="dispatch",
        )
    if codigo == EXIT_REAUTENTICACAO:
        return _encerrar(
            sessao,
            EXIT_REAUTENTICACAO,
            "WhatsApp requer reautenticacao apos envio parcial "
            f"({entrega.sent_count}/{entrega.total_count} paginas).",
        )
    return _encerrar(
        sessao,
        EXIT_FALHA_ORQUESTRACAO,
        f"Envio WhatsApp parcial ({entrega.sent_count}/{entrega.total_count} paginas "
        f"entregues, ExitCode={codigo}). OBs das paginas com falha serao reavaliadas na "
        "proxima execucao.",
    )


def _falha_lote_sem_envio(
    sessao: _Sessao, entrega: hw.EntregaWhatsApp, codigo: int
) -> int:
    """Lote sem nenhuma pagina entregue: 21 e 22 saem direto; o resto vira exit 4."""
    saida = _saida_reauth_ou_adiado(sessao, codigo)
    if saida is not None:
        return saida
    return _encerrar(
        sessao,
        EXIT_FALHA_ORQUESTRACAO,
        f"Falha no envio WhatsApp em lote (ExitCode={codigo}, 0/{entrega.total_count} "
        "paginas entregues). State NAO commitado — as OBs serao reavaliadas na proxima "
        "execucao.",
    )


def _envio_lote(sessao: _Sessao) -> int:
    """Varios cards: ``Send-WhatsApp.ps1`` em modo BATCH e reconciliacao do lote."""
    ctx = sessao.ctx
    caminhos = sessao.caminhos
    hw.write_whatsapp_batch_input(sessao.cards, caminhos.pasta, caminhos.batch_input)
    codigo = _enviar_whatsapp(sessao, MODO_LOTE)
    hr.log(ctx, f"Motor WhatsApp ExitCode={codigo}", step="dispatch")
    entrega = hw.resolve_whatsapp_batch_delivery(
        sessao.cards,
        caminhos.batch_result,
        caminhos.estado_tmp,
        wa_exit_code=codigo,
        on_warn=hr.warn_logger(ctx, "dispatch"),
    )
    sem_envio_adiado = entrega.status == "NoneSent" and codigo == EXIT_ADIADO
    hr.complete_step(ctx, ok=entrega.status == "AllSent" or sem_envio_adiado)
    if entrega.status == "PartialSent":
        return _envio_parcial(sessao, entrega, codigo)
    if entrega.status == "NoneSent":
        return _falha_lote_sem_envio(sessao, entrega, codigo)
    sessao.estado_confirmado = True
    return _commit_idempotencia(sessao)


def _etapa_envio(sessao: _Sessao) -> int:
    """Etapa dispatch conforme configuracao, dry-run e quantidade de cards."""
    ctx = sessao.ctx
    hr.start_step(
        ctx,
        "dispatch",
        mensagem=f"Enviando {len(sessao.cards)} card(s) ao grupo Expedicao Tinturaria",
    )
    if not hw.whatsapp_config_enabled(sessao.config_wa):
        return _avisar_envio_desabilitado(sessao)
    if sessao.dry_run:
        return _dry_run_envio(sessao)
    if len(sessao.cards) == 1:
        return _envio_unico(sessao)
    return _envio_lote(sessao)


def _limpar_tmp_sem_confirmacao(sessao: _Sessao) -> None:
    """Finally do fluxo protegido: remove ``.tmp`` quando o envio nao foi confirmado."""
    tmp = sessao.caminhos.estado_tmp
    if sessao.estado_confirmado or not tmp.exists():
        return
    hr.remove_quietly(tmp)
    if not sessao.encerrada:
        hr.log(sessao.ctx, f"Limpeza finally: {tmp} removido.", "DEBUG", step="cleanup")


def _fluxo(sessao: _Sessao) -> int:
    """Etapas extract, transform e dispatch dentro do lock."""
    hr.rotate_log(sessao.ctx.log_path, RETENCAO_LOG_DIAS)
    _limpar_artefatos(sessao.caminhos)
    codigo = _etapa_extracao(sessao)
    if codigo is None:
        codigo = _etapa_formatacao(sessao)
    if codigo is None:
        return _etapa_envio(sessao)
    return codigo


def _com_lock(sessao: _Sessao) -> int:
    """Executa o fluxo protegido pelo mutex da automacao."""
    ctx = sessao.ctx
    chave_lock = sessao.spec.chave_lock
    hr.start_step(ctx, "lock", mensagem="Adquirindo lock global")
    with hr.AutomationMutex(chave_lock, on_warning=hr.warn_logger(ctx, "lock")):
        hr.log(
            ctx,
            f"Lock global adquirido com sucesso (Mutex: {hr.nome_mutex(chave_lock)}).",
            "DEBUG",
            step="lock",
        )
        hr.complete_step(ctx)
        try:
            return _fluxo(sessao)
        finally:
            _limpar_tmp_sem_confirmacao(sessao)


def executar(
    ctx: hr.HubRunContext,
    caminhos: Caminhos,
    spec: ObsCardsSpec,
    *,
    dry_run: bool = False,
    aviso_env: str | None = None,
) -> int:
    """Roda o fluxo completo e devolve o exit code."""
    sessao = _Sessao(ctx=ctx, caminhos=caminhos, spec=spec, dry_run=dry_run)
    hr.execution_start(
        ctx, f"INICIO — {spec.automacao} ({spec.chave_lock}). ExecId={ctx.exec_id}"
    )
    if aviso_env is not None:
        hr.log(
            ctx, f"Aviso: falha ao carregar .env: {aviso_env}", "WARN", step="preflight"
        )
    if dry_run:
        hr.log(
            ctx,
            "[DRY-RUN] Validacao manual: nenhum envio de WhatsApp sera feito e o state "
            "nao sera confirmado.",
            "WARN",
        )
    # Residual: falha inesperada no pre-flight sai com 1 e fecha execucao/telemetria.
    try:
        codigo_preflight = _preflight(sessao)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return _encerrar(sessao, EXIT_ERRO_FATAL_PREFLIGHT, f"ERRO FATAL: {exc}")
    if codigo_preflight is not None:
        return _encerrar(
            sessao, codigo_preflight, "FALHA NO PRE-FLIGHT CHECK. Abortando."
        )
    # Residual: lock ocupado ou excecao de etapa dentro do fluxo sai com 4 (mutex ja liberado).
    try:
        return _com_lock(sessao)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return _encerrar(
            sessao, EXIT_FALHA_ORQUESTRACAO, f"Falha critica na orquestracao: {exc}"
        )


def rodar_cli(
    spec: ObsCardsSpec,
    pasta: Path,
    raiz: Path,
    argv: Sequence[str] | None = None,
) -> int:
    """Ponto de entrada CLI ``run_<prefixo>.py [ExecId] [--dry-run]``."""
    ensure_utf8_streams()
    argumentos = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in argumentos
    posicionais = [arg for arg in argumentos if arg != "--dry-run"]
    aviso_env = hr.load_env_file(raiz)
    ctx = hr.create_run_context(
        hr.AutomationSpec(
            automacao=spec.automacao,
            slug=spec.slug_log,
            trace_slug=spec.slug_trace,
            lock_key=spec.chave_lock,
            log_dir=pasta / "Logs",
            non_failure_codes=CODIGOS_SEM_FALHA,
        ),
        exec_id=posicionais[0] if posicionais else "",
        telemetry=hr.default_telemetry(raiz),
        project_root=raiz,
    )
    caminhos = Caminhos.da_pasta(pasta, raiz, prefixo=spec.prefixo)
    return executar(ctx, caminhos, spec, dry_run=dry_run, aviso_env=aviso_env)
