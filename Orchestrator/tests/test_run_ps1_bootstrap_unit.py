"""Contratos de bootstrap dos 6 `run.ps1` de automação.

Estes testes leem os `.ps1` como texto. Não substituem execução — a metade
PowerShell não tem cobertura executável em nenhuma plataforma — mas travam dois
contratos que a validação em produção de 08/09/2026 encontrou quebrados
(`CHANGELOG.md` [1.3.82]): o interpretador resolvido por `Resolve-HubPythonExe`
e o fechamento de telemetria em todo ponto de saída precoce.
"""

import re
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


# --------------------------------------------------------------------------
# Padronização dos run.ps1 (CHANGELOG [1.3.110])
# --------------------------------------------------------------------------


@pytest.mark.parametrize("automacao", AUTOMACOES)
def test_run_ps1_adquire_o_lock_sem_vazar_true_no_log(automacao: str) -> None:
    """`Enter-AutomationLock` devolve `$true`; sem descarte, o `True` sai no log
    de cada execução como linha própria da etapa `lock`."""
    fonte = _run_ps1(automacao)

    assert re.search(
        r"Enter-AutomationLock\s+-ExecId\s+\$ExecId\s+-LogPath\s+\$LogFile(?:\s+[^\r\n|]*)?\s*\|\s*Out-Null",
        fonte,
    ), f"{automacao}/run.ps1 deve descartar a saída de Enter-AutomationLock"
    assert "if (-not (Enter-AutomationLock" not in fonte, (
        f"{automacao}/run.ps1 usa o retorno de Enter-AutomationLock como booleano: "
        "a função lança exceção em concorrência e nunca devolve $false"
    )


@pytest.mark.parametrize(
    "automacao",
    [a for a in AUTOMACOES if a != "Montagem de Terceirizados"],
)
def test_run_ps1_declara_os_codigos_de_nao_falha(automacao: str) -> None:
    """Cada `Exit-WithCode` declara a lista de códigos que não são falha em
    `$NonFailureCodes`, em vez de repetir literais (que já divergiram)."""
    fonte = _run_ps1(automacao)

    assert (
        "$NonFailureCodes = @(" in fonte
    ), f"{automacao}/run.ps1 deve declarar $NonFailureCodes"
    assert re.search(
        r"NonFailureCodes\s*=?\s*\$NonFailureCodes", fonte
    ), f"{automacao}/run.ps1 deve repassar $NonFailureCodes a Exit-AutomationWithCode"
    assert (
        "-NonFailureCodes @(" not in fonte
    ), f"{automacao}/run.ps1 voltou a usar a lista literal em vez de $NonFailureCodes"


@pytest.mark.parametrize("automacao", AUTOMACOES)
def test_run_ps1_nao_usa_guarda_processo_finalizado(automacao: str) -> None:
    """`exit` não é capturável por `catch` (Windows PowerShell 5.1 e 7), então a
    guarda por mensagem "Processo finalizado" é código morto."""
    assert '-match "Processo finalizado"' not in _run_ps1(automacao)


@pytest.mark.parametrize("automacao", AUTOMACOES)
def test_run_ps1_valida_o_python_no_preflight(automacao: str) -> None:
    """O interpretador entra em `-CheckPaths` (ou `$pathsToCheck`): sem isso, o
    RB-01 tratava Python ausente como `exit 2` (sucesso)."""
    fonte = _run_ps1(automacao)

    assert re.search(
        r"(-CheckPaths\s+@\(\$pythonExe|\$pathsToCheck\s*=\s*@\(\$pythonExe)", fonte
    ), f"{automacao}/run.ps1 deve validar $pythonExe no pré-flight"


