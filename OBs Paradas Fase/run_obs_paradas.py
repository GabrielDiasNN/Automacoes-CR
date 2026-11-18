"""Runner Python da automacao OBs Paradas Fase (OBP-04), rollout do item 3 (migracao).

Substitui a orquestracao do ``run.ps1`` anterior e reproduz o mesmo fluxo, passo a passo:

1. pre-flight: Oracle (ORACLE_DRIVER_MODE e, no modo ``queue``, o worker da fila), paths,
   disco e o destino do WhatsApp (``whatsapp-config.json``);
2. lock global ``OBP-04``, rotacao do log e limpeza dos Chrome zumbis do motor WhatsApp;
3. extract: ``extract_obs.py`` com stdout como log, 3 tentativas e backoff 30/60/120;
   exit 2 encerra com 2 por idempotencia;
4. transform: ``generate_phase_cards.py`` (uma tentativa), que grava ``phase_cards.json``;
5. dispatch: um lote BATCH pelo ``lib/Send-WhatsApp.ps1`` (sessao unica), com o resultado
   por fase gravado em ``delivery_state.json``;
6. commit: ``obs_state.json.tmp`` promovido a ``obs_state.json`` so com todas as fases entregues.

Uso: ``python run_obs_paradas.py [ExecId] [--dry-run]``. O ``run.ps1`` e um shim que resolve o
interpretador, chama este arquivo e repassa o exit code, porque o worker le o exit code de
``powershell.exe -File run.ps1 <ExecId>``. Com ``--dry-run``, pre-flight, extract e transform
rodam de verdade, mas nenhum WhatsApp e enviado, nenhum lote e gravado e nenhum estado e
confirmado: a execucao so loga o que faria. Uso manual de validacao.
"""

# pylint: disable=import-error
from __future__ import annotations

import base64
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Final, NoReturn

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "python")
)

import hub_runner as hr  # noqa: E402
import hub_whatsapp as hw  # noqa: E402
import oracle_queue as fila  # noqa: E402
from automation_log import ensure_utf8_streams  # noqa: E402

AUTOMACAO: Final[str] = "OBs Paradas Fase"
CHAVE_LOCK: Final[str] = "OBP-04"
SLUG_LOG: Final[str] = "ObsParadasFase"
SLUG_TRACE: Final[str] = "obp"
MOTOR_EXTRACAO: Final[str] = "Python (extract_obs.py)"
OBP_DIR: Final[Path] = Path(__file__).resolve().parent
RAIZ: Final[Path] = OBP_DIR.parent
NAO_FALHA: Final[tuple[int, ...]] = (0, hr.EXIT_IDEMPOTENTE, 22)
EXIT_ERRO_FATAL: Final[int] = 1
EXIT_FALHA_EXTRACAO: Final[int] = 3
EXIT_FALHA_CRITICA: Final[int] = 4
EXIT_REAUTENTICACAO: Final[int] = 21
EXIT_ADIADO: Final[int] = 22
TENTATIVAS_EXTRACAO: Final[int] = 3
BACKOFF_EXTRACAO: Final[tuple[int, ...]] = (30, 60, 120)
RETENCAO_LOG_DIAS: Final[int] = 15
CLIENTE_PADRAO: Final[str] = "hub-global"
MODO_LOTE: Final[str] = "BATCH"
TIMEOUT_LIMPEZA_S: Final[float] = 60.0
MENSAGEM_IDEMPOTENCIA: Final[str] = (
    "Idempotencia confirmada — nenhuma mudanca desde o ultimo envio."
)
MENSAGEM_JA_ENTREGUE: Final[str] = (
    "Entrega ja realizada — nenhum novo envio necessario."
)
MENSAGEM_FALHA_ENVIO: Final[str] = (
    "Uma ou mais fases falharam no envio WhatsApp. Verifique os logs."
)
MENSAGEM_SUCESSO: Final[str] = "Execucao concluida com sucesso."
MENSAGEM_DRY_RUN_FIM: Final[str] = (
    "DRY-RUN concluido: nenhum envio WhatsApp e nenhum commit de estado."
)
MENSAGEM_ADIADO: Final[str] = (
    "WhatsApp adiado por lock ou cooldown da sessao hub-global."
)
_PADRAO_TS: Final[re.Pattern[str]] = re.compile(
    r'^\{"(?:ts|timestamp)":"(\d{4}-\d{2}-\d{2})T'
)
_COMENTARIO_INLINE: Final[re.Pattern[str]] = re.compile(r"\s+#.*$")
# Limpeza dos Chrome zumbis do motor WhatsApp (Invoke-CimInstance do run.ps1), em
# EncodedCommand para nao depender de aspas. O caminho da sessao chega por HUB_WA_AUTH_DIR.
# O daemon WhatsApp (opt-in, 1.3.117) usa o mesmo perfil e vive entre execucoes: ele e toda
# a sua arvore de descendentes ficam fora da limpeza, como em Select-WhatsAppStaleProcessIds.
_SCRIPT_LIMPEZA_CHROME: Final[str] = """\
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$pasta = $env:HUB_WA_AUTH_DIR
$todos = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
$filhos = @{}
foreach ($p in $todos) {
    $pai = [int]$p.ParentProcessId
    if (-not $filhos.ContainsKey($pai)) { $filhos[$pai] = New-Object 'System.Collections.Generic.List[int]' }
    $filhos[$pai].Add([int]$p.ProcessId)
}
$protegidos = New-Object 'System.Collections.Generic.HashSet[int]'
$fila = New-Object 'System.Collections.Generic.Queue[int]'
foreach ($p in $todos) {
    if ($p.Name -eq 'node.exe' -and $p.CommandLine -and $p.CommandLine -like '*whatsapp-daemon.js*') {
        if ($protegidos.Add([int]$p.ProcessId)) { $fila.Enqueue([int]$p.ProcessId) }
    }
}
while ($fila.Count -gt 0) {
    $atual = $fila.Dequeue()
    if (-not $filhos.ContainsKey($atual)) { continue }
    foreach ($f in $filhos[$atual]) { if ($protegidos.Add($f)) { $fila.Enqueue($f) } }
}
$zumbis = @($todos | Where-Object {
    $_.Name -eq 'chrome.exe' -and $_.CommandLine -and $_.CommandLine.ToLower().Contains($pasta) -and
    -not $protegidos.Contains([int]$_.ProcessId) })
Write-Output ('TOTAL ' + $zumbis.Count)
foreach ($proc in $zumbis) {
    try { Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop }
    catch [System.Exception] { Write-Output ('FALHA ' + $proc.ProcessId + ' ' + $_.Exception.Message) }
}
"""


