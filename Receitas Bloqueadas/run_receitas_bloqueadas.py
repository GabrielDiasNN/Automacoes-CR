"""Runner Python da automacao Receitas Bloqueadas (RB-01), migracao do item 3, parte 3.

Substitui a orquestracao do ``run.ps1`` anterior e reproduz o mesmo fluxo, passo a passo:

1. pre-flight, fora do lock como no run.ps1: disco, paths (interpretador,
   processar_receitas.py, lib/Send-WhatsApp.ps1, whatsapp-config.json e
   receitas_config.json) e o check Oracle do Test-AutomationPreFlight. Falha sai com 9,
   ou com 26 quando so o worker da fila esta offline;
2. lock global ``RB-01`` (o mesmo mutex do run.ps1 antigo), rotacao do log com 15 dias e
   remocao do ``rb_result.json``;
3. extract: ``processar_receitas.py`` com 3 tentativas e backoff 60/120/300. Exit 2 encerra
   com 2 (idempotencia, sem notificacao). Falha definitiva manda alerta e sai com o codigo
   canonico do Orchestrator (3, 26 ou 27);
4. dispatch, so quando existe ``email_body.html``: idempotencia granular por canal em
   ``email_state.json``, e-mail pela CLI com 2 tentativas e backoff 15/30 e WhatsApp pelo
   ``Send-WhatsApp.ps1`` em modo AUTO. Canal com falha define o codigo final (25 e-mail;
   21, 22, 23 ou 24 WhatsApp);
5. commit: ``receitas_state.json.tmp`` vira ``receitas_state.json`` so sem falha de canal.

Uso: ``python run_receitas_bloqueadas.py [ExecId] [--dry-run]``. O ``run.ps1`` e um shim que
resolve o interpretador, chama este arquivo e repassa o exit code. Com ``--dry-run``,
pre-flight e extract rodam de verdade, mas nenhum e-mail, alerta ou WhatsApp e enviado, nenhum
estado e confirmado e os destinatarios aparecem mascarados: a execucao so loga o que faria.
Uso manual de validacao.

A CLI ``lib/Invoke-OutlookEmail.ps1`` recebe ``-Cc``, ``-Bcc`` e ``-Attachments`` e os repassa a
``Send-OutlookEmail``, como o run.ps1 fazia. Anexo ausente falha fechado (canal 25): nunca sai
e-mail sem a planilha.
"""

# pylint: disable=import-error
from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import sys
import tempfile
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
import hub_whatsapp as hw  # noqa: E402
import oracle_queue as fila  # noqa: E402
from automation_log import ensure_utf8_streams  # noqa: E402
from log_masking import mask_sensitive  # noqa: E402

