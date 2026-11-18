"""Runner Python da automacao Montagem de Terceirizados (MT-02), item 3 do rollout.

Substitui a orquestracao do ``run.ps1`` anterior e segue o desenho do piloto RE-03
(``Receitas Emitidas/run_receitas.py``), sobre o runner compartilhado
``lib/python/hub_runner.py``. Passo a passo:

1. housekeeping: remove ``.data_*.json`` e ``.payload_*.json`` orfaos com mais de 1 dia;
2. pre-flight: disco, paths (interpretador, extract e validate) e o check Oracle do
   ``oracle_preflight``. Como no run.ps1, nao ha check de oci.dll;
3. lock global ``MT-02``; dentro dele, rotacao do log (15 dias) e as etapas abaixo;
4. extract: ``extract_oracle.py`` grava ``.data_<ExecId>.json``; 3 tentativas com backoff
   30/60/120. Qualquer exit diferente de 0 e falha definitiva, inclusive o 2 (o run.ps1 nao
   trata idempotencia): codigo 3, ou 26/27 pelos exit codes 6/7 da camada Oracle;
5. transform: ``validate_and_generate_html.py`` grava ``.payload_<ExecId>.json``; 2
   tentativas com backoff 15/30. Sem payload nao ha divergencia nem e-mail: exit 0;
6. dispatch: idempotencia pelo SHA-256 do payload (``delivery_state.json``) e e-mail pelo
   CLI ``lib/Invoke-OutlookEmail.ps1``, que repassa -Cc e -PreviewOnly a Send-OutlookEmail.
   Uma tentativa, como o run.ps1. Falha: 25;
7. commit: ``.cache_erros.json.tmp`` vira ``.cache_erros.json`` so com o canal confirmado.

Uso: ``python run_montagem.py [ExecId] [--dry-run] [--email-preview-only]
[--email-to-test X] [--email-cc-test X]``. O ``run.ps1`` e um shim que resolve o
interpretador, chama este arquivo e repassa o exit code. Com ``--dry-run``, pre-flight,
extract e transform rodam de verdade, mas nenhum e-mail e enviado, o estado nao e
confirmado e os destinatarios aparecem mascarados no log. Uso manual de validacao.
"""

# pylint: disable=import-error
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
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

AUTOMACAO: Final[str] = "Montagem de Terceirizados"
CHAVE_LOCK: Final[str] = "MT-02"
SLUG_LOG: Final[str] = "Montagem_Terceirizados"
SLUG_TRACE: Final[str] = "mt"
MOTOR_EXTRACAO: Final[str] = "Python (Direct Oracle)"
CANAL_EMAIL: Final[str] = "email"
MT_DIR: Final[Path] = Path(__file__).resolve().parent
RAIZ: Final[Path] = MT_DIR.parent
HELPER_EMAIL: Final[Path] = RAIZ / "lib" / "Invoke-OutlookEmail.ps1"
EXIT_ERRO_FATAL: Final[int] = 1
EXIT_FALHA_EXTRACAO: Final[int] = 3
EXIT_FALHA_CANAL_EMAIL: Final[int] = 25
TENTATIVAS_EXTRACAO: Final[int] = 3
BACKOFF_EXTRACAO: Final[tuple[int, ...]] = (30, 60, 120)
TENTATIVAS_VALIDACAO: Final[int] = 2
BACKOFF_VALIDACAO: Final[tuple[int, ...]] = (15, 30)
RETENCAO_LOG_DIAS: Final[int] = 15
IDADE_TEMPORARIOS_DIAS: Final[int] = 1
ESPACO_MINIMO_GB: Final[float] = 1.0
CAMPOS_RESUMO: Final[tuple[str, ...]] = (
    "total_linhas",
    "total_erros",
    "total_pecas_nf_incorreta",
    "novos",
    "novos_pecas_nf_incorreta",
    "corrigidos",
    "corrigidos_pecas_nf_incorreta",
    "permanentes",
    "permanentes_pecas_nf_incorreta",
)
_OPCOES_COM_VALOR: Final[frozenset[str]] = frozenset(
    {"--email-to-test", "--email-cc-test"}
)
_PADRAO_TS: Final[re.Pattern[str]] = re.compile(
    r'^\{"(?:ts|timestamp)":"(\d{4}-\d{2}-\d{2})T'
)
_SEPARADOR_DESTINOS: Final[re.Pattern[str]] = re.compile(r"[;,]")


