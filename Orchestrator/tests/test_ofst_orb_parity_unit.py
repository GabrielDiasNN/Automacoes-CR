"""Trava a paridade CONTRATUAL entre OFST-06 e ORB-07 nos pontos declarados
equivalentes -- sem exigir igualdade total dos dois scripts.

O repositório trata `OBs Fluxo Sem Tingimento` (OFST-06) e `OBs Restricao
Branco` (ORB-07) como "mesma arquitetura, mesmo contrato" (mesmo pipeline
extract -> validate -> notify, mesmo padrão de idempotência por poda de
state). Nesta revisão essa suposição falhou duas vezes seguidas, e as duas
vezes só foi pega por leitura manual: primeiro o OFST não podava o state
quando uma OB saía da query; depois, ao corrigir isso "alinhando com o
ORB-07", a correção copiou o trecho visível do `run.ps1`/`extract_ofst.py`
mas não trouxe a guarda de `resumo.falhas` que o `extract_orb.py` sempre
teve -- isso chegou a produção como regressão real (commit `bd2e7b6`: o
`ofst_state.json` zerava e todas as OBs já avisadas eram reanunciadas ao
grupo assim que o dado normalizasse).

Este arquivo NÃO tenta provar que os dois scripts são idênticos -- não são,
por design: só o ORB tem `todas_falhas_por_montagem` (regra de negócio sobre
classificação de cor na view), `parse_notified_state`/reservas de estoque com
janela (`JANELA_RESERVA_HORAS`) e `ClassificacaoNaoResolvidaError`. Um teste
que exigisse paridade total seria desativado na primeira semana por gerar
falso positivo a cada evolução legítima de UM dos dois. Em vez disso, cada
invariante abaixo foi escolhida por ser genuinamente CONTRATUAL -- documentada
em CONTEXT.md/CHANGELOG.md como comportamento que as duas automações
compartilham por decisão, não por coincidência de implementação:

1. `test_ambos_abortam_sem_tocar_state_quando_falhas_sem_ob` -- comportamental,
   parametrizada nos dois módulos: com `resumo.falhas` populado e `obs`
   vazio (linhas VIERAM da query mas nenhuma sobreviveu à validação), ambos
   têm que abortar com `sys.exit(1)` SEM escrever `<state>.tmp` e SEM tocar
   no state vivo. É exatamente o par de bugs desta revisão -- a poda
   incondicional (achado 1) e a falta desta guarda (achado 2, `bd2e7b6`).
   Fora do escopo: o branch extra do ORB
   (`todas_falhas_por_montagem` -> exit 2 preservando o state) não tem
   equivalente no OFST por não existir a noção de "montagem em curso" nesse
   fluxo -- não é comparado aqui de propósito.

2. `test_ambos_expoem_o_mesmo_conjunto_de_funcoes_de_escrita_de_state` --
   estrutural (AST, sem executar o módulo): os dois `extract_*.py` definem
   localmente `_read_notified`, `_write_state_tmp`, `_write_counts` e
   `_write_result` -- a superfície de E/S de state que o `run.ps1` de cada
   automação depende (`Move-Item $StateTmp $StateFile`) e que os testes de
   unidade de cada automação já usam via `monkeypatch.setattr`. Não comparamos
   os `validators.py` inteiros (esses SÃO diferentes por design -- ORB tem
   `reservas_*`/`parse_notified_state`/`JANELA_RESERVA_HORAS` que o OFST não
   tem e não deve ter).

3. `test_ambos_tem_o_bloco_de_reconciliacao_de_state_no_run_ps1` -- estrutural
   (texto, sem `pwsh`): os dois `run.ps1` têm que reconciliar
   `$StateTmp` -> `$StateFile` no mesmo ramo (`$pyResult.Idempotent`), porque é
   esse bloco que a regressão do achado 2 atingia -- um state.tmp escrito por
   engano no ramo idempotente do Python já basta para reintroduzir o bug,
   independente do que o `run.ps1` faça depois disso.

Deliberadamente FORA do escopo desta paridade (não é contrato, é diferença de
design ou muda com frequência normal demais para travar): SQL das queries,
formatação de mensagem WhatsApp, presença de reservas de estoque, contagem de
campos de `ResumoExecucao`, e qualquer coisa em `validators.py` que não seja a
função `merge_notified_state`.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).parent.parent.parent

OFST_DIR = ROOT / "OBs Fluxo Sem Tingimento"
ORB_DIR = ROOT / "OBs Restricao Branco"

_AUTOMACOES = (
    pytest.param(OFST_DIR, "extract_ofst.py", "extract_ofst_parity", id="OFST-06"),
    pytest.param(ORB_DIR, "extract_orb.py", "extract_orb_parity", id="ORB-07"),
)

# Módulos irmãos que extract_ofst.py e extract_orb.py importam pelo MESMO
# nome ("from validators import ...") apontando para arquivos DIFERENTES --
# têm que ser removidos de sys.modules entre um load e outro, senão o segundo
# import silenciosamente reaproveita o módulo genérico da automação errada.
_GENERIC_MODULE_NAMES = ("validators", "errors", "models", "queries", "format_message")

# Funções de escrita de state que o run.ps1 de cada automação depende
# (reconciliação .tmp -> arquivo real) e que os testes de unidade de cada
# automação já monkeypatcham individualmente.
_FUNCOES_DE_STATE_ESPERADAS = frozenset(
    {"_read_notified", "_write_state_tmp", "_write_counts", "_write_result"}
)


def _load_extract_module(name: str, automation_dir: Path, filename: str) -> ModuleType:
    """Carrega um extract_*.py isolando os módulos genéricos irmãos do outro
    par OFST/ORB eventualmente já carregado neste processo de teste.
    """
    for generic_name in _GENERIC_MODULE_NAMES:
        sys.modules.pop(generic_name, None)

    dir_str = str(automation_dir)
    if dir_str in sys.path:
        sys.path.remove(dir_str)
    sys.path.insert(0, dir_str)

    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(name, automation_dir / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module", autouse=True)
def _isolar_modulos_genericos_apos_o_modulo() -> Any:
    """Evita vazar `validators`/`errors`/`models`/`queries` (e os aliases
    `extract_ofst_parity`/`extract_orb_parity`) para outros arquivos de teste
    que repitam esse layout (test_ofst.py, test_orb.py).

    Escopo de MODULO (nao de funcao): `_load_extract_module` ja isola OFST de
    ORB *dentro* deste arquivo (pop dos genericos + reinsercao em sys.path a
    cada chamada). Um cleanup por FUNCAO removeria `OFST_DIR`/`ORB_DIR` de
    `sys.path` entre um teste parametrizado e o outro, o que quebra
    `test_ofst.py`/`test_orb.py` quando rodam na mesma sessao: esses arquivos
    inserem seu proprio diretorio em `sys.path` uma unica vez, na COLETA
    (import do modulo), e so removem no teardown do PROPRIO modulo — se este
    arquivo apagar essa entrada antes de `test_ofst.py`/`test_orb.py`
    executarem seus testes, o `from validators import ...` de dentro de
    `extract_ofst.py`/`extract_orb.py` (import de modulo irmao) quebra com
    `ModuleNotFoundError`. Restaurar `sys.path` para o snapshot de ANTES deste
    modulo (em vez de remover entradas especificas) preserva o que quer que
    outro arquivo ja tenha inserido.
    """
    sys_path_original = list(sys.path)
    yield
    sys.path[:] = sys_path_original
    for generic_name in _GENERIC_MODULE_NAMES:
        sys.modules.pop(generic_name, None)
    sys.modules.pop("extract_ofst_parity", None)
    sys.modules.pop("extract_orb_parity", None)


@pytest.mark.parametrize("automation_dir, filename, module_name", _AUTOMACOES)
def test_ambos_abortam_sem_tocar_state_quando_falhas_sem_ob(
    automation_dir: Path,
    filename: str,
    module_name: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """`resumo.falhas` populado + `obs` vazio == dado fora do contrato, nunca
    "nada a notificar". As duas automações têm que abortar com exit(1) sem
    escrever `<state>.tmp` e sem tocar no state vivo -- é o comportamento cuja
    ausência causou a regressão de produção corrigida em `bd2e7b6`.
    """
    extract = _load_extract_module(module_name, automation_dir, filename)

    state_file = tmp_path / f"{module_name}_state.json"
    state_original = '{"notified": {"1001": "2026-07-15T10:00:00"}}'
    state_file.write_text(state_original, encoding="utf-8")

    monkeypatch.setattr(extract, "STATE_FILE", str(state_file))
    monkeypatch.setattr(
        extract, "RESULT_FILE", str(tmp_path / f"{module_name}_result.json")
    )
    monkeypatch.setattr(
        extract, "resolve_oracle_credentials", lambda log, exec_id: object()
    )
    monkeypatch.setattr(extract, "init_thick_mode", lambda creds, log, exec_id: None)
    monkeypatch.setattr(extract.sys, "argv", [filename, "TESTE-PARIDADE"])

    def fake_fetch_obs(_creds: Any, _exec_id: str, resumo: Any) -> list[Any]:
        # Sinal de linha REJEITADA na validação (nunca de query vazia de
        # verdade) -- o mesmo gatilho usado pelos testes por-automação.
        resumo.falhas.append("linha rejeitada pela validacao (teste de paridade)")
        return []

    monkeypatch.setattr(extract, "_fetch_obs", fake_fetch_obs)

    with pytest.raises(SystemExit) as excinfo:
        extract.extract()

    assert excinfo.value.code == 1, (
        f"{module_name}: lote com todas as linhas rejeitadas tem que ser "
        "tratado como erro (exit 1), nunca como 'nada a notificar' (exit 2)"
    )
    assert not Path(str(state_file) + ".tmp").exists(), (
        f"{module_name}: este exit(1) nao pode escrever state.tmp -- o "
        "run.ps1 o commitaria no ramo idempotente e apagaria a idempotencia "
        "viva (regressao real corrigida em bd2e7b6)"
    )
    assert (
        state_file.read_text(encoding="utf-8") == state_original
    ), f"{module_name}: o state vivo tem que permanecer intocado"


def _funcoes_de_topo(caminho: Path) -> set[str]:
    arvore = ast.parse(caminho.read_text(encoding="utf-8"), filename=str(caminho))
    return {
        node.name
        for node in arvore.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_ambos_expoem_o_mesmo_conjunto_de_funcoes_de_escrita_de_state() -> None:
    """OFST e ORB têm que expor localmente as mesmas funções de leitura/escrita
    de state (`_read_notified`, `_write_state_tmp`, `_write_counts`,
    `_write_result`) -- é a superfície que o `run.ps1` de cada automação
    reconcilia via `.tmp` e que os testes de unidade de cada uma já
    monkeypatcham. Não compara `validators.py` inteiro nem o restante das
    funções top-level (essas divergem por design: só o ORB tem reservas de
    estoque com janela, `todas_falhas_por_montagem` etc.)."""
    funcoes_ofst = _funcoes_de_topo(OFST_DIR / "extract_ofst.py")
    funcoes_orb = _funcoes_de_topo(ORB_DIR / "extract_orb.py")

    faltando_no_ofst = _FUNCOES_DE_STATE_ESPERADAS - funcoes_ofst
    faltando_no_orb = _FUNCOES_DE_STATE_ESPERADAS - funcoes_orb

    assert not faltando_no_ofst, (
        "extract_ofst.py deixou de definir "
        f"{sorted(faltando_no_ofst)}: a "
        "superficie de escrita de state que o run.ps1/OFST-06 reconcilia via "
        ".tmp mudou -- se foi intencional, revise este teste conscientemente."
    )
    assert not faltando_no_orb, (
        "extract_orb.py deixou de definir "
        f"{sorted(faltando_no_orb)}: a "
        "superficie de escrita de state que o run.ps1/ORB-07 reconcilia via "
        ".tmp mudou -- se foi intencional, revise este teste conscientemente."
    )


def test_ambos_tem_o_bloco_de_reconciliacao_de_state_no_run_ps1() -> None:
    """Os dois `run.ps1` reconciliam `$StateTmp` -> `$StateFile` dentro do
    mesmo ramo (`$pyResult.Idempotent`). É esse bloco que a regressão do
    achado 2 atingia: bastou o Python escrever um `.tmp` por engano no ramo
    idempotente para o `run.ps1` -- em qualquer uma das duas automações --
    commitar o state vazio por cima do state vivo. Checagem textual (sem
    `pwsh` disponível neste ambiente de auditoria)."""
    for automation_dir, nome in ((OFST_DIR, "OFST-06"), (ORB_DIR, "ORB-07")):
        conteudo = (automation_dir / "run.ps1").read_text(encoding="utf-8")
        assert (
            "$StateTmp" in conteudo and "$StateFile" in conteudo
        ), f"{nome}: run.ps1 nao declara $StateTmp/$StateFile"
        assert "$pyResult.Idempotent" in conteudo, (
            f"{nome}: run.ps1 perdeu o ramo de reconciliacao idempotente "
            "($pyResult.Idempotent) que faz Move-Item $StateTmp $StateFile"
        )
        # Presenca de `Move-Item $StateTmp $StateFile` no arquivo NAO basta:
        # os dois run.ps1 tem DUAS ocorrencias (o ramo idempotente e o caminho
        # de sucesso normal). Uma assercao de substring global fica verde com o
        # bloco do ramo idempotente inteiro removido -- ou seja, com a correcao
        # do achado 2 desfeita. E preciso ancorar dentro do ramo.
        corpo_idempotente = conteudo.split("$pyResult.Idempotent", 1)[1].split("}", 1)[
            0
        ]
        assert "Move-Item $StateTmp $StateFile" in corpo_idempotente, (
            f"{nome}: o ramo $pyResult.Idempotent nao reconcilia mais "
            "$StateTmp em $StateFile via Move-Item -- e esse bloco, e nao "
            "outra ocorrencia qualquer no arquivo, que a regressao do achado "
            "2 atingia"
        )