@dataclass(frozen=True)
class Caminhos:  # pylint: disable=too-many-instance-attributes
    # Um campo por arquivo que o run.ps1 le ou grava; agrupar os esconderia.
    """Arquivos lidos e gravados pela automacao, todos na pasta dela (raiz = pasta pai)."""

    raiz: Path
    pasta: Path
    extract_py: Path
    generate_py: Path
    phase_cards: Path
    wa_config: Path
    entrega: Path
    obs_state: Path
    obs_state_tmp: Path
    resultado: Path
    batch_input: Path
    batch_result: Path

    @classmethod
    def da_pasta(cls, pasta: Path) -> Caminhos:
        """Caminhos padrao da automacao a partir da pasta dela."""
        return cls(
            raiz=pasta.parent,
            pasta=pasta,
            extract_py=pasta / "extract_obs.py",
            generate_py=pasta / "generate_phase_cards.py",
            phase_cards=pasta / "phase_cards.json",
            wa_config=pasta / "whatsapp-config.json",
            entrega=pasta / "delivery_state.json",
            obs_state=pasta / "obs_state.json",
            obs_state_tmp=pasta / "obs_state.json.tmp",
            resultado=pasta / "obs_result.json",
            batch_input=pasta / "batch_input.json",
            batch_result=pasta / "batch_result.json",
        )


@dataclass
class _Sessao:
    """Estado de uma execucao: contexto de log, modo de validacao e marcas de saida."""

    ctx: hr.HubRunContext
    caminhos: Caminhos
    dry_run: bool
    resultado_fresco: bool = False
    encerrado: bool = False
    protegida: bool = False


@dataclass(frozen=True)
class _Fase:
    """Um card de phase_cards.json, com os campos que o run.ps1 usa."""

    phase_key: str
    phase_display: str
    image_path: str
    caption: str


class _SaidaAntecipada(Exception):
    """Saida do fluxo, o equivalente ao Exit-WithCode do run.ps1; quem chama encerra com ela."""

    def __init__(
        self, codigo: int, mensagem: str, contagens: dict[str, int] | None = None
    ) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.contagens = contagens


def _sair(
    codigo: int, mensagem: str, contagens: dict[str, int] | None = None
) -> NoReturn:
    """Encerra o fluxo com o codigo do run.ps1 (a saida chega a _rodar_fluxo ou a executar)."""
    raise _SaidaAntecipada(codigo, mensagem, contagens)


def _aviso(ctx: hr.HubRunContext, step: str | None = None) -> Callable[[str], None]:
    """Repassa avisos das bibliotecas ao log da execucao como evento WARN."""

    def avisar(mensagem: str) -> None:
        hr.log(ctx, mensagem, "WARN", step=step)

    return avisar


def _texto(valor: object) -> str:
    """Valor do JSON como texto, como o [string] do PowerShell: nulo vira vazio."""
    return "" if valor is None else str(valor)


def _verdadeiro_ps(valor: object) -> bool:
    """Truthiness do PowerShell: nulo, falso, zero, texto vazio e lista vazia valem falso."""
    if valor is None:
        return False
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return valor != 0
    if isinstance(valor, str):
        return valor != ""
    if isinstance(valor, list):
        return len(valor) > 0
    return True


def _campo(objeto: object, nome: str) -> object:
    """Propriedade de um objeto JSON; quem nao e objeto devolve nulo, como no PowerShell."""
    if not isinstance(objeto, dict):
        return None
    return objeto.get(nome)


def _como_lista(valor: object) -> list[Any]:
    """Valor como lista, como @($x): nulo vira lista vazia e escalar vira um item."""
    if valor is None:
        return []
    if isinstance(valor, list):
        return list(valor)
    return [valor]


def _mesma_chave(valor: object, chave: str) -> bool:
    """Compara uma chave sem diferenciar caixa, como o -eq do PowerShell (nulo nunca casa)."""
    return valor is not None and str(valor).casefold() == chave.casefold()


