# pylint: disable=protected-access, reimported, redefined-outer-name, unused-variable
"""
Suite de Testes Unitários: Automação de Montagem de Terceirizados
Valida o extrator Oracle Thick Mode e o processador sintático de NF/OB.
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Salvar referência real antes de mockar
real_exists = os.path.exists

# Adicionar pasta da automacao ao PYTHONPATH dinamicamente
AUTOMATION_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "Montagem de Terceirizados")
)
sys.path.append(AUTOMATION_PATH)

import extract_oracle
import validate_and_generate_html


def test_parse_qt_pc_nf_formats():
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


def test_processar_validacao_erros():
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


def test_gerar_html_estilo_terceirizados():
    """Garante que as funções auxiliares de HTML do robô de terceirizados estilizam corretamente."""
    destaque_m = validate_and_generate_html.destaque_nf_montagem
    destaque_p = validate_and_generate_html.destaque_nf_prog

    # Destaque Montagem
    html_m = destaque_m("123, 999", "123")
    assert "color:#166534" in html_m  # Verde para o correto 123
    assert "background:#fee2e2" in html_m  # Vermelho para o incorreto 999

    # Destaque Programação
    html_p_ok = destaque_p("123", "123")
    assert "color:#166534" in html_p_ok
    html_p_err = destaque_p("888", "123")
    assert "background:#fee2e2" in html_p_err


@patch("extract_oracle.oracledb.connect")
@patch("extract_oracle.os.path.exists")
@patch("extract_oracle.open")
def test_extract_sucesso_oracle_mockado(mock_open, mock_exists, mock_connect, tmp_path):
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