class _ErroFatal(RuntimeError):
    """Falha que o run.ps1 tratava com throw: vira ERRO FATAL e exit 1."""


@dataclass(frozen=True)
class Opcoes:
    """Argumentos da linha de comando: ExecId, --dry-run e os switches de e-mail do run.ps1."""

    exec_id: str = ""
    dry_run: bool = False
    email_preview_only: bool = False
    email_to_test: str = ""
    # Aceito por paridade: o run.ps1 antigo declarava -EmailCcTest e nunca o usava.
    email_cc_test: str = ""


def interpretar_argumentos(argumentos: Sequence[str]) -> Opcoes:
    """Le ``[ExecId] [--dry-run] [--email-preview-only] [--email-to-test X] [--email-cc-test X]``.

    Parsing manual, sem argparse: um erro de uso nao pode sair com exit 2, que o Orchestrator
    trata como idempotencia. Argumento desconhecido e ignorado.
    """
    exec_id = ""
    dry_run = False
    preview = False
    valores: dict[str, str] = {"--email-to-test": "", "--email-cc-test": ""}
    pendente = ""
    for arg in argumentos:
        if pendente:
            valores[pendente] = arg
            pendente = ""
        elif arg in _OPCOES_COM_VALOR:
            pendente = arg
        elif arg == "--dry-run":
            dry_run = True
        elif arg == "--email-preview-only":
            preview = True
        elif not exec_id and not arg.startswith("--"):
            exec_id = arg
    return Opcoes(
        exec_id=exec_id,
        dry_run=dry_run,
        email_preview_only=preview,
        email_to_test=valores["--email-to-test"],
        email_cc_test=valores["--email-cc-test"],
    )


@dataclass(frozen=True)
class Caminhos:
    """Arquivos lidos e gravados pela automacao, todos na pasta dela."""

    pasta: Path
    extract_py: Path
    validate_py: Path
    config: Path
    entrega: Path
    cache: Path

    @property
    def cache_tmp(self) -> Path:
        """Cache de erros pendente: so vira definitivo com o envio confirmado."""
        return self.cache.with_name(self.cache.name + ".tmp")

    def dados(self, exec_id: str) -> Path:
        """Arquivo de dados que o extract grava para esta execucao."""
        return self.pasta / f".data_{exec_id}.json"

    def payload(self, exec_id: str) -> Path:
        """Payload de notificacao que o validate grava para esta execucao."""
        return self.pasta / f".payload_{exec_id}.json"

    @classmethod
    def da_pasta(cls, pasta: Path) -> Caminhos:
        """Caminhos padrao da automacao a partir da pasta dela."""
        return cls(
            pasta=pasta,
            extract_py=pasta / "extract_oracle.py",
            validate_py=pasta / "validate_and_generate_html.py",
            config=pasta / "config.json",
            entrega=pasta / "delivery_state.json",
            cache=pasta / ".cache_erros.json",
        )


@dataclass
class _Sessao:
    """Estado de uma execucao: contexto de log, caminhos, modos de validacao e contagens."""

    ctx: hr.HubRunContext
    caminhos: Caminhos
    dry_run: bool
    contagens: dict[str, int] | None = None
    encerrada: bool = False
    email_preview_only: bool = False
    email_to_test: str = ""


@dataclass(frozen=True)
class _Envio:
    """Destinatarios e conteudo de um envio, com o modo de teste ja aplicado."""

    para: str
    copia: str
    assunto: str
    html: str


def _identidade(texto: str) -> str:
    """Devolve o texto sem alteracao (log oficial, sem mascara)."""
    return texto


def _aviso(ctx: hr.HubRunContext, step: str | None = None) -> Callable[[str], None]:
    """Repassa avisos das bibliotecas ao log da execucao como evento WARN."""

    def avisar(mensagem: str) -> None:
        hr.log(ctx, mensagem, "WARN", step=step)

    return avisar


