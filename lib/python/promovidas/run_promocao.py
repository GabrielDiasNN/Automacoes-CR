"""CLI unificada para execucao de consultas promovidas (Modelo 2)."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

import hub_runner as hr
import hub_whatsapp as hw
import oracle_extract

from . import card, config, estado, extracao, regras, snapshot

RETENCAO_LOG_DIAS: Final[int] = 14
CODIGOS_SEM_FALHA: Final[tuple[int, ...]] = (0, 2, 22)
EXIT_REAUTENTICACAO: Final[int] = 21
EXIT_ADIADO: Final[int] = 22
EXIT_FALHA_ORQUESTRACAO: Final[int] = 4


def _limpar_artefatos(pasta: Path) -> None:
    """Remove artefatos residuais de execucoes anteriores na pasta da promocao."""
    for nome in (
        "card.png",
        "message.txt",
        "cards_manifest.json",
        "batch_input.json",
        "batch_result.json",
        "seen_state.json.tmp",
    ):
        hr.remove_quietly(pasta / nome)
    for cartao in pasta.glob("card_*.png"):
        hr.remove_quietly(cartao)


def _resolver_destino_whatsapp(cfg: config.ConfigPromocao) -> tuple[str, str]:
    exc_cfg = cfg.excecao
    env_name = (
        "AUTOMACAO_ALERT_WHATSAPP"
        if cfg.modo == "sombra"
        else (exc_cfg.destino_whatsapp_env if exc_cfg else "AUTOMACAO_ALERT_WHATSAPP")
    )
    destino = os.environ.get(env_name, "").strip()
    if not destino:
        raise ValueError(
            f"Variavel de ambiente '{env_name}' nao definida para envio WhatsApp "
            f"(modo={cfg.modo})."
        )
    client_id = exc_cfg.client_id_whatsapp if exc_cfg else "hub-global"
    return destino, client_id


def _resultado_card_unico(exit_code: int) -> tuple[int, bool]:
    if exit_code == 0:
        return 0, True
    if exit_code in (EXIT_REAUTENTICACAO, EXIT_ADIADO):
        return exit_code, False
    return EXIT_FALHA_ORQUESTRACAO, False


def _resultado_lote(
    entrega: hw.EntregaWhatsApp, exit_code: int
) -> tuple[int, bool]:
    if entrega.status == "AllSent":
        return 0, True
    if entrega.status == "PartialSent":
        code_parcial = (
            EXIT_REAUTENTICACAO
            if exit_code == EXIT_REAUTENTICACAO
            else EXIT_FALHA_ORQUESTRACAO
        )
        return code_parcial, True
    if exit_code in (EXIT_REAUTENTICACAO, EXIT_ADIADO):
        return exit_code, False
    return EXIT_FALHA_ORQUESTRACAO, False


def _enviar_whatsapp(
    ctx: hr.HubRunContext,
    cfg: config.ConfigPromocao,
    pasta: Path,
    manifest_path: Path,
    state_tmp_path: Path,
) -> tuple[int, bool]:
    """Envia cards gerados via ``Send-WhatsApp.ps1`` e devolve (exit_code, commit_state)."""
    resultado = hw.read_cards_manifest(manifest_path, base_dir=pasta)
    if not resultado.valid or not resultado.cards:
        hr.log(ctx, f"Manifesto invalido: {resultado.error}", "ERROR", step="dispatch")
        return EXIT_FALHA_ORQUESTRACAO, False

    destino, client_id = _resolver_destino_whatsapp(cfg)
    batch_in = pasta / "batch_input.json"
    batch_out = pasta / "batch_result.json"
    hw.write_whatsapp_batch_input(resultado.cards, pasta, batch_in)

    exit_code = hw.send_whatsapp(
        ctx,
        script=ctx.raiz / "lib" / "Send-WhatsApp.ps1",
        work_dir=pasta,
        mode="BATCH",
        client_id=client_id,
        phone=destino,
        batch_input_file=batch_in,
        batch_result_file=batch_out,
        step="dispatch",
    )

    if len(resultado.cards) == 1:
        return _resultado_card_unico(exit_code)

    entrega = hw.resolve_whatsapp_batch_delivery(
        resultado.cards,
        batch_out,
        state_tmp_path,
        wa_exit_code=exit_code,
        on_warn=hr.warn_logger(ctx, "dispatch"),
    )
    return _resultado_lote(entrega, exit_code)


def _despachar_excecoes(
    ctx: hr.HubRunContext,
    cfg: config.ConfigPromocao,
    pasta: Path,
    excecoes: list[dict[str, Any]],
    *,
    dry_run: bool,
) -> int:
    if "whatsapp" not in cfg.destinos or cfg.excecao is None:
        return 0
    state_path = pasta / "seen_state.json"
    state_tmp_path = pasta / "seen_state.json.tmp"
    estado_atual = estado.ler_estado(state_path)
    pendentes, proximo_estado = estado.selecionar_pendentes(
        excecoes,
        cfg.chave,
        estado_atual,
        renotificar_apos_horas=cfg.excecao.renotificar_apos_horas,
    )
    if not pendentes:
        if not dry_run and proximo_estado != estado_atual:
            estado.gravar_estado(state_path, proximo_estado, exec_id=ctx.exec_id)
        hr.log(
            ctx, "Nenhuma excecao pendente de notificacao.", "INFO", step="transform"
        )
        return 0

    hr.start_step(
        ctx, "transform", mensagem=f"Gerando card(s) para {len(pendentes)} excecao(oes)"
    )
    _, _, manifest_path = card.gerar_artefatos_whatsapp(cfg, pendentes, pasta)
    hr.complete_step(ctx, ok=True)

    if dry_run:
        hr.log(ctx, "[DRY-RUN] Envio WhatsApp e commit de estado ignorados.", "INFO")
        return 0

    estado.gravar_estado(state_tmp_path, proximo_estado, exec_id=ctx.exec_id)
    hr.start_step(
        ctx, "dispatch", mensagem=f"Enviando alerta WhatsApp (modo={cfg.modo})"
    )
    try:
        code, commit = _enviar_whatsapp(ctx, cfg, pasta, manifest_path, state_tmp_path)
        hr.complete_step(ctx, ok=code in (0, EXIT_ADIADO))
        if commit and state_tmp_path.exists():
            os.replace(state_tmp_path, state_path)
        return code
    finally:
        hr.remove_quietly(state_tmp_path)


def _oracle_logger(ctx: hr.HubRunContext) -> Any:
    def _log(msg: str, level: str = "INFO", _exec_id: str = "") -> None:
        hr.log(ctx, msg, level, step="extract")

    return _log


def _executar_promocao(
    ctx: hr.HubRunContext,
    cfg: config.ConfigPromocao,
    pasta: Path,
    *,
    dry_run: bool,
) -> int:
    _limpar_artefatos(pasta)
    sql_path = pasta / cfg.consulta
    hr.start_step(ctx, "preflight", mensagem="Oracle e Python configurados")
    oracle_pf = hr.oracle_preflight_from_env()
    ok_pf = hr.run_preflight(
        ctx,
        [Path(sys.executable), sql_path],
        oracle=oracle_pf,
    )
    hr.complete_step(ctx, ok=ok_pf)
    if not ok_pf:
        return hr.oracle_preflight_exit_code(
            oracle_pf,
            outros_checks=lambda: hr.run_preflight(ctx, [Path(sys.executable), sql_path]),
        )

    hr.start_step(ctx, "extract", mensagem=f"Executando {cfg.consulta}")
    try:
        rows = extracao.executar_consulta_promovida(
            ctx.raiz,
            sql_path,
            automacao=cfg.nome,
            exec_id=ctx.exec_id,
            log_fn=_oracle_logger(ctx),
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        hr.complete_step(ctx, ok=False)
        hr.log(ctx, str(exc), "ERROR", step="extract")
        py_code = oracle_extract.classify_oracle_exit_code(exc)
        return hr.resolve_oracle_failure_exit_code(py_code, default_exit_code=3)
    hr.complete_step(ctx, ok=True)

    kpis = regras.calcular_kpis(rows, cfg.painel.kpis)
    excecoes = (
        regras.filtrar_excecoes(rows, cfg.excecao.condicoes) if cfg.excecao else []
    )
    snapshot.gravar_snapshot(ctx.raiz, cfg, rows, kpis, excecoes_count=len(excecoes))
    return _despachar_excecoes(ctx, cfg, pasta, excecoes, dry_run=dry_run)


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada: ``python -m promovidas.run_promocao --config <promocao.json> [ExecId] [--dry-run]``."""
    parser = argparse.ArgumentParser(description="Runner de consultas promovidas")
    parser.add_argument("--config", required=True, help="Caminho para promocao.json")
    parser.add_argument("exec_id", nargs="?", default="", help="ExecId do Orchestrator")
    parser.add_argument(
        "--dry-run", action="store_true", help="Nao envia nem grava state"
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    cfg_path = Path(args.config).resolve()
    pasta = cfg_path.parent
    raiz = Path(__file__).resolve().parents[3]
    hr.load_env_file(raiz)
    cfg = config.carregar_config(cfg_path)

    spec = hr.AutomationSpec(
        automacao=cfg.nome,
        slug=cfg.slug,
        trace_slug=cfg.slug,
        lock_key=f"PROM-{cfg.slug.upper()}",
        log_dir=raiz / "Logs",
        non_failure_codes=CODIGOS_SEM_FALHA,
    )
    ctx = hr.create_run_context(
        spec,
        exec_id=str(args.exec_id or ""),
        telemetry=hr.default_telemetry(raiz),
        project_root=raiz,
    )
    hr.rotate_log(ctx.log_path, dias=RETENCAO_LOG_DIAS)

    try:
        with hr.AutomationMutex(spec.lock_key):
            hr.execution_start(ctx, f"Iniciando promocao {cfg.slug} (modo={cfg.modo})")
            code = _executar_promocao(ctx, cfg, pasta, dry_run=args.dry_run)
            return hr.finish(ctx, code)
    except hr.LockTimeoutError as exc:
        hr.log(ctx, str(exc), "WARN")
        return hr.finish(ctx, 0, msg=str(exc))
    except Exception as exc:  # pylint: disable=broad-exception-caught
        hr.log(ctx, f"Falha nao tratada: {exc}", "ERROR")
        return hr.finish(ctx, 1)


if __name__ == "__main__":
    sys.exit(main())