AUTOMACAO: Final[str] = "Receitas Bloqueadas"
CHAVE_LOCK: Final[str] = "RB-01"
SLUG_LOG: Final[str] = "ReceitasBloqueadas"
SLUG_TRACE: Final[str] = "rb"
CANAL_EMAIL: Final[str] = "email"
CANAL_WHATSAPP: Final[str] = "whatsapp"
CANAIS: Final[tuple[str, ...]] = (CANAL_EMAIL, CANAL_WHATSAPP)
RB_DIR: Final[Path] = Path(__file__).resolve().parent
RAIZ: Final[Path] = RB_DIR.parent
NOME_PLANILHA: Final[str] = "Receitas Bloqueadas.xlsx"
MENSAGEM_EXTRACAO: Final[str] = "Processamento Python (processar_receitas.py)"
MENSAGEM_DISPATCH: Final[str] = "Idempotencia granular + envio E-mail/WhatsApp"
TENTATIVAS_EXTRACAO: Final[int] = 3
BACKOFF_EXTRACAO: Final[tuple[int, ...]] = (60, 120, 300)
TENTATIVAS_EMAIL: Final[int] = 2
BACKOFF_EMAIL: Final[tuple[int, ...]] = (15, 30)
CODIGO_FALHA_EXTRACAO: Final[int] = 3
CODIGO_FALHA_CRITICA: Final[int] = 4
CODIGO_FALHA_CANAL_EMAIL: Final[int] = 25
CODIGO_ADIADO_WHATSAPP: Final[int] = 22
CODIGO_WHATSAPP_LOCK: Final[int] = 40
CODIGO_WHATSAPP_DESABILITADO: Final[int] = 23
CODIGO_WHATSAPP_REAUTENTICACAO: Final[int] = 21
CODIGO_FALHA_WHATSAPP: Final[int] = 24
NAO_FALHA: Final[tuple[int, ...]] = (0, hr.EXIT_IDEMPOTENTE, CODIGO_ADIADO_WHATSAPP)
MSG_FALHA_EMAIL: Final[str] = (
    "Execucao concluida com falha parcial no canal E-mail. "
    "Revise os logs do canal antes de novo requeue."
)
MSG_ADIADO_WHATSAPP: Final[str] = (
    "WhatsApp adiado por lock ou cooldown da sessao hub-global."
)
MSG_WHATSAPP_DESABILITADO: Final[str] = (
    "Execucao concluida com falha parcial: envio WhatsApp desabilitado na configuracao do canal."
)
MSG_WHATSAPP_REAUTENTICACAO: Final[str] = (
    "Execucao concluida com falha parcial: WhatsApp requer reautenticacao antes de nova tentativa."
)
MSG_FALHA_WHATSAPP: Final[str] = (
    "Execucao concluida com falha parcial no canal WhatsApp. "
    "Revise os logs do canal antes de novo requeue."
)
MSG_WHATSAPP_EXCECAO: Final[str] = (
    "Execucao concluida com falha parcial no canal WhatsApp. "
    "O wrapper nao conseguiu completar a notificacao."
)
RETENCAO_LOG_DIAS: Final[int] = 15
ESPACO_MINIMO_GB: Final[float] = 1.0
IDADE_TMP_ORFAO: Final[timedelta] = timedelta(days=1)
_PADRAO_TS: Final[re.Pattern[str]] = re.compile(
    r'^\{"(?:ts|timestamp)":"(\d{4}-\d{2}-\d{2})T'
)
_MARCADOR_NIVEL: Final[re.Pattern[str]] = re.compile(
    r"\[(INFO|WARN|ERROR|ERRO|DEBUG)\]", re.IGNORECASE
)
_NIVEIS: Final[dict[str, str]] = {
    "ERROR": "ERRO",
    "ERRO": "ERRO",
    "WARN": "WARN",
    "DEBUG": "DEBUG",
}


@dataclass(frozen=True)
class Caminhos:  # pylint: disable=too-many-instance-attributes
    # Um campo por arquivo que a automacao le ou grava; agrupar os esconderia.
    """Arquivos lidos e gravados pela automacao: a pasta dela e o send_whatsapp de lib/."""

    pasta: Path
    processar: Path
    html: Path
    planilha: Path
    config_email: Path
    config_whatsapp: Path
    estado: Path
    estado_tmp: Path
    entrega: Path
    resultado: Path
    send_whatsapp: Path

    @classmethod
    def da_pasta(cls, pasta: Path, raiz: Path) -> Caminhos:
        """Caminhos padrao da automacao a partir da pasta dela e da raiz do repositorio."""
        return cls(
            pasta=pasta,
            processar=pasta / "processar_receitas.py",
            html=pasta / "email_body.html",
            planilha=pasta / NOME_PLANILHA,
            config_email=pasta / "receitas_config.json",
            config_whatsapp=pasta / "whatsapp-config.json",
            estado=pasta / "receitas_state.json",
            estado_tmp=pasta / "receitas_state.json.tmp",
            entrega=pasta / "email_state.json",
            resultado=pasta / "rb_result.json",
            send_whatsapp=raiz / "lib" / "Send-WhatsApp.ps1",
        )


