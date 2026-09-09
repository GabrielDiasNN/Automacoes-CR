"""Contratos de bootstrap dos 6 `run.ps1` de automação.

Estes testes leem os `.ps1` como texto. Não substituem execução — a metade
PowerShell não tem cobertura executável em nenhuma plataforma — mas travam dois
contratos que a validação em produção de 08/09/2026 encontrou quebrados
(`docs/validacao-producao-revisao-08092026.md`, achados 3 e 4).
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

AUTOMACOES = [
    "Receitas Bloqueadas",
    "Montagem de Terceirizados",
    "Receitas Emitidas",
    "OBs Paradas Fase",
    "OBs Fluxo Sem Tingimento",
    "OBs Restricao Branco",
]


def _run_ps1(nome: str) -> str:
    caminho = REPO_ROOT / nome / "run.ps1"
    assert caminho.exists(), f"run.ps1 ausente em {nome}"
    return caminho.read_text(encoding="utf-8-sig")


@pytest.mark.parametrize("automacao", AUTOMACOES)
def test_run_ps1_resolve_o_venv_pela_funcao_compartilhada(automacao: str) -> None:
    """O interpretador não pode ser derivado só de $projectRoot.

    O `.venv` vive na raiz do repositório principal e não é versionado, então um
    worktree de agente não tem cópia própria. Hardcodear
    `Join-Path $projectRoot ".venv\\Scripts\\python.exe"` faz o pré-flight falhar
    com `Path inacessivel: python.exe` em toda automação rodada de um worktree —
    foi exatamente o que aconteceu em 08/09/2026.
    """
    fonte = _run_ps1(automacao)

    assert "Resolve-HubPythonExe" in fonte, (
        f"{automacao}/run.ps1 deve resolver o python por Resolve-HubPythonExe "
        "(lib/Lib-Process.psm1), que cai no venv do repositório principal "
        "quando a árvore corrente não tem um"
    )
    assert '$projectRoot ".venv' not in fonte, (
        f"{automacao}/run.ps1 voltou a hardcodear o venv em $projectRoot; "
        "isso quebra a execução a partir de um worktree"
    )


def test_mt02_fecha_a_telemetria_no_abort_do_preflight() -> None:
    """O abort de pré-flight do MT-02 acontece antes do try/finally.

    MT-02 é o único dos 6 que sai com `exit` cru em vez de `Exit-WithCode` (que
    chama `Exit-AutomationWithCode`, o qual fecha a telemetria). Sem o
    `Close-ExecutionTelemetry` explícito nesse ramo, a execução fica `RUNNING`
    para sempre no Orchestrator e passa a rejeitar a telemetria de todos os
    ciclos seguintes com `conflict: já existe uma execução ativa`.
    """
    fonte = _run_ps1("Montagem de Terceirizados")

    marcador = 'Write-Fim 9 "FALHA NO PRE-FLIGHT'
    assert marcador in fonte, "o ramo de abort do pré-flight mudou de forma"

    inicio = fonte.index(marcador)
    fim = fonte.index("exit 9", inicio)
    ramo = fonte[inicio:fim]

    assert "Close-ExecutionTelemetry" in ramo, (
        "o abort do pré-flight do MT-02 precisa fechar a telemetria antes do "
        "exit: esse caminho não passa pelo finally que a fecha no fluxo normal"
    )


@pytest.mark.parametrize("automacao", AUTOMACOES)
def test_run_ps1_nao_sai_sem_fechar_telemetria(automacao: str) -> None:
    """Todo ponto de saída fecha a telemetria, por helper ou explicitamente.

    Complementa o teste acima nas outras 5: elas usam `Exit-WithCode`, que
    encaminha para `Exit-AutomationWithCode` e fecha a telemetria antes do
    `exit`. Se alguma passar a usar `exit` cru sem fechar, este teste acusa.
    """
    fonte = _run_ps1(automacao)

    if "Register-ExecutionTelemetry" not in fonte:
        pytest.skip(f"{automacao} não registra telemetria")

    fecha_por_helper = "Exit-WithCode" in fonte
    fecha_explicito = "Close-ExecutionTelemetry" in fonte

    assert fecha_por_helper or fecha_explicito, (
        f"{automacao}/run.ps1 abre telemetria mas nunca a fecha: a execução "
        "ficaria RUNNING indefinidamente no Orchestrator"
    )
