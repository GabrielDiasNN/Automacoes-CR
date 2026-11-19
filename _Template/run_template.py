"""Runner Python da automacao TEMPLATE_SLUG (esqueleto gerado por Tools/New-Automation.ps1).

Mesmo fluxo do run.ps1 de template, sobre lib/python/hub_runner.py:

1. pre-flight: disco, Python e paths (o check Oracle fica comentado, na etapa);
2. lock global com a chave TEMPLATE_SLUG;
3. extract: placeholder para a logica de negocio;
4. entrega e commit: exemplos comentados (e-mail com idempotencia por canal, como RE-03).

Uso: ``python TEMPLATE_RUNNER [ExecId] [--dry-run]``. O ``run.ps1`` e um shim que resolve o
interpretador, chama este arquivo e repassa o exit code. Codigos: 0 sucesso; 2 idempotente
(nada a fazer); 4 falha critica; 9 pre-flight. Com ``--dry-run`` nenhum envio e feito e o
estado nao e confirmado.
"""

# pylint: disable=import-error
from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "python")
)

import hub_runner as hr  # noqa: E402
from automation_log import ensure_utf8_streams  # noqa: E402

AUTOMACAO: Final[str] = "[Nome da Automação]"
SLUG_LOG: Final[str] = "TEMPLATE_SLUG"
CHAVE_LOCK: Final[str] = "TEMPLATE_SLUG"
EXIT_FALHA_CRITICA: Final[int] = 4
RETENCAO_LOG_DIAS: Final[int] = 15
PASTA: Final[Path] = Path(__file__).resolve().parent
RAIZ: Final[Path] = PASTA.parent


def _preflight(ctx: hr.HubRunContext) -> bool:
    """Etapa preflight: disco, interpretador e paths."""
    hr.start_step(ctx, "preflight", mensagem="Python e paths")
    # Com Oracle: monte oracle = hr.oracle_preflight_from_env() e passe em
    # oracle=oracle de hr.run_preflight(...), usando hr.oracle_preflight_exit_code
    # para decidir o codigo de falha. Exemplo em Receitas Emitidas/run_receitas.py.
    ok = hr.run_preflight(ctx, [Path(sys.executable)], step="preflight")
    hr.complete_step(ctx, ok=ok)
    return ok


def _etapas(ctx: hr.HubRunContext, *, dry_run: bool) -> int:
    """Etapas extract, entrega e commit, executadas dentro do lock."""
    hr.rotate_log(ctx.log_path, RETENCAO_LOG_DIAS)
    hr.start_step(ctx, "extract", mensagem="Executando tarefas")
    hr.log(ctx, "Executando tarefas...", step="extract")
    # --- ETAPA 1: LOGICA DE NEGOCIO AQUI ---
    # Com Oracle, rode o extrator pelo runner compartilhado:
    #   resultado = hr.run_python_step(ctx, hr.PythonStepSpec(
    #       python_exe=sys.executable, script_path=str(PASTA / "extract_oracle.py"),
    #       operation_name="Extracao Oracle", step="extract", max_attempts=3,
    #       backoff_seconds=(30, 60, 120), stdout_is_data=True))
    #   if resultado.idempotent:  # exit 2 do script = nada a fazer
    #       return hr.finish(ctx, hr.EXIT_IDEMPOTENTE, "Idempotencia: nada a fazer.")
    hr.complete_step(ctx)

    # --- ETAPA 2: ENTREGA (exemplo comentado: e-mail com idempotencia por canal, como RE-03) ---
    # estado_tmp, estado = PASTA / "state.json.tmp", PASTA / "state.json"
    # entrega = PASTA / "delivery_state.json"
    # hash_atual = hr.get_last_content_hash(estado_tmp, estado, on_warning=...)
    # estado_entrega = hr.read_delivery_state(entrega, ["email"], on_warning=...)
    # hr.update_delivery_state_hash(estado_entrega, hash_atual)
    # if hr.delivery_pending(estado_entrega, "email", hash_atual) and not dry_run:
    #     enviado = hr.send_outlook_email(ctx, to=os.environ["NOVA_AUTOMACAO_EMAIL_TO"],
    #                                     subject="...", html_body="...")
    #     if not enviado:
    #         return hr.finish(ctx, EXIT_FALHA_CRITICA, "Falha no envio. State NAO commitado.")
    #     hr.set_delivery_success(estado_entrega, "email")
    #     hr.save_delivery_state(estado_entrega, entrega)
    # # --- COMMIT DA IDEMPOTENCIA (somente apos a entrega confirmada) ---
    # if not dry_run and estado_tmp.exists():
    #     os.replace(estado_tmp, estado)
    if dry_run:
        hr.log(ctx, "[DRY-RUN] Entrega e commit de estado nao executados.", "WARN")
    return hr.finish(ctx, 0, "Execucao concluida com sucesso.")


def executar(ctx: hr.HubRunContext, *, dry_run: bool = False) -> int:
    """Roda o fluxo completo e devolve o exit code (quem chama faz sys.exit)."""
    hr.execution_start(ctx, f"INICIO - {AUTOMACAO}. ExecId={ctx.exec_id}")
    if dry_run:
        hr.log(
            ctx,
            "[DRY-RUN] Validacao manual: nenhum envio e nenhum commit de estado.",
            "WARN",
        )
    try:
        if not _preflight(ctx):
            return hr.finish(
                ctx, hr.EXIT_PREFLIGHT_FALHA, "FALHA NO PRE-FLIGHT CHECK. Abortando."
            )
        hr.start_step(ctx, "lock", mensagem="Adquirindo lock global")
        mutex = hr.AutomationMutex(CHAVE_LOCK, on_warning=hr.warn_logger(ctx, "lock"))
        with mutex:
            hr.complete_step(ctx)
            return _etapas(ctx, dry_run=dry_run)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Equivale ao catch [System.Exception] do run.ps1: falha critica, exit 4.
        return hr.finish(
            ctx, EXIT_FALHA_CRITICA, f"Falha critica na orquestracao: {exc}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada: ``TEMPLATE_RUNNER [ExecId] [--dry-run]``. Devolve o exit code."""
    ensure_utf8_streams()
    argumentos = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in argumentos
    posicionais = [arg for arg in argumentos if arg != "--dry-run"]
    hr.load_env_file(RAIZ)
    ctx = hr.create_run_context(
        hr.AutomationSpec(
            automacao=AUTOMACAO,
            slug=SLUG_LOG,
            trace_slug=SLUG_LOG,
            lock_key=CHAVE_LOCK,
            log_dir=PASTA / "Logs",
            non_failure_codes=(0, hr.EXIT_IDEMPOTENTE),
        ),
        exec_id=posicionais[0] if posicionais else "",
        telemetry=hr.default_telemetry(RAIZ),
        project_root=RAIZ,
    )
    return executar(ctx, dry_run=dry_run)


if __name__ == "__main__":
    sys.exit(main())
