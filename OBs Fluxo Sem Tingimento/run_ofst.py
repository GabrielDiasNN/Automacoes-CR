"""Runner Python da automacao OBs Fluxo Sem Tingimento (OFST-06), migracao do item 3.

Substitui a orquestracao do ``run.ps1`` anterior e reproduz o mesmo fluxo, passo a passo:

1. pre-flight: disco, paths, check Oracle (modo ``queue`` ou endpoint TCP) e WhatsApp
   (``whatsapp-config.json`` com o destino em ``OFST_WHATSAPP_TARGET``); codigo 26 so no
   modo ``queue`` com worker offline e os demais checks ok;
2. lock global ``OFST-06``, rotacao do log (15 dias) e limpeza dos artefatos residuais;
3. extract: ``extract_ofst.py`` com 3 tentativas e backoff 30/60/120; exit 2 reconcilia o
   ``.tmp`` e encerra com 2 (nada a notificar); demais falhas viram o codigo canonico;
4. transform: ``format_message.py`` (exit 2 encerra com 2; outro exit diferente de 0
   encerra com 4) e leitura do ``cards_manifest.json``;
5. dispatch: WhatsApp com 1 card (``Send-WhatsApp.ps1``, modo AUTO) ou varios (modo
   BATCH, com reconciliacao do lote e commit parcial do state);
6. commit: ``ofst_state.json.tmp`` promovido a ``ofst_state.json`` so depois do envio
   confirmado ou no ramo idempotente (exit 2), em que o state podado precisa ser persistido.

Uso: ``python run_ofst.py [ExecId] [--dry-run]``. O ``run.ps1`` e um shim que resolve o
interpretador, chama este arquivo e repassa o exit code, porque o worker do Orchestrator le
o exit code de ``powershell.exe -File run.ps1 <ExecId>``. Com ``--dry-run``, pre-flight,
extract e transform rodam de verdade, mas nenhum WhatsApp e enviado e o state nao e
confirmado: a execucao so loga o que faria. Uso manual de validacao.
"""

# pylint: disable=import-error
from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Final

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "python")
)

import hub_runner as hr  # noqa: E402
import hub_whatsapp as hw  # noqa: E402
import oracle_queue as fila  # noqa: E402
from automation_log import ensure_utf8_streams  # noqa: E402

AUTOMACAO: Final[str] = "OBs Fluxo Sem Tingimento"
CHAVE_LOCK: Final[str] = "OFST-06"
SLUG_LOG: Final[str] = "Ofst"
SLUG_TRACE: Final[str] = "ofst"
OFST_DIR: Final[Path] = Path(__file__).resolve().parent
RAIZ: Final[Path] = OFST_DIR.parent
CODIGOS_SEM_FALHA: Final[tuple[int, ...]] = (0, 2, 22)
EXIT_ERRO_FATAL_PREFLIGHT: Final[int] = 1
EXIT_NADA_A_NOTIFICAR: Final[int] = 2
EXIT_FALHA_EXTRACAO: Final[int] = 3
EXIT_FALHA_ORQUESTRACAO: Final[int] = 4
EXIT_REAUTENTICACAO: Final[int] = 21
EXIT_ADIADO: Final[int] = 22
TENTATIVAS_EXTRACAO: Final[int] = 3
BACKOFF_EXTRACAO: Final[tuple[int, ...]] = (30, 60, 120)
RETENCAO_LOG_DIAS: Final[int] = 15
ESPACO_MINIMO_GB: Final[float] = 1.0
MODO_UNICO: Final[str] = "AUTO"
MODO_LOTE: Final[str] = "BATCH"
_PADRAO_TS: Final[re.Pattern[str]] = re.compile(
    r'^\{"(?:ts|timestamp)":"(\d{4}-\d{2}-\d{2})T'
)
_COMENTARIO_INLINE: Final[re.Pattern[str]] = re.compile(r"\s+#.*$")
_MARCADOR_NIVEL: Final[re.Pattern[str]] = re.compile(
    r"\[(INFO|WARN|ERROR|ERRO|DEBUG)\]", re.IGNORECASE
)
_NIVEIS_LINHA: Final[dict[str, str]] = {
    "ERROR": "ERRO",
    "ERRO": "ERRO",
    "WARN": "WARN",
    "DEBUG": "DEBUG",
}