@dataclass(frozen=True)
class _Email:
    """Um e-mail do canal: destinatarios, assunto, corpo HTML e anexo."""

    para: str
    copia: str | None
    oculta: str | None
    assunto: str
    html: str
    anexo: Path


@dataclass
class _Sessao:
    """Estado de uma execucao: contexto, caminhos, modo e o resultado dos canais."""

    ctx: hr.HubRunContext
    caminhos: Caminhos
    dry_run: bool
    resultado_fresco: bool = False
    falha_codigo: int = 0
    falha_mensagem: str = ""


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
    oracle: hr.OraclePreflight | None = None,
) -> bool:
    """Test-AutomationPreFlight: disco, paths e, se informado, as linhas do check Oracle."""
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
        caminhos.processar,
        caminhos.send_whatsapp,
        caminhos.config_whatsapp,
        caminhos.config_email,
    )


def _codigo_falha_preflight(
    ctx: hr.HubRunContext, caminhos: Sequence[Path], oracle: hr.OraclePreflight
) -> int:
    """Get-OraclePreFlightExitCode: 26 so no modo queue, com worker offline e o resto ok; senao 9."""
    return hr.oracle_preflight_exit_code(
        oracle,
        outros_checks=lambda: _pre_flight_automacao(ctx, caminhos),
    )


def _preflight(sessao: _Sessao) -> int | None:
    """Etapa preflight. Devolve o exit code de falha, ou None quando o pre-flight passa."""
    ctx = sessao.ctx
    caminhos = _caminhos_preflight(sessao.caminhos)
    hr.start_step(ctx, "preflight", mensagem="Python, WhatsApp, e-mail e disco")
    oracle = _resultado_oracle()
    passou = _pre_flight_automacao(ctx, caminhos, oracle=oracle)
    hr.complete_step(ctx, ok=passou)
    return None if passou else _codigo_falha_preflight(ctx, caminhos, oracle)


def _limpar_temporarios_orfaos(pasta: Path, agora: datetime) -> None:
    """Remove os .tmp_*.json com mais de 1 dia (housekeeping do run.ps1); falha e ignorada."""
    corte = (agora - IDADE_TMP_ORFAO).timestamp()
    for arquivo in pasta.glob(".tmp_*.json"):
        with contextlib.suppress(OSError):
            if arquivo.stat().st_mtime < corte:
                arquivo.unlink()


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


def _registrar_falha(sessao: _Sessao, codigo: int, mensagem: str) -> None:
    """Guarda o codigo e a mensagem da falha de canal que definem o exit code final."""
    sessao.falha_codigo = codigo
    sessao.falha_mensagem = mensagem


def _encerrar(sessao: _Sessao, codigo: int, mensagem: str) -> int:
    """Unico ponto de saida: fecha a execucao e a telemetria, como Exit-WithCode."""
    resultado = sessao.caminhos.resultado if sessao.resultado_fresco else None
    return hr.finish(sessao.ctx, codigo, mensagem, record_counts_path=resultado)


def _falha_extracao(sessao: _Sessao, extracao: hr.PythonStepResult) -> int:
    """Falha definitiva do processamento: alerta por e-mail e codigo canonico do Orchestrator."""
    ctx = sessao.ctx
    codigo = hr.resolve_oracle_failure_exit_code(
        extracao.exit_code, default_exit_code=CODIGO_FALHA_EXTRACAO
    )
    tentativas = 1 if extracao.non_retryable else TENTATIVAS_EXTRACAO
    ultimo_erro = (
        f"Falha definitiva no processamento Python (PythonExit={extracao.exit_code})."
    )
    if sessao.dry_run:
        hr.log(
            ctx,
            "[DRY-RUN] Alerta de falha nao enviado: " + ultimo_erro,
            "WARN",
            step="extract",
        )
        sufixo = "Alerta de falha nao enviado (dry-run)."
    else:
        hr.send_failure_alert(
            ctx,
            task_name=AUTOMACAO,
            ultimo_erro=ultimo_erro,
            tentativas=tentativas,
        )
        sufixo = "Alerta de falha enviado."
    return _encerrar(
        sessao,
        codigo,
        "Falha definitiva no script Python "
        f"(PythonExit={extracao.exit_code}). {sufixo}",
    )