def _mesmo_texto(a: str, b: str) -> bool:
    """Comparacao de hash sem caixa, como o -ne do PowerShell."""
    return a.casefold() == b.casefold()


def _agora() -> str:
    """Carimbo dd/MM/yyyy HH:mm:ss, como Get-Date -Format do run.ps1."""
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _mascarar_destino(destino: str) -> str:
    """Destino do WhatsApp para o log: so os ultimos 4 digitos do numero, o dominio fica."""
    local, arroba, dominio = destino.partition("@")
    oculto = "*" * max(len(local) - 4, 0) + local[-4:]
    return oculto + (arroba + dominio if arroba else "")


def _ler_json(caminho: Path) -> object:
    """JSON do arquivo com BOM tolerado (ConvertFrom-Json). Leitura ou parse falho levanta."""
    dados: object = json.loads(caminho.read_text(encoding="utf-8-sig"))
    return dados


def _gravar_json(caminho: Path, dados: object) -> None:
    """Grava JSON em UTF-8 sem BOM."""
    caminho.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
    )


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


def _carregar_env(raiz: Path) -> str | None:
    """Carrega o .env da raiz no ambiente (Import-HubEnv). Devolve o erro de leitura, se houver."""
    caminho = raiz / ".env"
    if not caminho.exists():
        return None
    try:
        conteudo = caminho.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        return str(exc)
    for linha in conteudo.splitlines():
        par = _ler_linha_env(linha)
        if par is not None:
            os.environ[par[0]] = par[1]
    return None


def _telemetria_padrao(raiz: Path) -> hr.TelemetryClient | None:
    """Cliente HTTP da telemetria quando o .env traz ORCHESTRATOR_API_KEY."""
    chave = hr.read_api_key(raiz)
    return hr.HttpTelemetryClient(chave) if chave else None


def _modo_driver() -> str:
    """ORACLE_DRIVER_MODE normalizado; ausente vale 'auto', o padrao do .env.example."""
    bruto = os.environ.get("ORACLE_DRIVER_MODE", "").strip().lower()
    return bruto or "auto"


def _resultado_oracle() -> hr.OraclePreflight:
    """Check Oracle do pre-flight (Test-AutomationPreFlight -CheckOracle), com modo, conexao e fila."""
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
    if livre < 1.0:
        return f"ERRO: Disco critico ({livre} GB)"
    return f"OK: Disco estavel ({livre} GB)"


def _linha_caminho(caminho: Path) -> str:
    """Linha de um path do pre-flight (CheckPaths)."""
    if caminho.exists():
        return f"OK: Path: {caminho.name}"
    return f"ERRO: Path inacessivel: {caminho.name}"


def _caminhos_preflight(caminhos: Caminhos) -> tuple[Path, ...]:
    """Interpretador e arquivos que o pre-flight confere (CheckPaths do run.ps1)."""
    return (
        Path(sys.executable),
        caminhos.extract_py,
        caminhos.generate_py,
        caminhos.wa_config,
    )


def _pre_flight_automacao(
    ctx: hr.HubRunContext,
    caminhos: Sequence[Path],
    oracle: hr.OraclePreflight | None = None,
) -> bool:
    """Test-AutomationPreFlight: disco, paths e, quando pedido, as linhas do check Oracle."""
    hr.log(ctx, "Iniciando Pre-Flight Check...")
    resultados = [_linha_disco(ctx.raiz)]
    resultados.extend(_linha_caminho(caminho) for caminho in caminhos)
    if oracle is not None:
        resultados.extend(oracle.linhas)
    ok = not any(linha.startswith(("ERRO:", "FAIL:")) for linha in resultados)
    hr.log(ctx, "Pre-Flight: " + " | ".join(resultados), "INFO" if ok else "ERRO")
    return ok


def _resolver_destino(target: object, origem: Path) -> str:
    """Destino real do envio (Resolve-WhatsAppTarget): contactIdEnv vence; o contactId e so placeholder."""
    sufixo = f" ({origem})"
    if not isinstance(target, dict):
        raise ValueError(
            f"Destino do WhatsApp ausente: 'target'{sufixo} nao declara contactId, "
            "contactPhone nem contactIdEnv."
        )
    variavel = target.get("contactIdEnv")
    if _verdadeiro_ps(variavel):
        valor = os.environ.get(str(variavel), "")
        if not valor.strip():
            raise ValueError(
                f"Destino do WhatsApp ausente: variavel de ambiente '{variavel}'{sufixo} "
                "nao esta definida ou esta vazia. O contactId do config e apenas "
                "placeholder de schema, nunca um destino real."
            )
        return valor
    placeholder = (
        target.get("contactId")
        if _verdadeiro_ps(target.get("contactId"))
        else target.get("contactPhone")
    )
    if placeholder is None or not str(placeholder).strip():
        raise ValueError(
            f"Destino do WhatsApp ausente: 'target'{sufixo} nao declara contactId, "
            "contactPhone nem contactIdEnv."
        )
    return str(placeholder)


def _checar_whatsapp(ctx: hr.HubRunContext, caminho: Path) -> bool:
    """Check WhatsApp do pre-flight: o destino do target precisa resolver."""
    try:
        cfg = _ler_json(caminho)
        _resolver_destino(_campo(cfg, "target"), caminho)
    except (OSError, ValueError) as exc:
        hr.log(ctx, f"Pre-Flight WhatsApp falhou: {exc}", "ERRO", step="preflight")
        return False
    return True