def _texto(valor: object) -> str:
    """Campo do JSON como texto, como [string] do PS: null vira vazio."""
    return "" if valor is None else str(valor)


def _inteiro(dados: dict[str, Any], chave: str) -> int:
    """Campo do payload como inteiro, como [int] do PS: null vira 0."""
    valor = dados.get(chave)
    return 0 if valor is None else int(valor)


def _primeiro_preenchido(*valores: str) -> str:
    """Primeiro valor com conteudo (nao so espacos); vazio quando nenhum tem."""
    for valor in valores:
        if valor.strip():
            return valor
    return ""


def _telemetria_padrao(raiz: Path) -> hr.TelemetryClient | None:
    """Cliente HTTP da telemetria quando o .env traz ORCHESTRATOR_API_KEY."""
    chave = hr.read_api_key(raiz)
    return hr.HttpTelemetryClient(chave) if chave else None


def _modo_driver() -> str:
    """ORACLE_DRIVER_MODE normalizado; ausente vale 'auto', o padrao do .env.example."""
    bruto = os.environ.get("ORACLE_DRIVER_MODE", "").strip().lower()
    return bruto or "auto"


def _variavel_usuario(nome: str) -> str:
    """Variavel do escopo User do Windows (HKCU\\Environment), como GetEnvironmentVariable(nome, 'User').

    E o registro, nao o ambiente do processo: o run.ps1 decide o modo teste por esse valor,
    entao um AUTOMACAO_TEST_EMAIL que so existe no ambiente do processo nao ativa o teste.
    Fora do Windows, ou sem a chave, devolve vazio.
    """
    return hr.user_environment_variable(nome)


def _limpar_temporarios_orfaos(pasta: Path) -> None:
    """Remove .data_*.json e .payload_*.json com mais de um dia (Get-ChildItem do run.ps1)."""
    corte = datetime.now() - timedelta(days=IDADE_TEMPORARIOS_DIAS)
    for padrao in (".data_*.json", ".payload_*.json"):
        for arquivo in pasta.glob(padrao):
            with contextlib.suppress(OSError):
                if datetime.fromtimestamp(arquivo.stat().st_mtime) < corte:
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


def _remover_quieto(caminho: Path) -> None:
    """Remove um arquivo se existir; falha de remocao e ignorada (finally do run.ps1)."""
    with contextlib.suppress(OSError):
        caminho.unlink(missing_ok=True)


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
    return (Path(sys.executable), caminhos.extract_py, caminhos.validate_py)


def _resultado_oracle() -> hr.OraclePreflight:
    """Check Oracle do pre-flight, com o modo, a conexao e a pasta da fila do ambiente."""
    return hr.oracle_preflight(
        modo=_modo_driver(),
        conexao=os.environ.get("ORACLE_CONNECT_STRING", ""),
        pasta_fila=fila.get_queue_dir(),
    )


def _preflight(sessao: _Sessao) -> int | None:
    """Etapa preflight. Devolve o exit code de falha, ou None quando o pre-flight passa."""
    ctx = sessao.ctx
    caminhos = _caminhos_preflight(sessao.caminhos)
    hr.start_step(ctx, "preflight", mensagem="Python, Oracle e paths")
    oracle = _resultado_oracle()
    passou = _pre_flight_automacao(ctx, caminhos, checar_oracle=True, oracle=oracle)
    hr.complete_step(ctx, ok=passou)
    if passou:
        return None
    hr.log(
        ctx, "FALHA NO PRE-FLIGHT (Python/Oracle/Paths). Abortando execucao.", "ERRO"
    )
    return hr.oracle_preflight_exit_code(
        oracle,
        outros_checks=lambda: _pre_flight_automacao(ctx, caminhos, checar_oracle=False),
    )