def _extrair(sessao: _Sessao) -> int | None:
    """Etapa extract: processar_receitas.py. Devolve o exit code de encerramento, ou None."""
    ctx = sessao.ctx
    hr.start_step(ctx, "extract", mensagem=MENSAGEM_EXTRACAO)
    spec = hr.PythonStepSpec(
        python_exe=sys.executable,
        script_path=str(sessao.caminhos.processar),
        operation_name=MENSAGEM_EXTRACAO,
        step="extract",
        max_attempts=TENTATIVAS_EXTRACAO,
        backoff_seconds=BACKOFF_EXTRACAO,
    )
    try:
        extracao = hr.run_python_step(ctx, spec)
    # Residual: o run.ps1 captura [System.Exception] em volta da invocacao e sai com 4; um
    # processo que nao chega a iniciar (interpretador ausente, falha de E/S) cai aqui.
    except Exception as exc:  # pylint: disable=broad-exception-caught
        hr.complete_step(ctx, ok=False)
        return _encerrar(
            sessao, CODIGO_FALHA_CRITICA, f"Falha ao invocar script Python: {exc}"
        )
    if extracao.idempotent:
        sessao.resultado_fresco = True
        hr.complete_step(ctx, ok=True)
        hr.log(
            ctx,
            "Python detectou idempotencia (ExitCode 2). Suprimindo notificacoes.",
            step="commit",
        )
        return _encerrar(
            sessao, hr.EXIT_IDEMPOTENTE, "Processo finalizado (Idempotencia Python)."
        )
    if not extracao.success:
        hr.complete_step(ctx, ok=False)
        return _falha_extracao(sessao, extracao)
    sessao.resultado_fresco = True
    hr.complete_step(ctx, ok=True)
    return None


def _modo_teste_ativo() -> bool:
    """Modo teste do run.ps1: ORCHESTRATOR_TEST_MODE manda, sem diferenciar caixa; ausente, vale
    AUTOMACAO_TEST_EMAIL do escopo User (registro), nunca o do processo, que tambem carrega o .env.
    """
    modo = os.environ.get("ORCHESTRATOR_TEST_MODE", "").casefold()
    if modo == "true":
        return True
    if modo == "false":
        return False
    return bool(hr.user_environment_variable("AUTOMACAO_TEST_EMAIL").strip())


def _destino_efetivo(to: str, cc: str | None) -> tuple[str, str | None, bool]:
    """Destino real ou, em modo teste, o endereco de teste sem copia. Devolve (to, cc, em_teste).

    Em modo teste so o To e redirecionado e o Cc some; o Bcc segue o run.ps1, que nao o limpa.
    """
    if not _modo_teste_ativo():
        return to, cc, False
    teste = hr.user_environment_variable("AUTOMACAO_TEST_EMAIL")
    alvo = teste if teste.strip() else os.environ.get("AUTOMACAO_ALERT_EMAIL", "")
    return alvo, None, True


def _juntar(valor: object) -> str:
    """Destinatarios como texto separado por ';' (-join do PowerShell); texto passa direto."""
    if isinstance(valor, list):
        return ";".join(str(item) for item in valor)
    return "" if valor is None else str(valor)


def _destinatarios(config: dict[str, Any]) -> tuple[str, str | None, str | None]:
    """To, Cc e Bcc: o .env (RB_EMAIL_TO/CC) tem prioridade; o config.json e fallback."""
    bloco = config.get("email")
    email: dict[str, Any] = bloco if isinstance(bloco, dict) else {}
    env_to = os.environ.get("RB_EMAIL_TO", "")
    env_cc = os.environ.get("RB_EMAIL_CC", "")
    to = env_to if env_to.strip() else _juntar(email.get("to"))
    cc_config = email.get("cc")
    cc = env_cc if env_cc.strip() else (_juntar(cc_config) if cc_config else None)
    bcc_config = email.get("bcc")
    bcc = _juntar(bcc_config) if bcc_config else None
    return to, cc, bcc