@dataclass(frozen=True)
class Caminhos:  # pylint: disable=too-many-instance-attributes
    # Um campo por arquivo que a automacao le ou grava; agrupar os esconderia.
    """Arquivos lidos e gravados pela automacao, todos na pasta dela (e o envio, na raiz)."""

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
    def da_pasta(cls, pasta: Path, raiz: Path) -> Caminhos:
        """Caminhos padrao da automacao a partir da pasta dela e da raiz do repositorio."""
        return cls(
            pasta=pasta,
            extract_py=pasta / "extract_ofst.py",
            format_py=pasta / "format_message.py",
            config_wa=pasta / "whatsapp-config.json",
            send_wa=raiz / "lib" / "Send-WhatsApp.ps1",
            estado=pasta / "ofst_state.json",
            estado_tmp=pasta / "ofst_state.json.tmp",
            resultado=pasta / "ofst_result.json",
            manifesto=pasta / "cards_manifest.json",
            mensagem=pasta / "message.txt",
            card=pasta / "card.png",
            batch_input=pasta / "batch_input.json",
            batch_result=pasta / "batch_result.json",
        )


@dataclass
class _Sessao:  # pylint: disable=too-many-instance-attributes
    # Estado de uma execucao: cada campo espelha uma variavel de escopo do run.ps1.
    """Estado de uma execucao: contexto de log, modo, arquivos e o que ja foi confirmado."""

    ctx: hr.HubRunContext
    caminhos: Caminhos
    dry_run: bool
    resultado_fresco: bool = False
    estado_confirmado: bool = False
    encerrada: bool = False
    config_wa: dict[str, Any] = field(default_factory=dict)
    destino_mascarado: str = ""
    cards: tuple[hw.CardPagina, ...] = ()


def _aviso(ctx: hr.HubRunContext, step: str | None = None) -> Callable[[str], None]:
    """Repassa avisos das bibliotecas ao log da execucao como evento WARN."""

    def avisar(mensagem: str) -> None:
        hr.log(ctx, mensagem, "WARN", step=step)

    return avisar


def _texto(valor: object) -> str:
    """Campo do JSON como texto, como [string] do PS: null vira vazio."""
    return "" if valor is None else str(valor)


def _ler_linha_env(linha: str) -> tuple[str, str] | None:
    """Par chave/valor de uma linha do .env, como ConvertFrom-EnvLine."""
    texto = linha.strip()
    if not texto or texto.startswith("#"):
        return None
    partes = texto.split("=", 1)
    if len(partes) != 2:
        return None
    chave = partes[0].strip()
    valor = _COMENTARIO_INLINE.sub("", partes[1].strip()).strip()
    if not chave or not valor:
        return None
    return chave, valor


def _carregar_env(raiz: Path) -> None:
    """Carrega o .env da raiz no ambiente do processo, como Import-HubEnv."""
    caminho = raiz / ".env"
    if not caminho.exists():
        return
    conteudo = caminho.read_text(encoding="utf-8-sig", errors="replace")
    for linha in conteudo.splitlines():
        par = _ler_linha_env(linha)
        if par is not None:
            os.environ[par[0]] = par[1]


def _telemetria_padrao(raiz: Path) -> hr.TelemetryClient | None:
    """Cliente HTTP da telemetria quando o .env traz ORCHESTRATOR_API_KEY."""
    chave = hr.read_api_key(raiz)
    return hr.HttpTelemetryClient(chave) if chave else None


def _modo_driver() -> str:
    """ORACLE_DRIVER_MODE normalizado; ausente vale 'auto', o padrao do .env.example."""
    bruto = os.environ.get("ORACLE_DRIVER_MODE", "").strip().lower()
    return bruto or "auto"


