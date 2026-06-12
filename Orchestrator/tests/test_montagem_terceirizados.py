# pylint: disable=protected-access, reimported, redefined-outer-name, unused-variable, line-too-long, wrong-import-position, unused-argument, import-error
"""
Suite de Testes Unitários: Automação de Montagem de Terceirizados
Valida o extrator Oracle Thick Mode e o processador sintático de NF/OB.
"""

import io
import json
import os
import sys
from typing import Any
from unittest.mock import MagicMock, patch


# Salvar referência real antes de mockar
real_exists = os.path.exists

# Adicionar pasta da automacao ao PYTHONPATH dinamicamente
AUTOMATION_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "Montagem de Terceirizados")
)
sys.path.append(AUTOMATION_PATH)

import extract_oracle  # type: ignore
import validate_and_generate_html  # type: ignore


def test_parse_qt_pc_nf_formats() -> None:
    """Valida o parser de quantidade e NF em diversos formatos sintáticos."""
    f = validate_and_generate_html.parse_qt_pc_nf

    # Cenário 1: Formato clássico
    res1 = f("10-12345")
    assert len(res1) == 1
    assert res1[0]["qtd"] == 10
    assert res1[0]["nf"] == "12345"

    # Cenário 2: Espaços e sufixos
    res2 = f(" 5 - 98765 - Faccao Leste ")
    assert len(res2) == 1
    assert res2[0]["qtd"] == 5
    assert res2[0]["nf"] == "98765"
    assert res2[0]["origem"] == "Faccao Leste"

    # Cenário 3: Múltiplos itens separados por ponto e vírgula ou vírgula
    res3 = f("15-11111; 8-22222-Oeste")
    assert len(res3) == 2
    assert res3[0]["qtd"] == 15
    assert res3[0]["nf"] == "11111"
    assert res3[1]["qtd"] == 8
    assert res3[1]["nf"] == "22222"
    assert res3[1]["origem"] == "Oeste"

    # Cenário 4: Texto inválido
    assert len(f("Texto inválido sem padrão")) == 0


def test_processar_validacao_erros() -> None:
    """Valida se a regra de negócio compara corretamente NF esperada, montagem e programação."""
    p = validate_and_generate_html.processar_validacao

    dados = [
        # Cenário A: Tudo correto (sem erros) -> não deve constar na listagem de erros
        {
            "CD_REF_CLT": "123",
            "QT_PC_NF": "10-123",
            "OBS_OB": "NF: 123",
            "NR_OB": "OB-001",
        },
        # Cenário B: Erro de Montagem (NF montagem difere de CD_REF_CLT)
        {
            "CD_REF_CLT": "123",
            "QT_PC_NF": "10-999",  # Divergente
            "OBS_OB": "NF: 123",
            "NR_OB": "OB-002",
        },
        # Cenário C: Erro de Programação (NF da obs difere de CD_REF_CLT)
        {
            "CD_REF_CLT": "123",
            "QT_PC_NF": "10-123",
            "OBS_OB": "NF: 888",  # Divergente
            "NR_OB": "OB-003",
        },
        # Cenário D: Erro de Montagem e Programação
        {
            "CD_REF_CLT": "123",
            "QT_PC_NF": "10-999",  # Divergente
            "OBS_OB": "NF: 888",  # Divergente
            "NR_OB": "OB-004",
        },
    ]

    erros = p(dados)

    # Apenas os cenários B, C e D devem gerar registros de erro
    assert len(erros) == 3

    # OB-002: Erro de Montagem
    err_ob2 = next(x for x in erros if x["NR_OB"] == "OB-002")
    assert err_ob2["DETALHE_ERRO"] == "Erro de Montagem"
    assert err_ob2["TEM_ERRO_MONTAGEM"] is True

    # OB-003: Erro de Programação
    err_ob3 = next(x for x in erros if x["NR_OB"] == "OB-003")
    assert err_ob3["DETALHE_ERRO"] == "Erro de Programação"
    assert err_ob3["TEM_ERRO_MONTAGEM"] is False

    # OB-004: Erro de Montagem e Programação
    err_ob4 = next(x for x in erros if x["NR_OB"] == "OB-004")
    assert err_ob4["DETALHE_ERRO"] == "Erro de Montagem e Programação"


def test_gerar_html_estilo_terceirizados() -> None:
    """Garante que as funções auxiliares de HTML do robô de terceirizados estilizam corretamente."""
    destaque_m = validate_and_generate_html.destaque_nf_montagem
    destaque_p = validate_and_generate_html.destaque_nf_prog
    formatar_kanban = validate_and_generate_html.formatar_nr_kanban

    # Destaque Montagem
    html_m = destaque_m("123, 999", "123")
    assert "color:#166534" in html_m  # Verde para o correto 123
    assert "background:#fee2e2" in html_m  # Vermelho para o incorreto 999

    # Destaque Programação
    html_p_ok = destaque_p("123", "123")
    assert "color:#166534" in html_p_ok
    html_p_err = destaque_p("888", "123")
    assert "background:#fee2e2" in html_p_err

    html_kanban = formatar_kanban({"NR_KANBAN": "KAN-456"})
    assert "KAN-456" in html_kanban
    assert "background:#f5f3ff" in html_kanban

    html_kanban_vazio = formatar_kanban({"NR_KANBAN": None})
    assert "N/A" in html_kanban_vazio