def _extrair(sessao: _Sessao) -> hr.PythonStepResult:
    """Etapa extract: extract_oracle.py grava o arquivo de dados (3 tentativas, backoff 30/60/120)."""
    ctx = sessao.ctx
    hr.start_step(ctx, "extract", mensagem=f"Extracao nativa via {MOTOR_EXTRACAO}")
    spec = hr.PythonStepSpec(
        python_exe=sys.executable,
        script_path=str(sessao.caminhos.extract_py),
        operation_name="Extracao Oracle (extract_oracle.py)",
        step="extract",
        max_attempts=TENTATIVAS_EXTRACAO,
        backoff_seconds=BACKOFF_EXTRACAO,
    )
    resultado = hr.run_python_step(ctx, spec)
    hr.complete_step(ctx, ok=resultado.success)
    return resultado


def _falha_extracao(sessao: _Sessao, extracao: hr.PythonStepResult) -> int:
    """Falha definitiva da extracao: codigo canonico do Orchestrator, sem alerta (como o run.ps1)."""
    codigo = hr.resolve_oracle_failure_exit_code(
        extracao.exit_code, default_exit_code=EXIT_FALHA_EXTRACAO
    )
    mensagem = f"Falha definitiva na extracao nativa ({MOTOR_EXTRACAO}) (PythonExit={extracao.exit_code})."
    hr.log(sessao.ctx, mensagem, "ERRO")
    return _encerrar(sessao, codigo, mensagem)


def _ler_dados(caminho: Path) -> object:
    """Conteudo do .data_<ExecId>.json, como Get-Content | ConvertFrom-Json."""
    return json.loads(caminho.read_text(encoding="utf-8-sig"))


def _contar_registros(dados: object) -> int:
    """Registros do extract: lista conta os itens, null conta 0 e objeto unico conta 1."""
    if dados is None:
        return 0
    if isinstance(dados, list):
        return len(dados)
    return 1


def _ler_extracao(sessao: _Sessao) -> int:
    """Confere o arquivo de dados do extract e devolve a quantidade de registros."""
    ctx = sessao.ctx
    caminho = sessao.caminhos.dados(ctx.exec_id)
    if not caminho.exists():
        raise _ErroFatal(
            f"Extracao concluiu mas arquivo de dados nao foi gerado: {caminho}"
        )
    tamanho = caminho.stat().st_size
    try:
        dados = _ler_dados(caminho)
    except ValueError as exc:
        raise _ErroFatal(
            f"Arquivo de dados {caminho} gerado mas contem JSON invalido "
            f"(Tamanho: {tamanho} bytes): {exc}"
        ) from exc
    contagem = _contar_registros(dados)
    kb = round(tamanho / 1024, 2)
    hr.log(ctx, f"Dados extraidos com sucesso ({kb} KB, {contagem} registro(s)).")
    return contagem


def _transformar(sessao: _Sessao) -> None:
    """Etapa transform: validate_and_generate_html.py grava o payload (2 tentativas, backoff 15/30)."""
    ctx = sessao.ctx
    hr.start_step(ctx, "transform", mensagem="Validando dados e gerando notificacao")
    sessao.caminhos.payload(ctx.exec_id).unlink(missing_ok=True)
    spec = hr.PythonStepSpec(
        python_exe=sys.executable,
        script_path=str(sessao.caminhos.validate_py),
        operation_name="Validacao e Geracao HTML (validate_and_generate_html.py)",
        step="transform",
        max_attempts=TENTATIVAS_VALIDACAO,
        backoff_seconds=BACKOFF_VALIDACAO,
    )
    resultado = hr.run_python_step(ctx, spec)
    hr.complete_step(ctx, ok=resultado.success)
    if not resultado.success:
        raise _ErroFatal(
            f"Falha definitiva na validacao Python apos {TENTATIVAS_VALIDACAO} tentativas."
        )


def _ler_payload(caminho: Path) -> tuple[str, dict[str, Any]]:
    """Texto bruto e objeto do payload. O texto bruto e o que entra no hash do run.ps1."""
    with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
        texto = arquivo.read()
    dados: object = json.loads(texto)
    if not isinstance(dados, dict):
        raise _ErroFatal(
            "Payload de notificacao invalido: a raiz nao e um objeto JSON."
        )
    return texto, dados


def _hash_payload(texto: str) -> str:
    """SHA-256 do texto em UTF-8, em maiusculas: igual ao ComputeHash do run.ps1."""
    return hashlib.sha256(texto.encode("utf-8")).hexdigest().upper()