def _resultado_oracle() -> hr.OraclePreflight:
    """Check Oracle do pre-flight, com o modo, a conexao e a pasta da fila do ambiente."""
    return hr.oracle_preflight(
        modo=_modo_driver(),
        conexao=os.environ.get("ORACLE_CONNECT_STRING", ""),
        pasta_fila=fila.get_queue_dir(),
    )


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
    """Linha de um path do pre-flight (CheckPaths do Test-AutomationPreFlight)."""
    if caminho.exists():
        return f"OK: Path: {caminho.name}"
    return f"ERRO: Path inacessivel: {caminho.name}"


def _pre_flight_automacao(
    ctx: hr.HubRunContext,
    caminhos: Sequence[Path],
    oracle: hr.OraclePreflight | None = None,
) -> bool:
    """Test-AutomationPreFlight: disco, paths e, quando informado, as linhas do check Oracle."""
    hr.log(ctx, "Iniciando Pre-Flight Check...", step="preflight")
    resultados = [_linha_disco(ctx.raiz)]
    resultados.extend(_linha_caminho(caminho) for caminho in caminhos)
    if oracle is not None:
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
    """Interpretador e arquivos que o pre-flight confere (CheckPaths do run.ps1)."""
    return (
        Path(sys.executable),
        caminhos.extract_py,
        caminhos.format_py,
        caminhos.config_wa,
    )


def _ler_config_whatsapp(caminho: Path) -> dict[str, Any]:
    """Le whatsapp-config.json (Get-Content | ConvertFrom-Json); a raiz precisa ser objeto."""
    dados: object = json.loads(caminho.read_text(encoding="utf-8-sig"))
    if not isinstance(dados, dict):
        raise ValueError(f"{caminho.name} invalido: a raiz nao e um objeto JSON.")
    return dados


def _resolver_destino(alvo: object, origem: Path) -> str:
    """Destino real do envio (Resolve-WhatsAppTarget): o valor de contactIdEnv no ambiente.

    O contactId do config e so placeholder de schema e nunca vira destino.
    """
    if not isinstance(alvo, dict):
        raise ValueError(
            f"Destino do WhatsApp ausente: 'target' nao e um objeto em {origem}."
        )
    trecho = f" ({origem})"
    nome_env = _texto(alvo.get("contactIdEnv"))
    if nome_env:
        destino = os.environ.get(nome_env, "")
        if not destino.strip():
            raise ValueError(
                f"Destino do WhatsApp ausente: variavel de ambiente '{nome_env}'{trecho} "
                "nao esta definida ou esta vazia. O contactId do config e apenas "
                "placeholder de schema, nunca um destino real."
            )
        return destino
    placeholder = _texto(alvo.get("contactId")) or _texto(alvo.get("contactPhone"))
    if not placeholder.strip():
        raise ValueError(
            f"Destino do WhatsApp ausente: 'target'{trecho} nao declara contactId, "
            "contactPhone nem contactIdEnv."
        )
    return placeholder


def _mascarar(valor: str) -> str:
    """Destinatario para o log de dry-run: so os 4 ultimos caracteres aparecem."""
    return "***" + valor[-4:] if len(valor) > 4 else "***"


def _checar_whatsapp(sessao: _Sessao) -> bool:
    """Pre-flight do WhatsApp: config legivel e destino resolvido. Guarda a config na sessao."""
    caminho = sessao.caminhos.config_wa
    try:
        config = _ler_config_whatsapp(caminho)
        destino = _resolver_destino(config.get("target"), caminho)
    except (OSError, ValueError) as exc:
        hr.log(
            sessao.ctx, f"Pre-Flight WhatsApp falhou: {exc}", "ERRO", step="preflight"
        )
        return False
    sessao.config_wa = config
    sessao.destino_mascarado = _mascarar(destino)
    return True