def _outros_checks(ctx: hr.HubRunContext, caminhos: Caminhos) -> bool:
    """OutrosChecks do pre-flight: paths e WhatsApp, sem o check Oracle (como no run.ps1)."""
    basico = _pre_flight_automacao(ctx, _caminhos_preflight(caminhos))
    return basico and _checar_whatsapp(ctx, caminhos.wa_config)


def _preflight(sessao: _Sessao) -> None:
    """Etapa preflight. Reprovada, sai com o codigo do Oracle (26 so no modo queue) ou 9."""
    ctx = sessao.ctx
    caminhos = sessao.caminhos
    hr.start_step(ctx, "preflight", mensagem="Oracle, Python e WhatsApp configurados")
    oracle = _resultado_oracle()
    passou = _pre_flight_automacao(
        ctx, _caminhos_preflight(caminhos), oracle
    ) and _checar_whatsapp(ctx, caminhos.wa_config)
    hr.complete_step(ctx, ok=passou)
    if not passou:
        codigo = hr.oracle_preflight_exit_code(
            oracle, outros_checks=lambda: _outros_checks(ctx, caminhos)
        )
        _sair(codigo, "FALHA NO PRE-FLIGHT CHECK. Abortando.")


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
    """Remove do jsonl os eventos anteriores a retencao (Invoke-LogRotation -KeepDays 15)."""
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


def _interpretar_limpeza(linhas: Sequence[str]) -> tuple[int, list[tuple[str, str]]]:
    """Total de Chrome zumbis e as falhas de encerramento, a partir da saida do PowerShell."""
    total = 0
    falhas: list[tuple[str, str]] = []
    for linha in linhas:
        tipo, _, resto = linha.partition(" ")
        if tipo == "TOTAL" and resto.strip().isdigit():
            total = int(resto)
        elif tipo == "FALHA":
            pid, _, motivo = resto.partition(" ")
            falhas.append((pid, motivo))
    return total, falhas


def _executar_limpeza_chrome(pasta_auth: str) -> list[str]:
    """Roda a limpeza em powershell.exe (Get-CimInstance e Stop-Process) e devolve a saida."""
    codificado = base64.b64encode(_SCRIPT_LIMPEZA_CHROME.encode("utf-16-le")).decode(
        "ascii"
    )
    ambiente = {**os.environ, "HUB_WA_AUTH_DIR": pasta_auth}
    resultado = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-EncodedCommand",
            codificado,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT_LIMPEZA_S,
        check=False,
        env=ambiente,
    )
    return resultado.stdout.splitlines()


def _limpar_chrome_zumbis(sessao: _Sessao) -> None:
    """Cleanup cirurgico: encerra Chrome do motor WhatsApp (so o perfil do projeto)."""
    ctx = sessao.ctx
    if sessao.dry_run:
        hr.log(
            ctx,
            "[DRY-RUN] Limpeza de Chrome zumbi do motor WhatsApp nao executada.",
            step="cleanup",
        )
        return
    pasta_auth = hw.get_whatsapp_auth_path().lower()
    try:
        saida = _executar_limpeza_chrome(pasta_auth)
    except (OSError, subprocess.SubprocessError) as exc:
        hr.log(
            ctx,
            f"Aviso: limpeza de Chrome zumbi nao executada: {exc}",
            "WARN",
            step="cleanup",
        )
        return
    total, falhas = _interpretar_limpeza(saida)
    if total > 0:
        hr.log(
            ctx,
            f"Limpando {total} processo(s) Chrome zumbi do motor WhatsApp...",
            step="cleanup",
        )
    for pid, motivo in falhas:
        hr.log(
            ctx,
            f"Aviso: nao foi possivel encerrar Chrome PID={pid}: {motivo}",
            "WARN",
            step="cleanup",
        )


def _codigo_falha_extracao(resultado: hr.PythonStepResult) -> int:
    """Codigo canonico da falha definitiva da extracao (6 vira 26, 7 vira 27, o resto 3)."""
    return hr.resolve_oracle_failure_exit_code(
        resultado.exit_code, default_exit_code=EXIT_FALHA_EXTRACAO
    )


def _extrair(sessao: _Sessao) -> hr.PythonStepResult:
    """Etapa extract: extract_obs.py com 3 tentativas e backoff 30/60/120; stdout vai ao log."""
    ctx = sessao.ctx
    hr.start_step(ctx, "extract", mensagem=f"Extracao Oracle via {MOTOR_EXTRACAO}")
    spec = hr.PythonStepSpec(
        python_exe=sys.executable,
        script_path=str(sessao.caminhos.extract_py),
        operation_name="Extracao OBs Paradas (extract_obs.py)",
        step="extract",
        max_attempts=TENTATIVAS_EXTRACAO,
        backoff_seconds=BACKOFF_EXTRACAO,
    )
    resultado = hr.run_python_step(ctx, spec)
    ok = resultado.success or resultado.idempotent
    if ok:
        sessao.resultado_fresco = True
    hr.complete_step(ctx, ok=ok)
    return resultado