def _contagens_sem_payload(lidos: int) -> dict[str, int]:
    """Contagens sem notificacao: so os registros lidos (o run.ps1 zera o resto)."""
    return {"read": lidos, "errors": 0, "new": 0, "fixed": 0, "permanent": 0}


def _contagens_do_payload(dados: dict[str, Any]) -> dict[str, int]:
    """Contagens do payload nos campos que o run.ps1 grava em record_counts."""
    return {
        "read": _inteiro(dados, "total_linhas"),
        "errors": _inteiro(dados, "total_erros"),
        "new": _inteiro(dados, "novos"),
        "fixed": _inteiro(dados, "corrigidos"),
        "permanent": _inteiro(dados, "permanentes"),
    }


def _resumir_payload(ctx: hr.HubRunContext, dados: dict[str, Any]) -> None:
    """Logs do payload: assunto e resumo seguro (so contagens, sem o HTML)."""
    hr.log(ctx, f"Notificacao gerada: {_texto(dados.get('subject'))}", step="dispatch")
    partes = [f"tipo={_texto(dados.get('tipo_notificacao'))}"]
    partes.extend(f"{campo}={_inteiro(dados, campo)}" for campo in CAMPOS_RESUMO)
    hr.log(ctx, "Resumo seguro payload => " + "; ".join(partes), step="dispatch")


def _ler_config(caminho: Path) -> dict[str, Any]:
    """config.json da pasta; vazio quando o arquivo nao existe (Test-Path do run.ps1)."""
    if not caminho.exists():
        return {}
    dados: object = json.loads(caminho.read_text(encoding="utf-8-sig"))
    return dados if isinstance(dados, dict) else {}


def _bloco_email(config: dict[str, Any]) -> dict[str, Any]:
    """Bloco 'email' do config.json; vazio quando ausente ou fora do formato."""
    bloco = config.get("email")
    return bloco if isinstance(bloco, dict) else {}


def _destinos_oficiais(config: dict[str, Any]) -> tuple[str, str]:
    """Para e Cc oficiais: MT_EMAIL_TO/CC do .env tem prioridade; config.json e fallback."""
    email = _bloco_email(config)
    para = _primeiro_preenchido(
        os.environ.get("MT_EMAIL_TO", ""),
        _texto(email.get("to")),
        os.environ.get("AUTOMACAO_ALERT_EMAIL", ""),
    )
    copia = _primeiro_preenchido(
        os.environ.get("MT_EMAIL_CC", ""), _texto(email.get("cc"))
    )
    return para, copia


def _e_modo_teste(teste_para: str) -> bool:
    """Modo teste como o run.ps1: ORCHESTRATOR_TEST_MODE vence; senao -EmailToTest ou o AUTOMACAO_TEST_EMAIL do escopo User."""
    forcado = os.environ.get("ORCHESTRATOR_TEST_MODE", "").lower()
    if forcado in ("true", "false"):
        return forcado == "true"
    return bool(teste_para.strip()) or bool(
        _variavel_usuario("AUTOMACAO_TEST_EMAIL").strip()
    )


def _alvo_teste(teste_para: str) -> str:
    """Destinatario do modo teste: -EmailToTest, depois AUTOMACAO_TEST_EMAIL (User), depois AUTOMACAO_ALERT_EMAIL."""
    return _primeiro_preenchido(
        teste_para,
        _variavel_usuario("AUTOMACAO_TEST_EMAIL"),
        os.environ.get("AUTOMACAO_ALERT_EMAIL", ""),
    )


def _mascarar_um(endereco: str) -> str:
    """Um endereco mascarado para o log do dry-run: primeira letra, *** e o dominio."""
    usuario, arroba, dominio = endereco.partition("@")
    if not arroba:
        return "***"
    return f"{usuario[:1]}***@{dominio}"


def _mascarar(enderecos: str) -> str:
    """Lista de destinatarios mascarada para o log; vazio quando nao ha nenhum."""
    partes = [p.strip() for p in _SEPARADOR_DESTINOS.split(enderecos) if p.strip()]
    return "; ".join(_mascarar_um(parte) for parte in partes)