def _ler_config(caminho: Path) -> dict[str, Any]:
    """Le receitas_config.json (ConvertFrom-Json). JSON invalido levanta excecao, como no PS."""
    dados: object = json.loads(caminho.read_text(encoding="utf-8-sig"))
    return dados if isinstance(dados, dict) else {}


def _argumentos_email(
    ctx: hr.HubRunContext, email: _Email, html_path: str
) -> list[str]:
    """Argumentos da CLI lib/Invoke-OutlookEmail.ps1 para um e-mail do canal."""
    argumentos = [
        "-To",
        email.para,
        "-Subject",
        email.assunto,
        "-HtmlBodyFile",
        html_path,
        "-ExecId",
        ctx.exec_id,
        "-LogPath",
        str(ctx.log_path),
    ]
    if email.copia:
        argumentos.extend(["-Cc", email.copia])
    if email.oculta:
        argumentos.extend(["-Bcc", email.oculta])
    argumentos.extend(["-Attachments", str(email.anexo)])
    return argumentos


def _nivel_da_linha(linha: str) -> str:
    """Nivel pelo marcador [INFO]/[WARN]/[ERRO]/[ERROR]/[DEBUG] da linha da CLI; padrao INFO."""
    casamento = _MARCADOR_NIVEL.search(linha)
    if casamento is None:
        return "INFO"
    return _NIVEIS.get(casamento.group(1).upper(), "INFO")


def _enviar_email_cli(ctx: hr.HubRunContext, email: _Email) -> bool:
    """Envia pela CLI lib/Invoke-OutlookEmail.ps1 e devolve True quando ela confirma o envio.

    O corpo vai por arquivo temporario UTF-8, como em hr.send_outlook_email. Excecao de
    execucao propaga para o chamador; falha de processo vira exit code diferente de 0.
    """
    script = ctx.raiz / "lib" / "Invoke-OutlookEmail.ps1"
    fd, caminho = tempfile.mkstemp(prefix="rb_email_", suffix=".html")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as arquivo:
            arquivo.write(email.html)
        codigo, saida = hr.executar_cli_outlook(
            script, _argumentos_email(ctx, email, caminho)
        )
    finally:
        Path(caminho).unlink(missing_ok=True)
    for linha in saida.splitlines():
        if linha.strip():
            hr.log(ctx, linha, _nivel_da_linha(linha), step="dispatch")
    return codigo == 0


def _tentar_envio(ctx: hr.HubRunContext, email: _Email) -> str | None:
    """Uma tentativa de envio. None quando confirmado; senao, a causa."""
    try:
        enviado = _enviar_email_cli(ctx, email)
    except OSError as exc:
        return f"excecao no envio: {exc}"
    return None if enviado else "Send-OutlookEmail retornou false."


def _enviar_com_retry(ctx: hr.HubRunContext, email: _Email) -> bool:
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
        falha = _tentar_envio(ctx, email)
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