def _fase_de(item: object) -> _Fase:
    """Card de phase_cards.json: texto vazio quando o campo e nulo, como no run.ps1."""
    chave = _texto(_campo(item, "phase_key"))
    imagem = (
        _texto(_campo(item, "image_path"))
        if _verdadeiro_ps(_campo(item, "image_path"))
        else ""
    )
    exibicao = (
        _texto(_campo(item, "phase_display"))
        if _verdadeiro_ps(_campo(item, "phase_display"))
        else chave
    )
    return _Fase(
        phase_key=chave,
        phase_display=exibicao,
        image_path=imagem,
        caption=_texto(_campo(item, "caption")),
    )


def _ler_fases(caminho: Path) -> list[_Fase]:
    """Le phase_cards.json. Ausente ou invalido sai com 4; vazio sai com 2 (idempotencia)."""
    if not caminho.exists():
        _sair(EXIT_FALHA_CRITICA, "phase_cards.json nao foi gerado.")
    try:
        bruto = _ler_json(caminho)
    except (OSError, ValueError) as exc:
        raise _SaidaAntecipada(
            EXIT_FALHA_CRITICA,
            f"Falha ao interpretar '{caminho}' como JSON: {exc}",
        ) from exc
    itens = _como_lista(bruto)
    if not itens:
        _sair(2, "phase_cards.json vazio — nenhuma fase para enviar.")
    return [_fase_de(item) for item in itens]


def _gerar_cards(sessao: _Sessao) -> list[_Fase]:
    """Etapa transform: generate_phase_cards.py em uma tentativa, como o Invoke-NativeProcess."""
    ctx = sessao.ctx
    caminhos = sessao.caminhos
    hr.start_step(
        ctx,
        "transform",
        mensagem="Gerando cards de imagem por fase (generate_phase_cards.py)",
    )
    spec = hr.PythonStepSpec(
        python_exe=sys.executable,
        script_path=str(caminhos.generate_py),
        operation_name="Geracao de cards (generate_phase_cards.py)",
        step="transform",
        max_attempts=1,
        backoff_seconds=(),
        non_retryable_exit_codes=(),
    )
    resultado = hr.run_python_step(ctx, spec)
    hr.complete_step(ctx, ok=resultado.exit_code in (0, 2))
    if resultado.exit_code == 2:
        _sair(2, "Nenhuma OB qualificada — nenhum card gerado.")
    if resultado.exit_code != 0:
        _sair(
            EXIT_FALHA_CRITICA,
            f"Falha em generate_phase_cards.py. ExitCode={resultado.exit_code}",
        )
    return _ler_fases(caminhos.phase_cards)


def _ler_estado_entrega(ctx: hr.HubRunContext, caminho: Path) -> dict[str, Any]:
    """delivery_state.json por fase: last_sent_hash e phases. Ilegivel reinicia, com aviso."""
    estado: dict[str, Any] = {"last_sent_hash": "", "phases": []}
    if not caminho.exists():
        return estado
    try:
        salvo = _ler_json(caminho)
    except (OSError, ValueError):
        hr.log(
            ctx, "Aviso: falha ao ler delivery_state.json. Reiniciando estado.", "WARN"
        )
        return estado
    ultimo = _campo(salvo, "last_sent_hash")
    if _verdadeiro_ps(ultimo):
        estado["last_sent_hash"] = ultimo
    fases = _campo(salvo, "phases")
    if _verdadeiro_ps(fases):
        estado["phases"] = _como_lista(fases)
    return estado


def _hash_estado_tmp(caminho: Path) -> str:
    """last_hash do obs_state.json.tmp desta execucao; ausente ou ilegivel vale vazio, sem aviso."""
    if not caminho.exists():
        return ""
    try:
        dados = _ler_json(caminho)
    except (OSError, ValueError):
        return ""
    valor = _campo(dados, "last_hash")
    return _texto(valor) if _verdadeiro_ps(valor) else ""


def _aplicar_hash_atual(
    ctx: hr.HubRunContext, caminhos: Caminhos, estado: dict[str, Any]
) -> None:
    """Hash novo zera as entregas por fase (o conteudo das OBs mudou)."""
    hash_atual = _hash_estado_tmp(caminhos.obs_state_tmp)
    if hash_atual and not _mesmo_texto(hash_atual, _texto(estado["last_sent_hash"])):
        hr.log(ctx, f"Novo hash ({hash_atual}) — resetando estado de entrega por fase.")
        estado["last_sent_hash"] = hash_atual
        estado["phases"] = []


def _contar_sucessos(estado: dict[str, Any]) -> int:
    """Fases com success verdadeiro no state (o Where-Object { $_.success } do run.ps1)."""
    return sum(
        1 for fase in estado["phases"] if _verdadeiro_ps(_campo(fase, "success"))
    )


def _entrega_completa(estado: dict[str, Any], total: int) -> bool:
    """allAlreadySent: o numero de fases com sucesso no state e igual ao de cards."""
    return total > 0 and _contar_sucessos(estado) == total


def _pendentes(fases: Sequence[_Fase], estado: dict[str, Any]) -> list[_Fase]:
    """Fases sem entrega confirmada para o lote atual (-not ($state.phases | Where-Object ...))."""
    entregues = {
        str(_campo(entrada, "key")).casefold()
        for entrada in estado["phases"]
        if _campo(entrada, "key") is not None
        and _verdadeiro_ps(_campo(entrada, "success"))
    }
    return [fase for fase in fases if fase.phase_key.casefold() not in entregues]