def _demais_checks(sessao: _Sessao, caminhos: Caminhos) -> bool:
    """Outros checks do pre-flight, sem o worker Oracle: paths e WhatsApp (OutrosChecks)."""
    return _pre_flight_automacao(sessao.ctx, _caminhos_preflight(caminhos)) and (
        _checar_whatsapp(sessao)
    )


def _preflight(sessao: _Sessao) -> int | None:
    """Etapa preflight. Devolve o exit code de falha, ou None quando o pre-flight passa."""
    ctx = sessao.ctx
    caminhos = _caminhos_preflight(sessao.caminhos)
    hr.start_step(ctx, "preflight", mensagem="Oracle, Python e WhatsApp configurados")
    oracle = _resultado_oracle()
    passou = _pre_flight_automacao(ctx, caminhos, oracle) and _checar_whatsapp(sessao)
    hr.complete_step(ctx, ok=passou)
    if passou:
        return None
    return hr.oracle_preflight_exit_code(
        oracle, outros_checks=lambda: _demais_checks(sessao, sessao.caminhos)
    )


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


def _limpar_artefatos(caminhos: Caminhos) -> None:
    """Artefatos residuais da execucao anterior, removidos antes da extracao (dentro do lock)."""
    for arquivo in (
        caminhos.resultado,
        caminhos.estado_tmp,
        caminhos.mensagem,
        caminhos.card,
        caminhos.manifesto,
        caminhos.batch_input,
        caminhos.batch_result,
    ):
        _remover(arquivo)
    for cartao in caminhos.pasta.glob("card_*.png"):
        _remover(cartao)


def _encerrar(sessao: _Sessao, codigo: int, mensagem: str) -> int:
    """Unico ponto de saida: fecha a execucao e a telemetria, como Exit-WithCode."""
    sessao.encerrada = True
    resultado = sessao.caminhos.resultado if sessao.resultado_fresco else None
    return hr.finish(sessao.ctx, codigo, mensagem, record_counts_path=resultado)


def _promover_state(sessao: _Sessao) -> None:
    """Promove o .tmp a ofst_state.json (Move-Item). So chamado fora do dry-run."""
    os.replace(sessao.caminhos.estado_tmp, sessao.caminhos.estado)


def _avisar_commit_dry_run(ctx: hr.HubRunContext) -> None:
    """Dry-run: informa que o commit do state foi pulado."""
    hr.log(
        ctx,
        "[DRY-RUN] Commit de estado nao executado: o .tmp seria promovido a ofst_state.json.",
        step="commit",
    )


def _encerrar_idempotente(sessao: _Sessao) -> int:
    """Extract idempotente (exit 2): reconcilia o .tmp sem envio e encerra com 2."""
    ctx = sessao.ctx
    if sessao.caminhos.estado_tmp.exists():
        hr.start_step(ctx, "commit", mensagem="Reconciliando state sem envio")
        if sessao.dry_run:
            _avisar_commit_dry_run(ctx)
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
    """Etapa extract: extract_ofst.py com 3 tentativas. None quando segue para o transform."""
    ctx = sessao.ctx
    hr.start_step(ctx, "extract", mensagem="Extracao Oracle + validacao de estoque")
    resultado = hr.run_python_step(
        ctx,
        hr.PythonStepSpec(
            python_exe=sys.executable,
            script_path=str(sessao.caminhos.extract_py),
            operation_name="Extracao OBs Fluxo Sem Tingimento (extract_ofst.py)",
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


def _ambiente_filho(ctx: hr.HubRunContext, step: str) -> dict[str, str]:
    """Ambiente do filho: UTF-8, HUB_* e HUB_LOG_STRUCTURED herdados do processo."""
    ambiente = dict(os.environ)
    ambiente.update(ctx.ambiente())
    ambiente.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "HUB_STEP": step})
    return ambiente