def _canal_email(
    sessao: _Sessao,
    estado: dict[str, Any],
    html: str,
    config: dict[str, Any],
) -> None:
    """Canal e-mail: destinatarios, modo teste, envio com retry e estado do canal."""
    ctx = sessao.ctx
    to, cc, bcc = _destinatarios(config)
    if not to.strip():
        hr.log(ctx, "Destinatarios 'to' nao configurados. Pulando e-mail.", "WARN")
        hr.set_delivery_success(estado, CANAL_EMAIL)
        return
    para, copia, em_teste = _destino_efetivo(to, cc)
    if em_teste:
        mensagem = f"MODO TESTE ATIVO: Redirecionando e-mail para {para}"
        hr.log(ctx, mask_sensitive(mensagem) if sessao.dry_run else mensagem, "WARN")
    email = _Email(
        para=para,
        copia=copia,
        oculta=bcc,
        assunto=f"Alerta: Receitas Bloqueadas - {datetime.now():%d/%m/%Y}",
        html=html,
        anexo=sessao.caminhos.planilha,
    )
    if sessao.dry_run:
        hr.log(
            ctx,
            mask_sensitive(
                f"[DRY-RUN] E-mail nao enviado. Destinatario={para}; "
                f"cc={copia or '-'}; bcc={bcc or '-'}; anexo={NOME_PLANILHA}; "
                f"assunto={email.assunto}."
            ),
            step="dispatch",
        )
        return
    hr.log(ctx, f"Enviando e-mail para {para}...")
    if _enviar_com_retry(ctx, email):
        hr.log(ctx, "E-mail enviado com sucesso. Consolidando estado parcial (E-mail).")
        hr.set_delivery_success(estado, CANAL_EMAIL)
        hr.save_delivery_state(estado, sessao.caminhos.entrega)
        return
    hr.log(
        ctx,
        "Falha definitiva no envio de e-mail. Canal pendente para retentativa.",
        "ERRO",
    )
    _registrar_falha(sessao, CODIGO_FALHA_CANAL_EMAIL, MSG_FALHA_EMAIL)


def _tratar_codigo_whatsapp(sessao: _Sessao, codigo: int) -> bool:
    """Traduz o exit code do Send-WhatsApp.ps1 nos ramos do run.ps1. True quando enviado."""
    ctx = sessao.ctx
    if codigo == 0:
        return True
    if codigo == CODIGO_ADIADO_WHATSAPP:
        hr.log(
            ctx,
            "WhatsApp adiado por lock ou cooldown da sessao hub-global (comportamento "
            "normal). Canal permanece pendente para a proxima execucao.",
        )
        if sessao.falha_codigo == 0:
            _registrar_falha(sessao, CODIGO_ADIADO_WHATSAPP, MSG_ADIADO_WHATSAPP)
    elif codigo == CODIGO_WHATSAPP_LOCK:
        hr.log(
            ctx,
            "WhatsApp ignorado por lock ativo (comportamento normal). Canal permanece "
            "pendente para a proxima execucao.",
        )
    elif codigo == CODIGO_WHATSAPP_DESABILITADO:
        hr.log(
            ctx, "WhatsApp desabilitado na configuracao. Canal nao entregue.", "WARN"
        )
        _registrar_falha(sessao, CODIGO_FALHA_WHATSAPP, MSG_WHATSAPP_DESABILITADO)
    elif codigo == CODIGO_WHATSAPP_REAUTENTICACAO:
        hr.log(ctx, "WhatsApp requer reautenticacao. Verifique o QR Code.", "WARN")
        _registrar_falha(
            sessao, CODIGO_WHATSAPP_REAUTENTICACAO, MSG_WHATSAPP_REAUTENTICACAO
        )
    else:
        hr.log(
            ctx,
            f"Send-WhatsApp.ps1 retornou ExitCode {codigo}. Notificacao incompleta.",
            "WARN",
        )
        # Codigo desconhecido nunca e repassado: 0, 2 e 22 nao podem virar falha que parece sucesso.
        proprio = (
            codigo if codigo > 0 and codigo not in NAO_FALHA else CODIGO_FALHA_WHATSAPP
        )
        _registrar_falha(sessao, proprio, MSG_FALHA_WHATSAPP)
    return False