def _promover_estado_tmp(sessao: _Sessao) -> None:
    """Move-Item do obs_state.json.tmp para obs_state.json; em dry-run so loga."""
    tmp = sessao.caminhos.obs_state_tmp
    if not tmp.exists():
        return
    if sessao.dry_run:
        hr.log(
            sessao.ctx,
            "[DRY-RUN] Commit de estado nao executado: o .tmp seria promovido a obs_state.json.",
            step="commit",
        )
        return
    os.replace(tmp, sessao.caminhos.obs_state)


def _sair_ja_entregue(sessao: _Sessao, total: int) -> NoReturn:
    """Idempotencia de entrega: sai com 2, promove o estado e informa as contagens."""
    hr.log(
        sessao.ctx,
        "Todas as fases ja entregues para este lote. Idempotencia confirmada.",
    )
    _promover_estado_tmp(sessao)
    _sair(
        2,
        MENSAGEM_JA_ENTREGUE,
        {"phases_total": total, "phases_sent": total, "phases_attempted": 0},
    )


def _montar_lote(pendentes: Sequence[_Fase]) -> list[hw.CardPagina]:
    """Lote do WhatsApp: cada fase pendente precisa de image_path (senao sai com 4)."""
    lote: list[hw.CardPagina] = []
    for fase in pendentes:
        if not fase.image_path:
            _sair(
                EXIT_FALHA_CRITICA,
                f"Card '{fase.phase_key}' sem image_path — phase_cards.json corrompido.",
            )
        lote.append(
            hw.CardPagina(
                phase_key=fase.phase_key,
                image_path=fase.image_path,
                caption=fase.caption,
                ob_ids=(),
            )
        )
    return lote


def _destino_whatsapp(sessao: _Sessao) -> tuple[str, str]:
    """Destino (Resolve-WhatsAppTarget) e clientId da sessao do whatsapp-config.json."""
    caminho = sessao.caminhos.wa_config
    try:
        cfg = _ler_json(caminho)
    except (OSError, ValueError) as exc:
        raise _SaidaAntecipada(
            EXIT_FALHA_CRITICA,
            f"Falha ao interpretar '{caminho}' como JSON: {exc}",
        ) from exc
    destino = _resolver_destino(_campo(cfg, "target"), caminho)
    cliente = _campo(_campo(cfg, "auth"), "clientId")
    return destino, (_texto(cliente) if _verdadeiro_ps(cliente) else CLIENTE_PADRAO)


def _simular_envio(
    sessao: _Sessao, pendentes: Sequence[_Fase], chat_id: str, client_id: str
) -> int:
    """Dry-run: loga o que seria enviado, sem enviar, sem gravar estado e sem confirmar."""
    ctx = sessao.ctx
    nomes = ", ".join(fase.phase_display for fase in pendentes)
    hr.log(
        ctx,
        f"[DRY-RUN] Envio WhatsApp nao executado: {len(pendentes)} fase(s) seriam "
        f"enviadas em lote (clientId={client_id}) ao destino {_mascarar_destino(chat_id)}: "
        f"{nomes}.",
        step="dispatch",
    )
    hr.complete_step(ctx, ok=True)
    hr.start_step(ctx, "commit", mensagem="Persistindo delivery_state e state Oracle")
    hr.log(
        ctx,
        "[DRY-RUN] Commit de estado nao executado: delivery_state.json nao gravado.",
        step="commit",
    )
    hr.complete_step(ctx, ok=True)
    return _encerrar(sessao, 0, MENSAGEM_DRY_RUN_FIM)


def _ler_resultados_lote(ctx: hr.HubRunContext, caminhos: Caminhos) -> list[object]:
    """Resultado por fase do lote. Ilegivel vira aviso e lista vazia; os arquivos do lote somem."""
    resultados: list[object] = []
    if caminhos.batch_result.exists():
        try:
            resultados = _como_lista(_ler_json(caminhos.batch_result))
        except (OSError, ValueError) as exc:
            hr.log(ctx, f"Aviso: falha ao ler batch_result.json: {exc}", "WARN")
        _remover(caminhos.batch_result)
    _remover(caminhos.batch_input)
    return resultados


def _enviar_lote(sessao: _Sessao, chat_id: str, client_id: str) -> list[object]:
    """Envio BATCH pelo Send-WhatsApp.ps1; 21 e 22 saem como no run.ps1."""
    ctx = sessao.ctx
    caminhos = sessao.caminhos
    codigo = hw.send_whatsapp(
        ctx,
        script=caminhos.raiz / "lib" / "Send-WhatsApp.ps1",
        work_dir=caminhos.pasta,
        mode=MODO_LOTE,
        client_id=client_id,
        phone=chat_id,
        batch_input_file=caminhos.batch_input,
        batch_result_file=caminhos.batch_result,
        step="dispatch",
    )
    hr.log(ctx, f"Motor WhatsApp Batch ExitCode={codigo}", step="dispatch")
    hr.complete_step(ctx, ok=codigo in (0, EXIT_ADIADO))
    if codigo == EXIT_REAUTENTICACAO:
        _sair(EXIT_REAUTENTICACAO, "WhatsApp requer reautenticacao.")
    if codigo == EXIT_ADIADO:
        _remover(caminhos.batch_result)
        _remover(caminhos.batch_input)
        _sair(EXIT_ADIADO, MENSAGEM_ADIADO)
    return _ler_resultados_lote(ctx, caminhos)


