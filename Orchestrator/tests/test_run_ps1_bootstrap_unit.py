"""Contratos de bootstrap das 6 automacoes com `run.ps1`.

Desde a 1.3.117 todo `run.ps1` e um shim: resolve o interpretador, chama o
runner Python da pasta e repassa o exit code. Lock, pre-flight, telemetria e
envio vivem no runner (sobre `lib/python/hub_runner.py`). Estes testes leem os
arquivos como texto e travam os contratos que a validacao em producao de
08/09/2026 encontrou quebrados (`CHANGELOG.md` [1.3.82]) e a padronizacao da
[1.3.110], agora no lugar onde cada contrato mora. O comportamento e coberto
pelos testes `test_run_<automacao>_unit.py`.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# (pasta, runner, chave do lock, codigos que nao sao falha)
AUTOMACOES = [
    ("Receitas Bloqueadas", "run_receitas_bloqueadas.py", "RB-01", "NAO_FALHA"),
    ("Montagem de Terceirizados", "run_montagem.py", "MT-02", "(0,)"),
    ("Receitas Emitidas", "run_receitas.py", "RE-03", "(0,)"),
    ("OBs Paradas Fase", "run_obs_paradas.py", "OBP-04", "NAO_FALHA"),
    ("OBs Fluxo Sem Tingimento", "run_ofst.py", "OFST-06", "CODIGOS_SEM_FALHA"),
    ("OBs Restricao Branco", "run_orb.py", "ORB-07", "CODIGOS_SEM_FALHA"),
]
PASTAS = [a[0] for a in AUTOMACOES]


def _run_ps1(nome: str) -> str:
    caminho = REPO_ROOT / nome / "run.ps1"
    assert caminho.exists(), f"run.ps1 ausente em {nome}"
    return caminho.read_text(encoding="utf-8-sig")


def _runner(nome: str, arquivo: str) -> str:
    caminho = REPO_ROOT / nome / arquivo
    assert caminho.exists(), f"{arquivo} ausente em {nome}"
    return caminho.read_text(encoding="utf-8")


@pytest.mark.parametrize("automacao", PASTAS)
def test_run_ps1_resolve_o_venv_pela_funcao_compartilhada(automacao: str) -> None:
    """O interpretador nao pode ser derivado so de $projectRoot.

    O `.venv` vive na raiz do repositorio principal e nao e versionado, entao um
    worktree de agente nao tem copia propria. Hardcodear o venv em $projectRoot
    faz a execucao falhar em toda automacao rodada de um worktree, como em
    08/09/2026.
    """
    fonte = _run_ps1(automacao)

    assert "Resolve-HubPythonExe" in fonte
    assert '$projectRoot ".venv' not in fonte


@pytest.mark.parametrize(("automacao", "runner", "_lock", "_nf"), AUTOMACOES)
def test_shim_delega_ao_runner_e_repassa_o_exit_code(
    automacao: str, runner: str, _lock: str, _nf: str
) -> None:
    """O shim chama o runner e sai com o mesmo exit code.

    Lock, pre-flight, telemetria e envio ficam no runner: o shim nao pode voltar
    a te-los, senao o contrato passa a existir em dois lugares.
    """
    fonte = _run_ps1(automacao)

    assert f'"{runner}"' in fonte
    assert "exit $LASTEXITCODE" in fonte
    assert "--dry-run" in fonte
    assert "Enter-AutomationLock" not in fonte
    assert "Register-ExecutionTelemetry" not in fonte
    assert '-match "Processo finalizado"' not in fonte


@pytest.mark.parametrize("automacao", PASTAS)
def test_shim_valida_o_python_antes_de_delegar(automacao: str) -> None:
    """Interpretador ausente sai com 9 (codigo de pre-flight), nunca com sucesso.

    Antes, o RB-01 tratava Python ausente como `exit 2` (sucesso).
    """
    fonte = _run_ps1(automacao)

    assert re.search(r"Test-Path\s+-LiteralPath\s+\$pythonExe", fonte)
    assert "exit 9" in fonte


@pytest.mark.parametrize(("automacao", "runner", "_lock", "_nf"), AUTOMACOES)
def test_runner_fecha_a_telemetria_em_todo_ponto_de_saida(
    automacao: str, runner: str, _lock: str, _nf: str
) -> None:
    """Toda saida passa por _encerrar, que devolve hr.finish.

    hr.finish fecha o execution.end e a telemetria (o equivalente de
    Exit-WithCode). Sem isso a execucao fica RUNNING no Orchestrator e passa a
    rejeitar a telemetria dos ciclos seguintes (caso do MT-02 em 08/09/2026).
    """
    fonte = _runner(automacao, runner)

    chamadas = fonte.count("hr.finish(")
    assert chamadas == fonte.count("return hr.finish("), "hr.finish sempre com return"
    assert 1 <= chamadas <= 2
    assert "sys.exit(main())" in fonte


@pytest.mark.parametrize(("automacao", "runner", "lock", "_nf"), AUTOMACOES)
def test_runner_adquire_o_lock_global_pela_chave_da_automacao(
    automacao: str, runner: str, lock: str, _nf: str
) -> None:
    """O lock e o mutex nomeado da automacao, o mesmo de Enter-AutomationLock."""
    fonte = _runner(automacao, runner)

    assert f'CHAVE_LOCK: Final[str] = "{lock}"' in fonte
    assert "hr.AutomationMutex(CHAVE_LOCK" in fonte


@pytest.mark.parametrize(("automacao", "runner", "_lock", "nao_falha"), AUTOMACOES)
def test_runner_declara_os_codigos_de_nao_falha_num_lugar_so(
    automacao: str, runner: str, _lock: str, nao_falha: str
) -> None:
    """Os codigos que nao sao falha vem de uma constante, como o $NonFailureCodes."""
    fonte = _runner(automacao, runner)

    assert f"non_failure_codes={nao_falha}" in fonte


@pytest.mark.parametrize(("automacao", "runner", "_lock", "_nf"), AUTOMACOES)
def test_runner_valida_o_python_no_preflight_e_rotaciona_o_log(
    automacao: str, runner: str, _lock: str, _nf: str
) -> None:
    """O pre-flight confere o interpretador e o log tem retencao de 15 dias."""
    fonte = _runner(automacao, runner)

    assert "Path(sys.executable)" in fonte
    assert "RETENCAO_LOG_DIAS: Final[int] = 15" in fonte
    assert "_rotacionar_log(" in fonte


@pytest.mark.parametrize(
    ("automacao", "runner"),
    [
        ("OBs Paradas Fase", "run_obs_paradas.py"),
        ("OBs Fluxo Sem Tingimento", "run_ofst.py"),
        ("OBs Restricao Branco", "run_orb.py"),
    ],
)
def test_runners_whatsapp_gravam_o_lote_pelo_helper_compartilhado(
    automacao: str, runner: str
) -> None:
    """O lote passa por hub_whatsapp, que grava sempre uma lista JSON."""
    fonte = _runner(automacao, runner)

    assert "hub_whatsapp" in fonte
    if runner != "run_obs_paradas.py":
        # Lote 2: ORB/OFST nao limpam chrome.exe antes do Oracle (o OBP-04 limpa, por desenho).
        assert "chrome.exe" not in fonte


@pytest.mark.parametrize(
    ("automacao", "runner"),
    [
        ("OBs Restricao Branco", "run_orb.py"),
        ("OBs Fluxo Sem Tingimento", "run_ofst.py"),
    ],
)
def test_orb_e_ofst_so_reportam_record_counts_de_result_fresco(
    automacao: str, runner: str
) -> None:
    """Como o $HasFreshResult: record_counts so sai de um result desta execucao."""
    fonte = _runner(automacao, runner)

    assert "resultado_fresco: bool = False" in fonte
    assert "sessao.resultado_fresco = True" in fonte
    assert "if sessao.resultado_fresco else None" in fonte
