"""Contrato de exit codes entre os `run.ps1` das automações e o EXIT_CODE_MAP.

Motivação: o mapa e os scripts eram mantidos em arquivos separados, sem nada que
os amarrasse. A divergência que existia até 31/07/2026 classificava o exit 3
("falha definitiva na extracao Oracle apos 3 tentativas") como SUCCESS — falha
total registrada como entrega, sem alerta, sem auto-retry e contando como
disponibilidade no SLA. O caminho inverso também ocorria: o exit 22, emitido
como comportamento normal, caía no default ERROR e gerava falso incidente.

Este teste falha quando um `run.ps1` passa a emitir um código ausente do mapa.
"""

import re
from pathlib import Path

import pytest
from app.constants import (
    EXECUTION_STATUS_ERROR,
    EXECUTION_STATUS_PARTIAL,
    EXECUTION_STATUS_SUCCESS,
    EXIT_CODE_MAP,
    FAILURE_REASON_DATA_EXTRACTION_FAILED,
    RECOVERY_ACTION_NONE,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Bloco de comentário do PowerShell: <# ... #>
_BLOCK_COMMENT = re.compile(r"<#.*?#>", re.DOTALL)
# Linha cujo primeiro caractere não-espaço é '#'
_LINE_COMMENT = re.compile(r"^\s*#.*$", re.MULTILINE)

# Formas pelas quais um run.ps1 encerra com código literal:
#   Exit-WithCode 3 "..."        (helper padrão das automações)
#   ...; exit 9                  (saída direta, início de linha ou após ';')
#   $channelFailureExitCode = 25 (variável consumida por Exit-WithCode depois)
_EMIT_PATTERNS = (
    re.compile(r"Exit-WithCode\s+(\d+)"),
    re.compile(r"(?:^|;)\s*exit\s+(\d+)", re.MULTILINE),
    re.compile(r"\$\w*[Ee]xit[_]?[Cc]ode\w*\s*=\s*(\d+)"),
)


def _strip_comments(source: str) -> str:
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", source))


def _emitted_exit_codes(script: Path) -> set[int]:
    source = _strip_comments(script.read_text(encoding="utf-8-sig"))
    codes: set[int] = set()
    for pattern in _EMIT_PATTERNS:
        codes.update(int(match) for match in pattern.findall(source))
    return codes


def _automation_run_scripts() -> list[Path]:
    """`run.ps1` das automações registradas (as que têm manifesto)."""
    return sorted(
        manifest.parent / "run.ps1"
        for manifest in PROJECT_ROOT.glob("*/automation.manifest.json")
        if (manifest.parent / "run.ps1").is_file()
    )


@pytest.mark.unitario
def test_ha_run_scripts_para_varrer() -> None:
    """Guarda contra o teste passar por não ter encontrado arquivo nenhum."""
    scripts = _automation_run_scripts()
    assert scripts, (
        "Nenhum run.ps1 de automação registrada encontrado em "
        f"{PROJECT_ROOT} — o contrato de exit codes não estaria sendo verificado."
    )


@pytest.mark.unitario
@pytest.mark.parametrize(
    "script", _automation_run_scripts(), ids=lambda p: p.parent.name
)
def test_todo_exit_code_emitido_esta_mapeado(script: Path) -> None:
    """Todo código emitido por um run.ps1 precisa constar no EXIT_CODE_MAP.

    Código ausente cai no default ERROR/EXIT_CODE_<n> de
    `classify_process_result`, transformando desfecho normal em falso incidente
    (ou mascarando a semântica real da falha).
    """
    emitidos = _emitted_exit_codes(script)
    nao_mapeados = sorted(emitidos - set(EXIT_CODE_MAP))
    assert not nao_mapeados, (
        f"{script.relative_to(PROJECT_ROOT)} emite os exit codes {nao_mapeados}, "
        "ausentes de EXIT_CODE_MAP em Orchestrator/app/constants.py. "
        "Adicione-os ao mapa com status, failure_reason e recovery_action "
        "explícitos — o default silencioso é ERROR."
    )


@pytest.mark.unitario
def test_falha_definitiva_de_extracao_nao_e_sucesso() -> None:
    """Regressão: o exit 3 já foi classificado como SUCCESS.

    Três automações usam `Exit-WithCode 3` para falha definitiva de extração
    (Oracle após 3 tentativas / script Python). Classificar isso como SUCCESS
    suprime alerta, suprime auto-retry e conta a execução como entregue no SLA.
    """
    status, failure_reason, _recovery = EXIT_CODE_MAP[3]
    assert status == EXECUTION_STATUS_ERROR
    assert failure_reason == FAILURE_REASON_DATA_EXTRACTION_FAILED


@pytest.mark.unitario
def test_whatsapp_adiado_nao_e_falha() -> None:
    """Regressão: o exit 22 caía no default ERROR.

    O 22 é emitido para lock/cooldown da sessão hub-global — comportamento
    normal, com state não commitado e reavaliação no ciclo seguinte. Tratá-lo
    como falha gera alerta e polui os hotspots a cada disputa de sessão.
    """
    status, failure_reason, recovery = EXIT_CODE_MAP[22]
    assert status == EXECUTION_STATUS_SUCCESS
    assert failure_reason is None
    assert recovery == RECOVERY_ACTION_NONE


@pytest.mark.unitario
def test_mapa_e_internamente_coerente() -> None:
    """Status de sucesso não carrega motivo de falha, e vice-versa."""
    for code, (status, failure_reason, recovery) in EXIT_CODE_MAP.items():
        assert status in {
            EXECUTION_STATUS_SUCCESS,
            EXECUTION_STATUS_PARTIAL,
            EXECUTION_STATUS_ERROR,
        }, f"exit {code}: status inesperado {status}"
        assert isinstance(recovery, str) and recovery, f"exit {code}: recovery vazio"
        if status == EXECUTION_STATUS_SUCCESS:
            assert failure_reason is None, (
                f"exit {code}: SUCCESS não pode carregar failure_reason "
                f"({failure_reason})"
            )
        else:
            assert failure_reason, (
                f"exit {code}: {status} exige failure_reason explícito para o "
                "operador saber o que aconteceu"
            )