def _sucesso_da_fase(resultados: Sequence[object], chave: str) -> bool:
    """Success do primeiro resultado cuja phase_key casa; sem resultado vale falha."""
    for item in resultados:
        if _mesma_chave(_campo(item, "phase_key"), chave):
            return _verdadeiro_ps(_campo(item, "success"))
    return False


def _registrar_entrega(estado: dict[str, Any], chave: str, sucesso: bool) -> None:
    """Atualiza a entrada da fase no state, ou cria uma nova (success e sent_at)."""
    agora = _agora() if sucesso else None
    entradas = [
        entrada
        for entrada in estado["phases"]
        if isinstance(entrada, dict) and _mesma_chave(entrada.get("key"), chave)
    ]
    if not entradas:
        estado["phases"].append({"key": chave, "success": sucesso, "sent_at": agora})
        return
    for entrada in entradas:
        entrada["success"] = sucesso
        entrada["sent_at"] = agora


def _aplicar_resultados(
    ctx: hr.HubRunContext,
    pendentes: Sequence[_Fase],
    resultados: Sequence[object],
    estado: dict[str, Any],
) -> int:
    """Reconcilia o resultado de cada fase com o state e loga OK/FALHA. Devolve as falhas."""
    falhas = 0
    for fase in pendentes:
        sucesso = _sucesso_da_fase(resultados, fase.phase_key)
        if not sucesso:
            falhas += 1
        _registrar_entrega(estado, fase.phase_key, sucesso)
        situacao = "OK" if sucesso else "FALHA"
        hr.log(ctx, f"Fase '{fase.phase_display}' — {situacao}", step="dispatch")
    return falhas


def _persistir(sessao: _Sessao, estado: dict[str, Any]) -> None:
    """Etapa commit: grava delivery_state.json e promove o .tmp so com todas as fases entregues."""
    ctx = sessao.ctx
    hr.start_step(ctx, "commit", mensagem="Persistindo delivery_state e state Oracle")
    _gravar_json(
        sessao.caminhos.entrega,
        {"last_sent_hash": estado["last_sent_hash"], "phases": estado["phases"]},
    )
    todas = all(_verdadeiro_ps(_campo(fase, "success")) for fase in estado["phases"])
    if todas:
        _promover_estado_tmp(sessao)
    hr.complete_step(ctx, ok=todas)


def _despachar(
    sessao: _Sessao,
    fases: Sequence[_Fase],
    pendentes: Sequence[_Fase],
    estado: dict[str, Any],
) -> int:
    """Etapa dispatch (lote WhatsApp por fase) e commit; fecha a execucao com 0 ou 4."""
    ctx = sessao.ctx
    caminhos = sessao.caminhos
    hr.start_step(
        ctx,
        "dispatch",
        mensagem=f"Enviando {len(pendentes)} fases em lote (sessao unica)",
    )
    lote = _montar_lote(pendentes)
    if not sessao.dry_run:
        hw.write_whatsapp_batch_input(lote, caminhos.pasta, caminhos.batch_input)
    chat_id, client_id = _destino_whatsapp(sessao)
    if sessao.dry_run:
        return _simular_envio(sessao, pendentes, chat_id, client_id)
    resultados = _enviar_lote(sessao, chat_id, client_id)
    falhas = _aplicar_resultados(ctx, pendentes, resultados, estado)
    _persistir(sessao, estado)
    contagens = {
        "phases_total": len(fases),
        "phases_attempted": len(pendentes),
        "phases_sent": _contar_sucessos(estado),
        "phases_failed": falhas,
    }
    if falhas > 0:
        return _encerrar(sessao, EXIT_FALHA_CRITICA, MENSAGEM_FALHA_ENVIO, contagens)
    return _encerrar(sessao, 0, MENSAGEM_SUCESSO, contagens)


def _fluxo(sessao: _Sessao) -> int:
    """Etapas extract, transform, dispatch e commit, executadas dentro do lock OBP-04."""
    ctx = sessao.ctx
    _rotacionar_log(ctx.log_path)
    _remover(sessao.caminhos.resultado)
    _limpar_chrome_zumbis(sessao)
    extracao = _extrair(sessao)
    if extracao.idempotent:
        hr.log(ctx, "Sem alteracoes nas OBs (idempotencia). Encerrando.", step="commit")
        _sair(hr.EXIT_IDEMPOTENTE, MENSAGEM_IDEMPOTENCIA)
    if not extracao.success:
        _sair(
            _codigo_falha_extracao(extracao),
            f"Falha definitiva na extracao Oracle ({MOTOR_EXTRACAO}) "
            f"(PythonExit={extracao.exit_code}).",
        )
    fases = _gerar_cards(sessao)
    estado = _ler_estado_entrega(ctx, sessao.caminhos.entrega)
    _aplicar_hash_atual(ctx, sessao.caminhos, estado)
    if _entrega_completa(estado, len(fases)):
        _sair_ja_entregue(sessao, len(fases))
    pendentes = _pendentes(fases, estado)
    if not pendentes:
        _sair_ja_entregue(sessao, len(fases))
    return _despachar(sessao, fases, pendentes, estado)