def _canal_whatsapp(sessao: _Sessao, estado: dict[str, Any]) -> None:
    """Canal WhatsApp: Send-WhatsApp.ps1 em modo AUTO e estado do canal."""
    ctx = sessao.ctx
    cam = sessao.caminhos
    hr.log(ctx, f"Disparando Send-WhatsApp.ps1. ExecId={ctx.exec_id} Mode=AUTO")
    if sessao.dry_run:
        hr.log(
            ctx,
            "[DRY-RUN] WhatsApp nao enviado: Send-WhatsApp.ps1 -Mode AUTO nao foi acionado.",
            "WARN",
            step="dispatch",
        )
        return
    # Residual: o run.ps1 captura [System.Exception] neste bloco; cobre falha ao iniciar o
    # processo e ao gravar o estado do canal, sempre como falha do canal (24).
    try:
        codigo = hw.send_whatsapp(
            ctx,
            script=cam.send_whatsapp,
            work_dir=cam.pasta,
            mode="AUTO",
            config_path=cam.config_whatsapp,
            step="dispatch",
        )
        hr.log(ctx, f"Send-WhatsApp.ps1 finalizado. ExitCode={codigo}")
        estado["delivery_status"][CANAL_WHATSAPP]["exit_code"] = codigo
        if _tratar_codigo_whatsapp(sessao, codigo):
            hr.log(
                ctx,
                "WhatsApp concluido com sucesso. Consolidando estado parcial (WhatsApp).",
            )
            hr.set_delivery_success(estado, CANAL_WHATSAPP)
            hr.save_delivery_state(estado, cam.entrega)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        hr.log(ctx, f"Falha ao iniciar processo WhatsApp: {exc}", "WARN")
        estado["delivery_status"][CANAL_WHATSAPP]["exit_code"] = CODIGO_FALHA_WHATSAPP
        _registrar_falha(sessao, CODIGO_FALHA_WHATSAPP, MSG_WHATSAPP_EXCECAO)