def _e_envelope(linha: str) -> bool:
    """True quando a linha ja e um evento completo do envelope (Test-HubLogEnvelope)."""
    texto = linha.strip()
    if not texto.startswith("{"):
        return False
    try:
        objeto: object = json.loads(texto)
    except ValueError:
        return False
    return isinstance(objeto, dict) and all(
        campo in objeto for campo in hr.CAMPOS_ENVELOPE
    )


def _nivel_da_linha(linha: str, padrao: str) -> str:
    """Nivel pelo marcador [INFO]/[WARN]/[ERRO]/[ERROR]/[DEBUG] da linha, senao o padrao."""
    casamento = _MARCADOR_NIVEL.search(linha)
    if casamento is None:
        return padrao
    return _NIVEIS_LINHA.get(casamento.group(1).upper(), "INFO")


def _anexar_bruto(caminho: Path, texto: str) -> None:
    """Anexa um evento ja no envelope ao jsonl, em CRLF, como o Write-HubLogEvent."""
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with caminho.open("a", encoding="utf-8", newline="\r\n") as arquivo:
            arquivo.write(texto + "\n")
    except OSError as exc:
        sys.stderr.write(f"[run_ofst] Falha ao persistir evento de log: {exc}\n")


def _encaminhar_linha(
    ctx: hr.HubRunContext, linha: str, nivel_padrao: str, step: str
) -> None:
    """Encaminha uma linha de filho como Write-HubForwardedLine: envelope verbatim ou log."""
    if not linha.strip():
        return
    if _e_envelope(linha):
        texto = linha.strip()
        _anexar_bruto(ctx.log_path, texto)
        sys.stdout.write(texto + "\n")
        return
    hr.log(ctx, linha, _nivel_da_linha(linha, nivel_padrao), step=step)