def _montar_envio(sessao: _Sessao, dados: dict[str, Any]) -> _Envio:
    """Escolhe o modo (teste ou oficial), os destinatarios e o conteudo; loga o modo como o run.ps1."""
    ctx = sessao.ctx
    exibir: Callable[[str], str] = _mascarar if sessao.dry_run else _identidade
    config = _ler_config(sessao.caminhos.config)
    assunto = _texto(dados.get("subject"))
    html = _texto(dados.get("html"))
    if _e_modo_teste(sessao.email_to_test):
        alvo = _alvo_teste(sessao.email_to_test)
        hr.log(ctx, f"MODO TESTE ATIVO: Redirecionando para {exibir(alvo)}", "WARN")
        return _Envio(para=alvo, copia="", assunto=assunto, html=html)
    para, copia = _destinos_oficiais(config)
    hr.log(ctx, f"MODO OFICIAL ATIVO (config.json): Disparando para {exibir(para)}")
    return _Envio(para=para, copia=copia, assunto=assunto, html=html)


def _executor_envio(
    copia: str, *, preview: bool
) -> Callable[[Path, list[str]], tuple[int, str]]:
    """Executor do envio pela CLI lib/Invoke-OutlookEmail.ps1, com os extras da MT-02.

    Os argumentos base (-To, -Subject, -HtmlBodyFile, -ExecId, -LogPath) vem do hub_runner. O
    executor so acrescenta -Cc (quando ha copia) e -PreviewOnly, como o run.ps1 antigo passava.
    """
    extras: list[str] = []
    if copia.strip():
        extras.extend(["-Cc", copia])
    if preview:
        extras.append("-PreviewOnly")

    def executar_helper(_script: Path, argumentos: list[str]) -> tuple[int, str]:
        return hr.executar_cli_outlook(HELPER_EMAIL, [*argumentos, *extras])

    return executar_helper


def _enviar(sessao: _Sessao, envio: _Envio) -> bool:
    """Envio por uma tentativa, como o run.ps1. Dry-run so loga, com os destinatarios mascarados."""
    ctx = sessao.ctx
    if sessao.dry_run:
        hr.log(
            ctx,
            "[DRY-RUN] E-mail nao enviado. "
            f"Destinatario={_mascarar(envio.para)}; "
            f"copia={_mascarar(envio.copia) or '-'}; assunto={envio.assunto}.",
            step="dispatch",
        )
        return True
    return hr.send_outlook_email(
        ctx,
        to=envio.para,
        subject=envio.assunto,
        html_body=envio.html,
        executor=_executor_envio(envio.copia, preview=sessao.email_preview_only),
    )


def _despachar(sessao: _Sessao, dados: dict[str, Any], texto: str) -> bool:
    """Idempotencia por hash e envio. True quando o canal esta ok (enviado, suprimido ou simulado)."""
    ctx = sessao.ctx
    caminhos = sessao.caminhos
    hash_atual = _hash_payload(texto)
    estado = hr.read_delivery_state(
        caminhos.entrega, [CANAL_EMAIL], on_warning=_aviso(ctx)
    )
    if hr.update_delivery_state_hash(estado, hash_atual):
        hr.log(ctx, "Mudanca de conteudo detectada. Resetando status de entrega.")
    if not hr.delivery_pending(estado, CANAL_EMAIL):
        hr.log(ctx, "E-mail ja enviado para este conteudo (Hash Match). Suprimindo.")
        return True
    envio = _montar_envio(sessao, dados)
    if not _enviar(sessao, envio):
        return False
    if not sessao.dry_run:
        hr.log(ctx, "E-mail enviado com sucesso. Consolidando estado parcial (E-mail).")
        hr.set_delivery_success(estado, CANAL_EMAIL)
        hr.save_delivery_state(estado, caminhos.entrega)
    return True