def test_tabelas_html_exibem_placa_kanban_quando_disponivel() -> None:
    """Garante que a placa kanban aparece nas tabelas de resumo e detalhamento."""
    erro = {
        "ST_OB_ABERTO": "1",
        "NR_PROG": "PRG-10",
        "NR_KANBAN": "KAN-123",
        "DS_ITEMPED_CLT": "Faccao Norte",
        "NR_OB": "OB-100",
        "NF_ESPERADA": "555",
        "NF_MONTAGEM": "555, 999",
        "QT_PECA_NF_INCORRETA": 8,
        "NF_PROGRAMACAO": "555",
        "DETALHE_ERRO": "Erro de Montagem",
        "CD_ALTERNATIVO": "ALT-01",
        "TEM_ERRO_MONTAGEM": True,
    }

    resumo_html = validate_and_generate_html.gerar_tabela_categoria_html(
        "Novos", [erro], "#dc2626"
    )
    assert "Placa Kanban" in resumo_html
    assert "KAN-123" in resumo_html

    detalhe_html = validate_and_generate_html.gerar_tabela_completa_erros([erro])
    assert "Placa Kanban" in detalhe_html
    assert "KAN-123" in detalhe_html


def test_tabelas_html_tratam_kanban_ausente_sem_quebrar_layout() -> None:
    """Garante fallback visual quando a OB nao possui placa kanban."""
    erro_sem_kanban = {
        "ST_OB_ABERTO": "1",
        "NR_PROG": "PRG-11",
        "NR_KANBAN": None,
        "DS_ITEMPED_CLT": "Faccao Sul",
        "NR_OB": "OB-101",
        "NF_ESPERADA": "777",
        "NF_MONTAGEM": "888",
        "QT_PECA_NF_INCORRETA": 4,
        "NF_PROGRAMACAO": "777",
        "DETALHE_ERRO": "Erro de Montagem",
        "CD_ALTERNATIVO": "ALT-02",
        "TEM_ERRO_MONTAGEM": True,
    }

    resumo_html = validate_and_generate_html.gerar_tabela_categoria_html(
        "Pendentes", [erro_sem_kanban], "#b45309"
    )
    detalhe_html = validate_and_generate_html.gerar_tabela_completa_erros(
        [erro_sem_kanban]
    )

    assert "Placa Kanban" in resumo_html
    assert "Placa Kanban" in detalhe_html
    assert "N/A" in resumo_html
    assert "N/A" in detalhe_html


@patch("validate_and_generate_html.os.remove")
@patch("validate_and_generate_html.os.path.exists")
@patch("validate_and_generate_html.open")
def test_main_tipo_notif_erro_gera_payload(
    mock_open_fn: Any, mock_exists: Any, mock_remove: Any
) -> None:
    """Valida que main() determina tipo_notif=ERRO e grava o payload quando há erros novos sem cache anterior."""
    exec_id = "test_notif_err_001"

    # Registro com NF de montagem divergente → processar_validacao gerará 1 erro
    data = [
        {
            "CD_REF_CLT": "123",
            "QT_PC_NF": "10-999",  # NF 999 ≠ CD_REF_CLT 123
            "OBS_OB": "NF: 123",
            "NR_OB": "OB-ERR-001",
            "ST_OB_ABERTO": "1",
            "NR_PROG": "PRG-01",
            "NR_KANBAN": None,
            "DS_ITEMPED_CLT": "Faccao A",
            "QT_PECA_NF_INCORRETA": 10,
            "CD_ALTERNATIVO": "",
        }
    ]

    def side_exists(path: str) -> bool:
        return f".data_{exec_id}" in path  # Apenas o arquivo de dados existe

    mock_exists.side_effect = side_exists

    def side_open(path: str, mode: str = "r", encoding: Any = None) -> Any:
        ctx = MagicMock()
        if f".data_{exec_id}" in path and "r" in mode:
            ctx.__enter__.return_value = io.StringIO(json.dumps(data))
        else:
            ctx.__enter__.return_value = io.StringIO()
        ctx.__exit__ = MagicMock(return_value=False)
        return ctx

    mock_open_fn.side_effect = side_open

    captured_dumps: list[Any] = []

    def fake_json_dump(obj: Any, fp: Any, **kwargs: Any) -> None:
        captured_dumps.append(obj)

    with patch("validate_and_generate_html.json.load", return_value=data), \
         patch("validate_and_generate_html.json.dump", side_effect=fake_json_dump), \
         patch("validate_and_generate_html.sys.argv", ["validate_and_generate_html.py", exec_id]), \
         patch("validate_and_generate_html.sys.exit") as mock_exit:
        validate_and_generate_html.main()

    # Não deve terminar com erro
    mock_exit.assert_not_called()

    # O payload gerado deve ter tipo_notificacao=ERRO (primeira execução com erros)
    payload = next((d for d in captured_dumps if isinstance(d, dict) and "tipo_notificacao" in d), None)
    assert payload is not None, "Payload de notificação não foi gerado"
    assert payload["tipo_notificacao"] == "ERRO"
    assert payload["total_erros"] >= 1