def _encerrar(
    sessao: _Sessao,
    codigo: int,
    mensagem: str,
    contagens: dict[str, int] | None = None,
) -> int:
    """Unico ponto de saida: fecha a execucao e a telemetria pelo hub_runner (Exit-AutomationWithCode)."""
    sessao.encerrado = True
    with _arquivo_de_contagens(sessao, contagens) as caminho:
        return hr.finish(sessao.ctx, codigo, mensagem, record_counts_path=caminho)


@contextlib.contextmanager
def _arquivo_de_contagens(
    sessao: _Sessao, contagens: dict[str, int] | None
) -> Iterator[Path | None]:
    """record_counts da saida: as contagens do run.ps1 (-Counts) num arquivo temporario, ou o *_result.json."""
    if contagens is None:
        yield sessao.caminhos.resultado if sessao.resultado_fresco else None
        return
    fd, nome = tempfile.mkstemp(prefix="obp04_counts_", suffix=".json")
    caminho = Path(nome)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps({"record_counts": contagens}, ensure_ascii=False))
        yield caminho
    finally:
        caminho.unlink(missing_ok=True)


def _limpar_estado_tmp(sessao: _Sessao) -> None:
    """Finally do run.ps1: remove o obs_state.json.tmp nao promovido (envio nao confirmado)."""
    tmp = sessao.caminhos.obs_state_tmp
    if not tmp.exists():
        return
    _remover(tmp)
    if not sessao.encerrado:
        hr.log(sessao.ctx, f"Limpeza finally: {tmp} removido.", "DEBUG", step="cleanup")


def _rodar_fluxo(sessao: _Sessao) -> int:
    """Roda o fluxo dentro do lock. A saida fecha a execucao antes de liberar o lock, como no run.ps1."""
    try:
        return _fluxo(sessao)
    except _SaidaAntecipada as saida:
        return _encerrar(sessao, saida.codigo, saida.mensagem, saida.contagens)
    finally:
        _limpar_estado_tmp(sessao)


def _com_lock(sessao: _Sessao) -> int:
    """Executa o fluxo protegido pelo mutex OBP-04 (Enter/Exit-AutomationLock)."""
    ctx = sessao.ctx
    sessao.protegida = True
    hr.start_step(ctx, "lock", mensagem="Adquirindo lock global")
    with hr.AutomationMutex(CHAVE_LOCK, on_warning=_aviso(ctx, "lock")):
        hr.log(
            ctx,
            f"Lock global adquirido com sucesso (Mutex: {hr.nome_mutex(CHAVE_LOCK)}).",
            "DEBUG",
            step="lock",
        )
        hr.complete_step(ctx)
        return _rodar_fluxo(sessao)


def executar(
    ctx: hr.HubRunContext,
    caminhos: Caminhos,
    *,
    dry_run: bool = False,
    aviso_env: str | None = None,
) -> int:
    """Roda o fluxo completo e devolve o exit code (quem chama faz sys.exit)."""
    sessao = _Sessao(ctx=ctx, caminhos=caminhos, dry_run=dry_run)
    hr.execution_start(ctx, f"INICIO — {AUTOMACAO} (OBP-04). ExecId={ctx.exec_id}")
    if aviso_env is not None:
        hr.log(
            ctx, f"Aviso: falha ao carregar .env: {aviso_env}", "WARN", step="preflight"
        )
    if dry_run:
        hr.log(
            ctx,
            "[DRY-RUN] Validacao manual: nenhum WhatsApp sera enviado e o estado "
            "nao sera confirmado.",
            "WARN",
        )
    try:
        _preflight(sessao)
        return _com_lock(sessao)
    except _SaidaAntecipada as saida:
        return _encerrar(sessao, saida.codigo, saida.mensagem, saida.contagens)
    # Residual: as falhas fora do fluxo (KeyError, OSError, LockTimeoutError, ValueError...)
    # recebem o fim do catch do run.ps1: dentro do lock, exit 4 "Falha critica na orquestracao";
    # no pre-flight, o erro nao tratado do PowerShell, exit 1. A excecao ja passou pelo finally
    # do lock, entao o .tmp e o mutex estao liberados antes do execution.end.
    except Exception as exc:  # pylint: disable=broad-exception-caught
        if sessao.protegida:
            return _encerrar(
                sessao, EXIT_FALHA_CRITICA, f"Falha critica na orquestracao: {exc}"
            )
        return _encerrar(sessao, EXIT_ERRO_FATAL, f"ERRO FATAL: {exc}")


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada: ``run_obs_paradas.py [ExecId] [--dry-run]``. Devolve o exit code."""
    ensure_utf8_streams()
    argumentos = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in argumentos
    posicionais = [arg for arg in argumentos if arg != "--dry-run"]
    aviso_env = _carregar_env(RAIZ)
    ctx = hr.create_run_context(
        hr.AutomationSpec(
            automacao=AUTOMACAO,
            slug=SLUG_LOG,
            trace_slug=SLUG_TRACE,
            lock_key=CHAVE_LOCK,
            log_dir=OBP_DIR / "Logs",
            non_failure_codes=NAO_FALHA,
        ),
        exec_id=posicionais[0] if posicionais else "",
        telemetry=_telemetria_padrao(RAIZ),
        project_root=RAIZ,
    )
    return executar(
        ctx, Caminhos.da_pasta(OBP_DIR), dry_run=dry_run, aviso_env=aviso_env
    )


if __name__ == "__main__":
    sys.exit(main())