def test_obp04_serializa_o_lote_sempre_como_array() -> None:
    """Com uma única fase pendente, `$lote | ConvertTo-Json` (pipeline) gera um
    objeto, não um array; o motor Node descarta como "Lote vazio", a fase vira
    FALHA e a execução sai com 4 (ocorreu em 09/11/2026 com só "Controle De
    Qualidade" pendente)."""
    fonte = _run_ps1("OBs Paradas Fase")

    assert "ConvertTo-Json -InputObject @($batchInput)" in fonte
    assert "$batchInput | ConvertTo-Json" not in fonte


def test_lib_whatsapp_batch_serializa_o_lote_sempre_como_array() -> None:
    """Garante no helper compartilhado de ORB-07/OFST-06 a mesma protecao
    contra o unwrap de array unitario do ConvertTo-Json."""
    modulo = (REPO_ROOT / "lib" / "Lib-WhatsAppBatch.psm1").read_text(
        encoding="utf-8-sig"
    )

    assert "ConvertTo-Json -InputObject @($batchInput)" in modulo
    assert "$batchInput | ConvertTo-Json" not in modulo


@pytest.mark.parametrize(
    ("automacao", "lock_key"),
    [
        ("OBs Restricao Branco", "ORB-07"),
        ("OBs Fluxo Sem Tingimento", "OFST-06"),
    ],
)
def test_orb_e_ofst_isolam_lock_batch_e_rotacao_sem_codigos_mortos(
    automacao: str, lock_key: str
) -> None:
    """Contrato Lote 2: lock nomeado por automacao, rotacao 15d ativa, sem
    cleanup pre-Oracle de chrome.exe e sem ramos mortos 40/23/22."""
    fonte = _run_ps1(automacao)

    assert f'-LockKey "{lock_key}"' in fonte
    assert "Exit-AutomationLock -ExecId $ExecId -LogPath $LogFile -LockKey" in fonte
    assert "Invoke-LogRotation -LogPath $LogFile -KeepDays 15" in fonte
    assert "chrome.exe" not in fonte
    assert "Lib-WhatsAppBatch.psm1" in fonte
    assert "-Mode BATCH" in fonte
    assert "$waExit -eq 40" not in fonte
    assert "$waExit -eq 23" not in fonte
    assert "22" not in re.findall(r"\$NonFailureCodes\s*=\s*@\(([^)]+)\)", fonte)[0]

    pos_lock = fonte.index("Enter-AutomationLock")
    pos_remove = fonte.index("Remove-Item $ResultFile")
    assert pos_remove > pos_lock


@pytest.mark.parametrize(
    "automacao",
    [
        "OBs Restricao Branco",
        "OBs Fluxo Sem Tingimento",
    ],
)
def test_orb_e_ofst_protegem_result_file_obsoleto_config_desabilitada_e_telemetria_parcial(
    automacao: str,
) -> None:
    """Contrato: $HasFreshResult protege record_counts antes da extracao,
    Test-WhatsAppConfigEnabled encerra com Exit-WithCode 2 antes do envio e
    PartialSent ajusta contadores com DeliveredObCount."""
    fonte = _run_ps1(automacao)

    assert "$script:HasFreshResult = $false" in fonte
    assert "$script:HasFreshResult = $true" in fonte
    assert (
        'if ($script:HasFreshResult) { $ResultFile } else { "" }' in fonte
        or "if ($script:HasFreshResult) { $ResultFile } else { '' }" in fonte
    )

    assert "Test-WhatsAppConfigEnabled -Config $waConfig" in fonte
    pos_cfg_check = fonte.index("Test-WhatsAppConfigEnabled -Config $waConfig")
    pos_dispatch_send = fonte.index("$SendWhatsAppScript =")
    assert pos_cfg_check < pos_dispatch_send
    assert "Complete-HubStep -Ok $true" in fonte[pos_cfg_check:pos_dispatch_send]
    assert "Exit-WithCode 2" in fonte[pos_cfg_check:pos_dispatch_send]

    pos_partial = fonte.index("PartialSent")
    assert "DeliveredObCount" in fonte[pos_partial:]
    assert "Update-WhatsAppResultRecordCounts" in fonte[pos_partial:]