def _exit_code_anterior(caminho: Path) -> object:
    """exit_code do WhatsApp gravado na ultima entrega: diagnostico que o run.ps1 preserva."""
    try:
        dados: object = json.loads(caminho.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    status = dados.get("delivery_status") if isinstance(dados, dict) else None
    canal = status.get(CANAL_WHATSAPP) if isinstance(status, dict) else None
    return canal.get("exit_code") if isinstance(canal, dict) else None


def _promover_estado_tmp(sessao: _Sessao) -> None:
    """Commit do estado Python: receitas_state.json.tmp vira receitas_state.json (Move-Item)."""
    ctx = sessao.ctx
    cam = sessao.caminhos
    if not cam.estado_tmp.exists():
        return
    if sessao.dry_run:
        hr.log(
            ctx,
            "[DRY-RUN] Commit de estado nao executado: o .tmp seria promovido a "
            "receitas_state.json.",
            "WARN",
            step="dispatch",
        )
        return
    os.replace(cam.estado_tmp, cam.estado)
    hr.log(ctx, f"Estado Python atualizado: {cam.estado}")


def _avisar_commit_adiado(sessao: _Sessao) -> None:
    """Explica por que o estado nao foi promovido, quando o .tmp segue pendente."""
    ctx = sessao.ctx
    if not sessao.caminhos.estado_tmp.exists():
        return
    if sessao.falha_codigo == CODIGO_ADIADO_WHATSAPP:
        hr.log(
            ctx,
            "Commit de estado adiado: WhatsApp adiado (ExitCode=22). Lote sera reavaliado "
            "na proxima execucao.",
            "INFO",
        )
    else:
        hr.log(
            ctx,
            "Commit de estado adiado: canal com falha parcial "
            f"(ExitCode={sessao.falha_codigo}). Lote sera reavaliado na proxima execucao.",
            "WARN",
        )


def _despachar(sessao: _Sessao) -> None:
    """Etapa dispatch: idempotencia granular por canal, envios e commit. Sem html, nao faz nada."""
    ctx = sessao.ctx
    cam = sessao.caminhos
    hr.log(
        ctx,
        "Verificando estado de notificacoes (Idempotencia Granular)...",
        step="dispatch",
    )
    if not cam.html.exists():
        return
    hash_atual = hr.get_last_content_hash(
        cam.estado_tmp, cam.estado, on_warning=_aviso(ctx)
    )
    estado = hr.read_delivery_state(cam.entrega, list(CANAIS), on_warning=_aviso(ctx))
    estado["delivery_status"][CANAL_WHATSAPP]["exit_code"] = _exit_code_anterior(
        cam.entrega
    )
    if hr.update_delivery_state_hash(estado, hash_atual):
        hr.log(ctx, f"Novo Hash detectado ({hash_atual}). Resetando status de entrega.")
    pendente_email = hr.delivery_pending(estado, CANAL_EMAIL, hash_atual)
    pendente_whatsapp = hr.delivery_pending(estado, CANAL_WHATSAPP, hash_atual)
    if not pendente_email and not pendente_whatsapp:
        hr.log(
            ctx,
            "Conteudo identico ao ultimo envio (Hash match) e canais entregues. "
            "Suprimindo E-mail e WhatsApp.",
        )
        _promover_estado_tmp(sessao)
        return
    html = cam.html.read_text(encoding="utf-8-sig")
    config = _ler_config(cam.config_email)
    if pendente_email:
        _canal_email(sessao, estado, html, config)
    else:
        hr.log(ctx, "E-mail ja entregue para este lote. Pulando envio.")
    if pendente_whatsapp:
        _canal_whatsapp(sessao, estado)
    else:
        hr.log(ctx, "WhatsApp ja entregue para este lote. Pulando envio.")
    if sessao.falha_codigo == 0:
        _promover_estado_tmp(sessao)
    else:
        _avisar_commit_adiado(sessao)


def _fluxo(sessao: _Sessao) -> int:
    """Etapas extract e dispatch, executadas dentro do lock RB-01."""
    ctx = sessao.ctx
    _rotacionar_log(ctx.log_path)
    _remover(sessao.caminhos.resultado)
    codigo_extracao = _extrair(sessao)
    if codigo_extracao is not None:
        return codigo_extracao
    hr.start_step(ctx, "dispatch", mensagem=MENSAGEM_DISPATCH)
    _despachar(sessao)
    hr.complete_step(ctx, ok=sessao.falha_codigo in NAO_FALHA)
    if sessao.falha_codigo != 0:
        return _encerrar(sessao, sessao.falha_codigo, sessao.falha_mensagem)
    return _encerrar(sessao, 0, "Execucao concluida com sucesso.")


def _com_lock(sessao: _Sessao) -> int:
    """Executa o fluxo protegido pelo mutex RB-01 (Enter/Exit-AutomationLock)."""
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
    _limpar_temporarios_orfaos(caminhos.pasta, datetime.now())
    hr.execution_start(ctx, f"INICIO — {AUTOMACAO} (RB-01). ExecId={ctx.exec_id}")
    if dry_run:
        hr.log(
            ctx,
            "[DRY-RUN] Validacao manual: nenhum e-mail, alerta ou WhatsApp sera enviado "
            "e o estado nao sera confirmado.",
            "WARN",
        )
    # Residual: o run.ps1 fecha com 4 (catch externo) qualquer falha fora dos caminhos esperados.
    # O pre-flight fica dentro do try para nunca deixar a telemetria RUNNING em excecao inesperada.
    try:
        codigo_preflight = _preflight(sessao)
        if codigo_preflight is not None:
            return _encerrar(
                sessao,
                codigo_preflight,
                "FALHA NO PRE-FLIGHT CHECK. Abortando execucao.",
            )
        return _com_lock(sessao)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return _encerrar(
            sessao, CODIGO_FALHA_CRITICA, f"Falha critica na orquestracao: {exc}"
        )
    finally:
        if dry_run and not tmp_existia:
            _remover(caminhos.estado_tmp)


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada: ``run_receitas_bloqueadas.py [ExecId] [--dry-run]``. Devolve o exit code."""
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
            log_dir=RB_DIR / "Logs",
            non_failure_codes=NAO_FALHA,
        ),
        exec_id=posicionais[0] if posicionais else "",
        telemetry=_telemetria_padrao(RAIZ),
        project_root=RAIZ,
    )
    return executar(ctx, Caminhos.da_pasta(RB_DIR, RAIZ), dry_run=dry_run)


if __name__ == "__main__":
    sys.exit(main())