def _executar_formatador(ctx: hr.HubRunContext, caminhos: Caminhos) -> int:
    """Roda format_message.py como processo filho (Invoke-NativeProcess) e devolve o exit code."""
    resultado = subprocess.run(
        [sys.executable, str(caminhos.format_py), ctx.exec_id],
        cwd=caminhos.pasta,
        env=_ambiente_filho(ctx, "transform"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    for linha in resultado.stdout.splitlines():
        _encaminhar_linha(ctx, linha, "INFO", "transform")
    for linha in resultado.stderr.splitlines():
        _encaminhar_linha(ctx, linha, "WARN", "transform")
    return int(resultado.returncode)


def _etapa_formatacao(sessao: _Sessao) -> int | None:
    """Etapa transform: cards PNG e manifesto. None quando segue para o dispatch."""
    ctx = sessao.ctx
    caminhos = sessao.caminhos
    hr.start_step(
        ctx,
        "transform",
        mensagem="Gerando card(s) PNG e cards_manifest.json (format_message.py)",
    )
    codigo = _executar_formatador(ctx, caminhos)
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
    """Dry-run do dispatch: prepara o lote sem enviar, loga o que faria e nao commita."""
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
        _avisar_commit_dry_run(ctx)
    hr.complete_step(ctx)
    return _encerrar(
        sessao,
        0,
        "[DRY-RUN] Validacao manual concluida: nenhum envio e nenhum commit de estado.",
    )


def _enviar_whatsapp(sessao: _Sessao, modo: str) -> int:
    """Aciona o Send-WhatsApp.ps1 pelo modulo compartilhado e devolve o exit code."""
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
    """Exit 21 (reautenticacao) e 22 (adiado por lock/cooldown). None para os demais codigos."""
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
    """Commit da idempotencia, somente apos envio confirmado (exit 0)."""
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
    """Um card: Send-WhatsApp em modo AUTO. 0 e 22 seguem o fluxo; 21 e 22 saem direto."""
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
    """Envio parcial do lote: commit do state sem as OBs falhas e ajuste do record_counts."""
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
    """Lote sem nenhuma pagina entregue: 21 e 22 saem direto; o resto e falha (exit 4)."""
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
    """Varios cards: Send-WhatsApp em modo BATCH e reconciliacao do batch_result.json."""
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
        on_warn=_aviso(ctx, "dispatch"),
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
    """Etapa dispatch: WhatsApp conforme a configuracao, o dry-run e a quantidade de cards."""
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
    """Finally do run.ps1: remove o .tmp quando o envio nao foi confirmado."""
    tmp = sessao.caminhos.estado_tmp
    if sessao.estado_confirmado or not tmp.exists():
        return
    _remover(tmp)
    if not sessao.encerrada:
        hr.log(sessao.ctx, f"Limpeza finally: {tmp} removido.", "DEBUG", step="cleanup")


def _fluxo(sessao: _Sessao) -> int:
    """Etapas extract, transform e dispatch, executadas dentro do lock."""
    _rotacionar_log(sessao.ctx.log_path)
    _limpar_artefatos(sessao.caminhos)
    codigo = _etapa_extracao(sessao)
    if codigo is None:
        codigo = _etapa_formatacao(sessao)
    if codigo is None:
        return _etapa_envio(sessao)
    return codigo


def _com_lock(sessao: _Sessao) -> int:
    """Executa o fluxo protegido pelo mutex OFST-06 (Enter/Exit-AutomationLock)."""
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
        try:
            return _fluxo(sessao)
        finally:
            _limpar_tmp_sem_confirmacao(sessao)


def executar(
    ctx: hr.HubRunContext, caminhos: Caminhos, *, dry_run: bool = False
) -> int:
    """Roda o fluxo completo e devolve o exit code (quem chama faz sys.exit)."""
    sessao = _Sessao(ctx=ctx, caminhos=caminhos, dry_run=dry_run)
    hr.execution_start(ctx, f"INICIO — {AUTOMACAO} (OFST-06). ExecId={ctx.exec_id}")
    if dry_run:
        hr.log(
            ctx,
            "[DRY-RUN] Validacao manual: nenhum envio de WhatsApp sera feito e o state "
            "nao sera confirmado.",
            "WARN",
        )
    # Residual: falha inesperada no pre-flight. O run.ps1 deixava o erro subir sem
    # Exit-WithCode (processo sai com 1); aqui o mesmo codigo sai com execution.end e telemetria.
    try:
        codigo_preflight = _preflight(sessao)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return _encerrar(sessao, EXIT_ERRO_FATAL_PREFLIGHT, f"ERRO FATAL: {exc}")
    if codigo_preflight is not None:
        return _encerrar(
            sessao, codigo_preflight, "FALHA NO PRE-FLIGHT CHECK. Abortando."
        )
    # Residual: catch [System.Exception] externo do run.ps1, que sai com 4 (lock ocupado,
    # excecao de etapa). O lock ja foi liberado pelo with antes de chegar aqui.
    try:
        return _com_lock(sessao)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return _encerrar(
            sessao, EXIT_FALHA_ORQUESTRACAO, f"Falha critica na orquestracao: {exc}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada: ``run_ofst.py [ExecId] [--dry-run]``. Devolve o exit code."""
    ensure_utf8_streams()
    argumentos = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in argumentos
    posicionais = [arg for arg in argumentos if arg != "--dry-run"]
    # O run.ps1 anterior exportava HUB_LOG_STRUCTURED=1 aos filhos (extract e format).
    os.environ["HUB_LOG_STRUCTURED"] = "1"
    _carregar_env(RAIZ)
    ctx = hr.create_run_context(
        hr.AutomationSpec(
            automacao=AUTOMACAO,
            slug=SLUG_LOG,
            trace_slug=SLUG_TRACE,
            lock_key=CHAVE_LOCK,
            log_dir=OFST_DIR / "Logs",
            non_failure_codes=CODIGOS_SEM_FALHA,
        ),
        exec_id=posicionais[0] if posicionais else "",
        telemetry=_telemetria_padrao(RAIZ),
        project_root=RAIZ,
    )
    return executar(ctx, Caminhos.da_pasta(OFST_DIR, RAIZ), dry_run=dry_run)


if __name__ == "__main__":
    sys.exit(main())