@patch("validate_and_generate_html.os.remove")
@patch("validate_and_generate_html.os.path.exists")
@patch("validate_and_generate_html.open")
def test_main_sem_erros_nao_gera_payload(
    mock_open_fn: Any, mock_exists: Any, mock_remove: Any
) -> None:
    """Valida que main() não grava payload quando não há divergências (tipo_notif=NENHUMA)."""
    exec_id = "test_notif_nenhuma_001"

    # Registro sem divergência → processar_validacao não gerará erros
    data = [
        {
            "CD_REF_CLT": "123",
            "QT_PC_NF": "10-123",  # NF 123 == CD_REF_CLT 123 → sem erro
            "OBS_OB": "NF: 123",
            "NR_OB": "OB-OK-001",
            "ST_OB_ABERTO": "1",
            "NR_PROG": "PRG-02",
            "NR_KANBAN": None,
            "DS_ITEMPED_CLT": "Faccao B",
            "QT_PECA_NF_INCORRETA": 0,
            "CD_ALTERNATIVO": "",
        }
    ]

    mock_exists.side_effect = lambda path: f".data_{exec_id}" in path

    def side_open(path: str, mode: str = "r", encoding: Any = None) -> Any:
        ctx = MagicMock()
        ctx.__enter__.return_value = io.StringIO()
        ctx.__exit__ = MagicMock(return_value=False)
        return ctx

    mock_open_fn.side_effect = side_open

    captured_dumps: list[Any] = []

    with patch("validate_and_generate_html.json.load", return_value=data), \
         patch("validate_and_generate_html.json.dump", side_effect=lambda o, f, **k: captured_dumps.append(o)), \
         patch("validate_and_generate_html.sys.argv", ["validate_and_generate_html.py", exec_id]), \
         patch("validate_and_generate_html.sys.exit") as mock_exit:
        validate_and_generate_html.main()

    mock_exit.assert_not_called()

    # Sem erros e sem cache anterior → tipo_notif = NENHUMA → nenhum payload gerado
    payload = next((d for d in captured_dumps if isinstance(d, dict) and "tipo_notificacao" in d), None)
    assert payload is None, f"Payload não deveria ser gerado, mas foi: {payload}"


@patch("extract_oracle.oracledb.connect")
@patch("extract_oracle.os.path.exists")
@patch("extract_oracle.open")
def test_extract_sucesso_oracle_mockado(
    mock_open: Any, mock_exists: Any, mock_connect: Any, tmp_path: Any
) -> None:
    """Valida se o extract() lê a query SQL e grava os dados extraídos no json temporário."""
    exec_id = "test_extract"

    # Configuração de Mocks
    os.environ["ORACLE_READONLY_USER"] = "test_user"
    os.environ["ORACLE_READONLY_PASSWORD"] = "test_pass"
    os.environ["ORACLE_CLIENT_LIB_DIR"] = tmp_path.as_posix()
    os.environ["TNS_ADMIN"] = tmp_path.as_posix()

    mock_exists.side_effect = lambda path: "SQL-MontagemTerceirizados" in path or real_exists(path)

    sql_content = "SELECT * FROM MONTAGEM"
    mock_file_sql = MagicMock()
    mock_file_sql.read.return_value = sql_content

    # Mocks de open
    mock_open.side_effect = lambda path, mode="r", encoding=None: mock_file_sql if "SQL-MontagemTerceirizados" in path else MagicMock()

    # Mocks de banco Oracle
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_conn
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor

    # Retorna uma lista de registros mockados no fetchmany
    mock_cursor.description = [("NR_OB",), ("CD_REF_CLT",), ("QT_PC_NF",), ("OBS_OB",)]
    mock_cursor.fetchmany.side_effect = [
        [("OB-001", "123", "10-123", "NF: 123")],
        None,  # Termina o laço
    ]

    with patch("extract_oracle.sys.argv", ["extract_oracle.py", exec_id]), \
         patch("extract_oracle.sys.exit") as mock_exit:

        extract_oracle.extract()

        # O script de extração deve completar sem erro
        mock_exit.assert_not_called()