def _confirmar_cache(sessao: _Sessao) -> None:
    """Commit do cache de erros: promove o .tmp ao definitivo (nao roda em dry-run)."""
    ctx = sessao.ctx
    caminhos = sessao.caminhos
    if sessao.dry_run:
        hr.log(
            ctx,
            "[DRY-RUN] Commit de estado nao executado: "
            f"{caminhos.cache_tmp.name} seria promovido a {caminhos.cache.name}.",
            step="dispatch",
        )
        return
    hr.log(ctx, "Confirmando compromisso de estado (Commit Success)...")
    if caminhos.cache_tmp.exists():
        os.replace(caminhos.cache_tmp, caminhos.cache)
        hr.log(ctx, f"Cache de erros consolidado: {caminhos.cache}")


def _disparar(sessao: _Sessao) -> bool:
    """Etapa dispatch do payload: resumo, idempotencia, envio e commit. True quando o canal esta ok."""
    ctx = sessao.ctx
    caminhos = sessao.caminhos
    hr.start_step(ctx, "dispatch", mensagem="Envio de e-mail via Outlook")
    texto, dados = _ler_payload(caminhos.payload(ctx.exec_id))
    sessao.contagens = _contagens_do_payload(dados)
    _resumir_payload(ctx, dados)
    canal_ok = _despachar(sessao, dados, texto)
    if canal_ok:
        _confirmar_cache(sessao)
    else:
        hr.log(
            ctx,
            "Falha no envio de e-mail. O cache NAO sera atualizado para garantir retentativa.",
            "WARN",
        )
    caminhos.payload(ctx.exec_id).unlink(missing_ok=True)
    caminhos.dados(ctx.exec_id).unlink(missing_ok=True)
    hr.complete_step(ctx, ok=canal_ok)
    return canal_ok


def _fluxo(sessao: _Sessao) -> int:
    """Etapas extract, transform e dispatch, dentro do lock (corpo do try do run.ps1)."""
    ctx = sessao.ctx
    _rotacionar_log(ctx.log_path)
    sessao.caminhos.dados(ctx.exec_id).unlink(missing_ok=True)
    extracao = _extrair(sessao)
    if not extracao.success:
        return _falha_extracao(sessao, extracao)
    lidos = _ler_extracao(sessao)
    _transformar(sessao)
    if not sessao.caminhos.payload(ctx.exec_id).exists():
        sessao.contagens = _contagens_sem_payload(lidos)
        hr.log(
            ctx,
            "Nenhuma divergencia ou mudanca de estado. Nenhuma notificacao enviada.",
        )
        return _encerrar(sessao, 0, "Execucao concluida com sucesso.")
    if not _disparar(sessao):
        return _encerrar(
            sessao,
            EXIT_FALHA_CANAL_EMAIL,
            "Execucao concluida com falha parcial no canal E-mail.",
        )
    return _encerrar(sessao, 0, "Execucao concluida com sucesso.")


def _limpar_temporarios(sessao: _Sessao) -> None:
    """Finally do run.ps1: remove .data e .payload desta execucao e o cache pendente nao confirmado."""
    ctx = sessao.ctx
    for caminho in (
        sessao.caminhos.dados(ctx.exec_id),
        sessao.caminhos.payload(ctx.exec_id),
        sessao.caminhos.cache_tmp,
    ):
        _remover_quieto(caminho)


def _gravar_contagens(contagens: dict[str, int]) -> Path:
    """Grava record_counts num JSON temporario, no formato que hub_runner.finish le."""
    descritor, nome = tempfile.mkstemp(prefix="mt_contagens_", suffix=".json")
    with os.fdopen(descritor, "w", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps({"record_counts": contagens}))
    return Path(nome)


def _encerrar(sessao: _Sessao, codigo: int, mensagem: str) -> int:
    """Unico ponto de saida: execution.end e telemetria, uma vez so (como Write-Fim)."""
    if sessao.encerrada:
        return codigo
    sessao.encerrada = True
    if sessao.contagens is None:
        return hr.finish(sessao.ctx, codigo, mensagem)
    caminho = _gravar_contagens(sessao.contagens)
    try:
        return hr.finish(sessao.ctx, codigo, mensagem, record_counts_path=caminho)
    finally:
        _remover_quieto(caminho)


