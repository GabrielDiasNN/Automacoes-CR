"""Testes unitários de Tools/oracle/gerar_catalogo_sql.py (sem tocar o Oracle)."""

import json
import sys
from pathlib import Path

import pytest
from tests.carregadores_modulos import (
    acessar_privado as _priv,
    carregar_tool_oracle as _carregar,
)

gc = _carregar("gerar_catalogo_sql")

_sha8 = _priv(gc, "_sha8")
_header_field = _priv(gc, "_header_field")
_inventory = _priv(gc, "_inventory")
_load_status = _priv(gc, "_load_status")
_merge_evidence = _priv(gc, "_merge_evidence")
_status_cell = _priv(gc, "_status_cell")
_br_date = _priv(gc, "_br_date")

pytestmark = pytest.mark.unitario


@pytest.fixture(name="mini_ambiente")
def _mini_ambiente(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Cria mini-ambiente temporário com pastas SQL de teste."""
    sql_root = tmp_path / "sql"
    sql_root.mkdir()
    catalog = sql_root / "CATALOGO_QUERIES.md"
    status_file = sql_root / "validacao_status.json"

    # Redireciona constantes de módulo para tmp_path
    monkeypatch.setattr(gc, "ROOT", tmp_path)
    monkeypatch.setattr(gc, "SQL_ROOT", sql_root)
    monkeypatch.setattr(gc, "CONSULTAS_ROOT", sql_root)
    monkeypatch.setattr(gc, "CATALOG", catalog)
    monkeypatch.setattr(gc, "STATUS_FILE", status_file)

    return {"sql_root": sql_root, "catalog": catalog, "status_file": status_file}


def _criar_sql(
    pasta: Path, nome: str, objetivo: str = "", tipo: str = "", binds: str = ""
) -> Path:
    """Cria arquivo .sql com cabeçalho padrão."""
    arquivo = pasta / nome
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    conteudo = f"""/* ====
OBJETIVO: {objetivo}
TIPO: {tipo}
PARÂMETROS / BINDS: {binds}
==== */
"""
    # Corpo fixo fora da f-string: o bandit (B608) le f-string com SELECT como SQL montado.
    conteudo += "SELECT 1 FROM DUAL\n"
    arquivo.write_text(conteudo, encoding="utf-8")
    return arquivo


def test_sha8_gera_hash_truncado(tmp_path: Path) -> None:
    """_sha8 retorna hash SHA256 truncado a 8 caracteres."""
    arquivo = tmp_path / "teste.sql"
    arquivo.write_text("SELECT 1 FROM DUAL", encoding="utf-8")
    hash_resultado = _sha8(arquivo)
    assert len(hash_resultado) == 8
    assert hash_resultado.isalnum()
    # Mesmo conteúdo deve gerar mesmo hash
    assert _sha8(arquivo) == hash_resultado


def test_sha8_ignora_diferenca_crlf_lf_e_bate_com_o_validador(tmp_path: Path) -> None:
    """O mesmo SQL em CRLF e em LF gera o mesmo hash, no gerador e no validador."""
    crlf = tmp_path / "crlf.sql"
    lf = tmp_path / "lf.sql"
    crlf.write_bytes(b"SELECT 1\r\nFROM DUAL\r\n")
    lf.write_bytes(b"SELECT 1\nFROM DUAL\n")
    assert _sha8(crlf) == _sha8(lf)
    validador = sys.modules["validar_sql_oracle"]
    assert validador.content_sha256(crlf.read_bytes()) == validador.content_sha256(
        lf.read_bytes()
    )
    assert validador.content_sha256(lf.read_bytes())[:8] == _sha8(lf)


def test_header_field_extrai_objetivo_com_bloco_comentario(tmp_path: Path) -> None:
    """_header_field extrai OBJETIVO de cabeçalho com /* */."""
    arquivo = _criar_sql(tmp_path, "teste.sql", objetivo="Consultar histórico")
    texto = arquivo.read_text(encoding="utf-8")
    assert _header_field(texto, "OBJETIVO") == "Consultar histórico"


def test_header_field_extrai_tipo_com_traco_comentario() -> None:
    """_header_field extrai TIPO de cabeçalho com -- ."""
    conteudo = """-- OBJETIVO: Teste
-- TIPO: Painel de Controle
SELECT 1 FROM DUAL
"""
    assert _header_field(conteudo, "TIPO") == "Painel de Controle"


def test_header_field_retorna_vazio_quando_campo_nao_existe() -> None:
    """_header_field retorna string vazia quando campo não existe."""
    conteudo = "/* ====\nOBJETIVO: teste\n==== */\nSELECT 1"
    assert _header_field(conteudo, "TIPO") == ""


def test_header_field_ignora_pipe_em_tipo() -> None:
    """_header_field substitui pipe por barra."""
    conteudo = """/*
TIPO: Painel | KPI
*/
SELECT 1
"""
    assert _header_field(conteudo, "TIPO") == "Painel / KPI"


def test_inventory_lista_apenas_sql_de_pastas_nn(
    mini_ambiente: dict[str, Path],
) -> None:
    """_inventory lista apenas .sql de pastas NN_*."""
    sql_root = mini_ambiente["sql_root"]

    # Cria estrutura
    (sql_root / "01_teste").mkdir()
    (sql_root / "02_outra").mkdir()
    (sql_root / "invalid_folder").mkdir()

    _criar_sql(sql_root / "01_teste", "query1.sql", objetivo="Teste 1")
    _criar_sql(sql_root / "02_outra", "query2.sql", objetivo="Teste 2")
    _criar_sql(sql_root / "invalid_folder", "query3.sql", objetivo="Inválido")

    # Cria arquivo não-.sql
    (sql_root / "01_teste" / "readme.txt").write_text("readme")

    items = _inventory()

    # Deve encontrar 2 arquivos .sql válidos, ignorar pasta inválida e arquivo .txt
    assert len(items) == 2
    assert any(item["file"] == "query1.sql" for item in items)
    assert any(item["file"] == "query2.sql" for item in items)
    assert not any("query3.sql" in item["file"] for item in items)
    assert not any("readme" in item["file"] for item in items)


def test_inventory_recursivo_encontra_arquivos_em_subpastas(
    mini_ambiente: dict[str, Path],
) -> None:
    """_inventory é recursivo e encontra .sql em subpastas."""
    sql_root = mini_ambiente["sql_root"]

    (sql_root / "01_teste").mkdir()
    (sql_root / "01_teste" / "subpasta").mkdir()

    _criar_sql(sql_root / "01_teste", "query1.sql", objetivo="Root")
    _criar_sql(sql_root / "01_teste" / "subpasta", "query2.sql", objetivo="Sub")

    items = _inventory()
    assert len(items) == 2
    assert any(item["file"] == "query1.sql" for item in items)
    assert any(item["file"] == "subpasta/query2.sql" for item in items)


def test_inventory_extrai_binds_corretamente(mini_ambiente: dict[str, Path]) -> None:
    """_inventory extrai binds (`:dt_inicio` → DT_INICIO)."""
    sql_root = mini_ambiente["sql_root"]
    (sql_root / "01_teste").mkdir()

    conteudo = """/* OBJETIVO: Teste
TIPO: Query */
SELECT * FROM TAB WHERE DT >= :dt_inicio AND DT < :dt_fim
"""
    arquivo = sql_root / "01_teste" / "query.sql"
    arquivo.write_text(conteudo, encoding="utf-8")

    items = _inventory()
    assert len(items) == 1
    # Binds devem estar em ordem alfabética, maiúsculos
    assert sorted(items[0]["binds"]) == ["DT_FIM", "DT_INICIO"]


def test_inventory_nao_confunde_colunas_com_binds(
    mini_ambiente: dict[str, Path],
) -> None:
    """_inventory não extrai ':' dentro de literais de texto."""
    sql_root = mini_ambiente["sql_root"]
    (sql_root / "01_teste").mkdir()

    conteudo = """/* OBJETIVO: Teste */
SELECT * FROM TAB WHERE MSG = 'uso de :colon' AND ID = :id_real
"""
    arquivo = sql_root / "01_teste" / "query.sql"
    arquivo.write_text(conteudo, encoding="utf-8")

    items = _inventory()
    assert len(items) == 1
    # Deve extrair apenas :id_real, não :colon do literal
    assert items[0]["binds"] == ["ID_REAL"]


def test_inventory_sql_sem_cabecalho_nao_quebra(mini_ambiente: dict[str, Path]) -> None:
    """Arquivo .sql sem cabeçalho não quebra o inventário."""
    sql_root = mini_ambiente["sql_root"]
    (sql_root / "01_teste").mkdir()

    arquivo = sql_root / "01_teste" / "simples.sql"
    arquivo.write_text("SELECT 1 FROM DUAL", encoding="utf-8")

    items = _inventory()
    assert len(items) == 1
    # OBJETIVO vazio deve mostrar texto padrão
    assert items[0]["objetivo"] == "(sem OBJETIVO no cabeçalho)"
    assert items[0]["tipo"] == ""


@pytest.mark.usefixtures("mini_ambiente")
def test_load_status_arquivo_ausente_retorna_estrutura_vazia() -> None:
    """_load_status com arquivo ausente retorna estrutura vazia válida."""
    # STATUS_FILE não existe
    status = _load_status()
    assert status["schema"] == "sql-catalog-status/v1"
    assert status["files"] == {}


def test_load_status_arquivo_existente_retorna_conteudo(
    mini_ambiente: dict[str, Path],
) -> None:
    """_load_status lê arquivo JSON existente."""
    status_file = mini_ambiente["status_file"]
    dados = {
        "schema": "sql-catalog-status/v1",
        "files": {"01_teste/query.sql": {"status": "validated"}},
    }
    status_file.write_text(json.dumps(dados), encoding="utf-8")

    status = _load_status()
    assert status["files"]["01_teste/query.sql"]["status"] == "validated"


def test_merge_evidence_incorpora_validacao_e_guarda_hash(
    mini_ambiente: dict[str, Path],
) -> None:
    """_merge_evidence incorpora JSON de evidência e guarda hash do arquivo."""
    status = {"schema": "sql-catalog-status/v1", "files": {}}
    evidence_file = mini_ambiente["sql_root"] / "evidence.json"

    evidence = {
        "results": [
            {
                "file": "Produção Beneficimento/sql/01_teste/query.sql",
                "status": "validated",
                "rows": 42,
                "execute_ms": 100.5,
                "raw_sha256": "abcdef0123456789",
                "started_at_utc": "2026-09-29T10:00:00",
                "validator_version": "2.1.0",
                "error": None,
            }
        ],
        "generated_at_utc": "2026-09-29T10:00:00",
    }
    evidence_file.write_text(json.dumps(evidence), encoding="utf-8")

    resultado = _merge_evidence(status, evidence_file)

    assert "01_teste/query.sql" in resultado["files"]
    record = resultado["files"]["01_teste/query.sql"]
    assert record["status"] == "validated"
    assert record["sample_rows"] == 42
    assert record["execute_ms"] == 100.5
    assert record["sha8"] == "abcdef01"
    assert record["validated_at"] == "2026-09-29"


def test_merge_evidence_remove_prefixo_de_caminho(
    mini_ambiente: dict[str, Path],
) -> None:
    """_merge_evidence remove o prefixo do acervo (`CONSULTAS_ROOT`) da chave."""
    status = {"schema": "sql-catalog-status/v1", "files": {}}
    evidence_file = mini_ambiente["sql_root"] / "evidence.json"

    evidence = {
        "results": [
            {
                "file": "sql/02_pasta/arquivo.sql",
                "status": "validated",
            }
        ],
        "generated_at_utc": "2026-09-29",
    }
    evidence_file.write_text(json.dumps(evidence), encoding="utf-8")

    resultado = _merge_evidence(status, evidence_file)
    assert "02_pasta/arquivo.sql" in resultado["files"]
    assert list(resultado["files"]) == ["02_pasta/arquivo.sql"]


def test_merge_evidence_aceita_prefixo_legado_do_acervo(
    mini_ambiente: dict[str, Path],
) -> None:
    """Evidência gravada antes da mudança de pasta ainda é incorporada."""
    evidence_file = mini_ambiente["sql_root"] / "evidence.json"
    evidence = {
        "results": [
            {
                "file": "Produção Beneficimento/sql/02_pasta/arquivo.sql",
                "status": "validated",
            }
        ],
        "generated_at_utc": "2026-09-29",
    }
    evidence_file.write_text(json.dumps(evidence), encoding="utf-8")

    resultado = _merge_evidence({"schema": "x", "files": {}}, evidence_file)

    assert list(resultado["files"]) == ["02_pasta/arquivo.sql"]


def test_merge_evidence_persiste_tentativas_e_queda_inconclusiva(
    mini_ambiente: dict[str, Path],
) -> None:
    """attempts e network_inconclusive (só no bruto) entram no registro mesclado."""
    evidence_file = mini_ambiente["sql_root"] / "evidence.json"
    evidence = {
        "results": [
            {
                "file": "Produção Beneficimento/sql/01_teste/queda.sql",
                "status": "oracle_error",
                "raw_sha256": "abcdef0123456789",
                "started_at_utc": "2026-10-08T10:00:00",
                "error": "DatabaseError: ORA-00028: sessao eliminada",
                "attempts": 5,
                "network_inconclusive": True,
            },
            {
                "file": "Produção Beneficimento/sql/01_teste/ok.sql",
                "status": "validated",
                "raw_sha256": "1234567890abcdef",
                "started_at_utc": "2026-10-08T10:00:00",
                "attempts": 1,
            },
        ],
        "generated_at_utc": "2026-10-08T10:00:00",
    }
    evidence_file.write_text(json.dumps(evidence), encoding="utf-8")

    resultado = _merge_evidence({"schema": "x", "files": {}}, evidence_file)

    queda = resultado["files"]["01_teste/queda.sql"]
    assert queda["attempts"] == 5
    assert queda["network_inconclusive"] is True
    assert queda["cancelled"] is True
    ok = resultado["files"]["01_teste/ok.sql"]
    assert ok["attempts"] == 1
    assert "network_inconclusive" not in ok


@pytest.mark.usefixtures("mini_ambiente")
def test_status_cell_nao_muda_com_tentativas_gravadas() -> None:
    """attempts e network_inconclusive não alteram o status exibido no catálogo."""
    item = {
        "folder": "01_teste",
        "file": "query.sql",
        "key": "01_teste/query.sql",
        "sha8": "abcd1234",
    }
    base = {
        "status": "oracle_error",
        "sha8": "abcd1234",
        "validated_at": "2026-10-08",
        "sample_rows": None,
        "execute_ms": None,
        "cancelled": True,
    }
    com_tentativas = {**base, "attempts": 5, "network_inconclusive": True}

    assert _status_cell(item, com_tentativas) == _status_cell(item, base)


@pytest.mark.usefixtures("mini_ambiente")
def test_status_cell_arquivo_alterado_apos_validacao_descartado() -> None:
    """Status com hash diferente é descartado (arquivo alterado após validação)."""
    item = {
        "folder": "01_teste",
        "file": "query.sql",
        "key": "01_teste/query.sql",
        "sha8": "abcd1234",
    }
    record = {
        "status": "validated",
        "sha8": "xyz98765",  # Hash diferente
        "validated_at": "2026-09-29",
        "sample_rows": 10,
        "execute_ms": 50,
    }

    status, sample, elapsed = _status_cell(item, record)

    # Deve mostrar "alterada após validação"
    assert "alterada após validação" in status
    assert "29/09/2026" in status
    assert "2026-09-29" not in status
    assert sample == "—"
    assert elapsed == "—"


@pytest.mark.usefixtures("mini_ambiente")
def test_status_cell_nao_validada_quando_nao_ha_record() -> None:
    """Arquivo sem registro de validação mostra como não validada."""
    item = {
        "folder": "01_teste",
        "file": "query.sql",
        "key": "01_teste/query.sql",
        "sha8": "abcd1234",
    }

    status, sample, elapsed = _status_cell(item, None)

    assert "não validada" in status
    assert sample == "—"
    assert elapsed == "—"


@pytest.mark.usefixtures("mini_ambiente")
def test_status_cell_pasta_not_validated_mostra_motivo() -> None:
    """Arquivos em pastas NOT_VALIDATED mostram motivo."""
    item = {
        "folder": "11_views_referencia_sgt",
        "file": "view.sql",
        "key": "11_views_referencia_sgt/view.sql",
        "sha8": "abc123",
    }

    status, sample, _ = _status_cell(item, None)

    assert "referência (DDL de view" in status
    assert sample == "—"


def test_render_gera_resumo_com_contagem_correta(
    mini_ambiente: dict[str, Path],
) -> None:
    """render() gera seção Resumo com contagem correta de arquivos."""
    sql_root = mini_ambiente["sql_root"]
    (sql_root / "01_teste").mkdir()
    (sql_root / "02_outra").mkdir()

    _criar_sql(sql_root / "01_teste", "q1.sql", objetivo="Q1")
    _criar_sql(sql_root / "01_teste", "q2.sql", objetivo="Q2")
    _criar_sql(sql_root / "02_outra", "q3.sql", objetivo="Q3")

    items = _inventory()
    status = _load_status()
    catalogo = gc.render(items, status)

    # Deve mencionar 3 arquivos e 2 pastas
    assert "3 arquivos" in catalogo
    assert "2 pastas" in catalogo
    assert "## Resumo" in catalogo
    assert "## Inventário por pasta" in catalogo


def test_render_gera_secoes_por_pasta(mini_ambiente: dict[str, Path]) -> None:
    """render() gera uma seção ### para cada pasta."""
    sql_root = mini_ambiente["sql_root"]
    (sql_root / "01_teste").mkdir()
    (sql_root / "02_outra").mkdir()

    _criar_sql(sql_root / "01_teste", "q1.sql", objetivo="Teste")
    _criar_sql(sql_root / "02_outra", "q2.sql", objetivo="Outra")

    items = _inventory()
    status = _load_status()
    catalogo = gc.render(items, status)

    assert "### 01_teste" in catalogo
    assert "### 02_outra" in catalogo


def test_render_inclui_binds_e_objetivo_tipo(mini_ambiente: dict[str, Path]) -> None:
    """render() inclui binds, objetivo e tipo na tabela."""
    sql_root = mini_ambiente["sql_root"]
    (sql_root / "01_teste").mkdir()

    conteudo = """/* ====
OBJETIVO: Consultar histórico
TIPO: Relatório
PARÂMETROS / BINDS: :dt_inicio
==== */
SELECT * FROM TAB WHERE DT >= :dt_inicio AND ID = :id_numero
"""
    arquivo = sql_root / "01_teste" / "query.sql"
    arquivo.write_text(conteudo, encoding="utf-8")

    items = _inventory()
    status = _load_status()
    catalogo = gc.render(items, status)

    assert "Consultar histórico" in catalogo
    assert "Relatório" in catalogo
    assert "`query.sql`" in catalogo
    # Os dois binds extraídos do SQL (não só o declarado no cabeçalho) aparecem na tabela
    assert "`:dt_inicio`" in catalogo
    assert "`:id_numero`" in catalogo


def test_main_sem_argumentos_grava_catalogo(mini_ambiente: dict[str, Path]) -> None:
    """main([]) grava catálogo em CATALOG (tmp_path)."""
    sql_root = mini_ambiente["sql_root"]
    catalog = mini_ambiente["catalog"]
    (sql_root / "01_teste").mkdir()

    _criar_sql(sql_root / "01_teste", "q1.sql", objetivo="Teste")

    resultado = gc.main([])

    assert resultado == 0
    assert catalog.is_file()
    conteudo = catalog.read_text(encoding="utf-8")
    assert "# Catálogo de Consultas SQL" in conteudo


def test_main_check_retorna_zero_quando_catalogo_atualizado(
    mini_ambiente: dict[str, Path],
) -> None:
    """main(["--check"]) retorna 0 quando catálogo == gerado."""
    sql_root = mini_ambiente["sql_root"]
    (sql_root / "01_teste").mkdir()

    _criar_sql(sql_root / "01_teste", "q1.sql", objetivo="Teste")

    # Gera o catálogo
    gc.main([])

    # Checa sem alterar nada
    resultado = gc.main(["--check"])

    assert resultado == 0


def test_main_check_retorna_um_quando_catalogo_desatualizado(
    mini_ambiente: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """main(["--check"]) retorna 1 quando catálogo está desatualizado."""
    sql_root = mini_ambiente["sql_root"]
    (sql_root / "01_teste").mkdir()

    _criar_sql(sql_root / "01_teste", "q1.sql", objetivo="Teste")

    # Gera o catálogo
    gc.main([])

    # Adiciona novo arquivo .sql
    _criar_sql(sql_root / "01_teste", "q2.sql", objetivo="Novo")

    # Checa - deve desatualizar
    resultado = gc.main(["--check"])

    assert resultado == 1
    captured = capsys.readouterr()
    assert "desatualizado" in captured.err


def test_main_com_evidencia_incorpora_status(mini_ambiente: dict[str, Path]) -> None:
    """main(["--evidencia", path]) incorpora validação no STATUS_FILE."""
    sql_root = mini_ambiente["sql_root"]
    status_file = mini_ambiente["status_file"]
    (sql_root / "01_teste").mkdir()

    _criar_sql(sql_root / "01_teste", "query.sql", objetivo="Teste")

    evidence_file = sql_root / "evidence.json"
    evidence = {
        "results": [
            {
                "file": "Produção Beneficimento/sql/01_teste/query.sql",
                "status": "validated",
                "rows": 10,
                "execute_ms": 50,
                "raw_sha256": "abcdef0123456789",
                "started_at_utc": "2026-09-29",
                "validator_version": "2.1.0",
            }
        ],
        "generated_at_utc": "2026-09-29",
    }
    evidence_file.write_text(json.dumps(evidence), encoding="utf-8")

    resultado = gc.main(["--evidencia", str(evidence_file)])

    assert resultado == 0
    assert status_file.is_file()
    status_dados = json.loads(status_file.read_text(encoding="utf-8"))
    assert "01_teste/query.sql" in status_dados["files"]


def test_inventory_ignora_arquivos_que_nao_sao_sql(
    mini_ambiente: dict[str, Path],
) -> None:
    """_inventory ignora arquivos que não são .sql."""
    sql_root = mini_ambiente["sql_root"]
    (sql_root / "01_teste").mkdir()

    _criar_sql(sql_root / "01_teste", "query.sql", objetivo="Válido")
    (sql_root / "01_teste" / "backup.bak").write_text("backup")
    (sql_root / "01_teste" / "README.md").write_text("readme")

    items = _inventory()
    assert len(items) == 1
    assert items[0]["file"] == "query.sql"


def test_render_inclui_aviso_de_arquivo_gerado(mini_ambiente: dict[str, Path]) -> None:
    """render() inclui aviso de que o arquivo é gerado."""
    sql_root = mini_ambiente["sql_root"]
    (sql_root / "01_teste").mkdir()
    _criar_sql(sql_root / "01_teste", "q.sql")

    items = _inventory()
    status = _load_status()
    catalogo = gc.render(items, status)

    assert "Arquivo gerado — não edite à mão" in catalogo
    assert "gerar_catalogo_sql.py" in catalogo


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("2026-09-29", "29/09/2026"),
        ("2026-01-05", "05/01/2026"),
        ("", ""),
        ("29/09/2026", "29/09/2026"),
        ("2026-09-29T10:00:00", "2026-09-29T10:00:00"),
    ],
)
def test_br_date_converte_so_data_iso_pura(entrada: str, esperado: str) -> None:
    assert _br_date(entrada) == esperado


def test_catalogo_de_consultas_do_repositorio_esta_em_dia() -> None:
    """Gate de CI: `CATALOGO_QUERIES.md` é gerado e não pode divergir do disco."""
    assert (
        gc.main(["--check"]) == 0
    ), "CATALOGO_QUERIES.md desatualizado: rode Tools/oracle/gerar_catalogo_sql.py"