def _fluxo_protegido(sessao: _Sessao) -> int:
    """Fluxo dentro do lock: excecao vira ERRO FATAL (exit 1) e os temporarios saem no finally."""
    try:
        return _fluxo(sessao)
    # Residual: as falhas esperadas (_ErroFatal, OSError, ValueError) e as demais (KeyError,
    # RuntimeError...) recebem o mesmo fim do catch [System.Exception] do run.ps1: ERRO FATAL,
    # exit 1 e fechamento da execucao. Sem isso a excecao escapa sem execution.end nem telemetria.
    except Exception as exc:  # pylint: disable=broad-exception-caught
        mensagem = f"ERRO FATAL NA EXECUCAO NATIVA: {exc}"
        hr.log(sessao.ctx, mensagem, "ERRO")
        return _encerrar(sessao, EXIT_ERRO_FATAL, mensagem)
    finally:
        _limpar_temporarios(sessao)


def _com_lock(sessao: _Sessao) -> int:
    """Executa o fluxo protegido pelo mutex MT-02 (Enter/Exit-AutomationLock)."""
    ctx = sessao.ctx
    hr.start_step(ctx, "lock", mensagem="Adquirindo lock global")
    with contextlib.ExitStack() as pilha:
        try:
            pilha.enter_context(
                hr.AutomationMutex(CHAVE_LOCK, on_warning=_aviso(ctx, "lock"))
            )
        except (hr.LockTimeoutError, OSError) as exc:
            hr.complete_step(ctx, ok=False)
            mensagem = f"Falha ao adquirir lock global: {exc}"
            hr.log(ctx, mensagem, "ERRO")
            return _encerrar(sessao, EXIT_ERRO_FATAL, mensagem)
        hr.log(
            ctx,
            f"Lock global adquirido com sucesso (Mutex: {hr.nome_mutex(CHAVE_LOCK)}).",
            "DEBUG",
            step="lock",
        )
        hr.complete_step(ctx)
        return _fluxo_protegido(sessao)


def executar(
    ctx: hr.HubRunContext,
    caminhos: Caminhos,
    *,
    dry_run: bool = False,
    email_preview_only: bool = False,
    email_to_test: str = "",
) -> int:
    """Roda o fluxo completo e devolve o exit code (quem chama faz sys.exit)."""
    sessao = _Sessao(
        ctx=ctx,
        caminhos=caminhos,
        dry_run=dry_run,
        email_preview_only=email_preview_only,
        email_to_test=email_to_test,
    )
    _limpar_temporarios_orfaos(caminhos.pasta)
    hr.execution_start(ctx, f"INICIO — {AUTOMACAO} (MT-02). ExecId={ctx.exec_id}")
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
                "FALHA NO PRE-FLIGHT (Python/Oracle/Paths).",
            )
        return _com_lock(sessao)
    # Residual: falha inesperada antes do lock (pre-flight). Sem este catch a execucao ficaria
    # RUNNING no Orchestrator; aqui ela fecha com ERRO FATAL e exit 1, como o catch do run.ps1.
    except Exception as exc:  # pylint: disable=broad-exception-caught
        hr.log(ctx, f"ERRO FATAL: {exc}", "ERRO")
        return _encerrar(sessao, EXIT_ERRO_FATAL, f"ERRO FATAL: {exc}")


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada: ``run_montagem.py [ExecId] [opcoes]``. Devolve o exit code."""
    ensure_utf8_streams()
    opcoes = interpretar_argumentos(list(sys.argv[1:] if argv is None else argv))
    hr.load_env_file(RAIZ)
    ctx = hr.create_run_context(
        hr.AutomationSpec(
            automacao=AUTOMACAO,
            slug=SLUG_LOG,
            trace_slug=SLUG_TRACE,
            lock_key=CHAVE_LOCK,
            log_dir=MT_DIR / "Logs",
            non_failure_codes=(0,),
        ),
        exec_id=opcoes.exec_id,
        telemetry=_telemetria_padrao(RAIZ),
        project_root=RAIZ,
    )
    return executar(
        ctx,
        Caminhos.da_pasta(MT_DIR),
        dry_run=opcoes.dry_run,
        email_preview_only=opcoes.email_preview_only,
        email_to_test=opcoes.email_to_test,
    )


if __name__ == "__main__":
    sys.exit(main())
