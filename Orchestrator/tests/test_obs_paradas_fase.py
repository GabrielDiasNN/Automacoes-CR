"""Smoke tests para OBs Paradas Fase (OBP-04)."""

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).parent.parent.parent
AUTOMATION_DIR = ROOT / "OBs Paradas Fase"


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_manifest_valido() -> None:
    manifest_path = AUTOMATION_DIR / "automation.manifest.json"
    assert manifest_path.exists(), "automation.manifest.json ausente"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["id"] == "OBP-04"
    assert manifest["runtime"] == "powershell"
    assert "whatsapp" in manifest["channels"]


def test_entrypoint_existe() -> None:
    assert (AUTOMATION_DIR / "run.ps1").exists()


def test_scripts_python_existem() -> None:
    assert (AUTOMATION_DIR / "extract_obs.py").exists()
    assert (AUTOMATION_DIR / "generate_phase_cards.py").exists()


def test_whatsapp_config_valido() -> None:
    cfg_path = AUTOMATION_DIR / "whatsapp-config.json"
    assert cfg_path.exists(), "whatsapp-config.json ausente"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert cfg["auth"]["clientId"] == "hub-global"
    assert cfg["target"]["type"] == "group"
    assert re.match(
        r"^[\d\-]+@g\.us$", cfg["target"]["contactId"]
    ), f"contactId inválido: {cfg['target']['contactId']!r} — esperado formato <digitos>@g.us ou <digitos-timestamp>@g.us"


def test_docs_existem() -> None:
    assert (AUTOMATION_DIR / "README.md").exists()
    assert (AUTOMATION_DIR / "CONTEXT.md").exists()


def test_config_json_valido() -> None:
    cfg_path = AUTOMATION_DIR / "config.json"
    assert cfg_path.exists(), "config.json ausente"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert "contatos" not in cfg, (
        "config.json não deve mais conter 'contatos' — números/nomes reais vivem só no "
        ".env local, nunca versionados (ver OBP_CONTATO_* em .env.example)"
    )
    module = _load_module(
        "generate_phase_cards_test", AUTOMATION_DIR / "generate_phase_cards.py"
    )
    contatos = module._load_contatos_from_env()  # pylint: disable=protected-access
    assert "fases_monitoradas" in cfg, "config.json deve conter 'fases_monitoradas'"
    fases = cfg["fases_monitoradas"]
    assert isinstance(fases, dict), "'fases_monitoradas' deve ser um objeto"
    assert len(fases) > 0, "'fases_monitoradas' não pode ser vazio"
    for codigo, dados in fases.items():
        assert (
            codigo.isdigit()
        ), f"chave '{codigo}' de fases_monitoradas deve ser um código numérico"
        assert isinstance(
            dados, dict
        ), f"fases_monitoradas['{codigo}'] deve ser um objeto"
        assert dados.get("descricao"), f"fases_monitoradas['{codigo}'] sem 'descricao'"
        assert isinstance(
            dados.get("ativo"), bool
        ), f"fases_monitoradas['{codigo}'] sem 'ativo' booleano"
        assert isinstance(
            dados.get("threshold_dias"), (int, float)
        ), f"fases_monitoradas['{codigo}'] sem 'threshold_dias' numérico"
        resp_ref = dados.get("responsavel")
        assert resp_ref, f"fases_monitoradas['{codigo}'] sem 'responsavel'"
        assert (
            resp_ref in contatos
        ), f"fases_monitoradas['{codigo}'].responsavel = '{resp_ref}' não existe em 'contatos'"
    # Fase 26 (IVF-INVERSÃO P/FELPAGEM) e fase 65 (FEL-FELPAGEM) devem ter
    # responsáveis distintos, mesmo com texto de descrição parecido.
    assert fases["26"]["responsavel"] != fases["65"]["responsavel"]
    assert "ordem_codigos_fase" in cfg, "config.json deve conter 'ordem_codigos_fase'"
    ordem = cfg["ordem_codigos_fase"]
    assert isinstance(
        ordem, dict
    ), "'ordem_codigos_fase' deve ser um objeto {codigo: descricao}"
    assert len(ordem) > 0, "'ordem_codigos_fase' não pode ser vazio"
    for codigo in ordem:
        assert (
            codigo in fases
        ), f"ordem_codigos_fase referencia código '{codigo}' ausente em fases_monitoradas"
    sql_path = AUTOMATION_DIR / "SQL-ObsParadasFase.sql"
    assert sql_path.exists(), "SQL-ObsParadasFase.sql ausente"


def test_sql_nao_vazio() -> None:
    sql_path = AUTOMATION_DIR / "SQL-ObsParadasFase.sql"
    assert sql_path.exists(), "SQL-ObsParadasFase.sql ausente"
    content = sql_path.read_text(encoding="utf-8").strip()
    assert len(content) > 0, "SQL-ObsParadasFase.sql está vazio"
    assert "SELECT" in content.upper(), "SQL-ObsParadasFase.sql não contém SELECT"
    assert (
        "DT_ENTREGA" in content.upper()
    ), "SQL-ObsParadasFase.sql não contém DT_ENTREGA"
    assert (
        "CODIGO_FASE" in content.upper()
    ), "SQL-ObsParadasFase.sql não expõe CODIGO_FASE"


def test_get_fase_config_resolve_por_codigo_exato() -> None:
    """Regressão: fase 26 (IVF-INVERSÃO P/FELPAGEM) e fase 65 (FEL-FELPAGEM) compartilham
    a substring 'FELPAGEM' no texto da descrição — o matching hoje é 100% por código
    exato (sem nenhum fallback por palavra-chave), então as duas devem resolver para
    configurações independentes mesmo com texto parecido."""
    module = _load_module(
        "generate_phase_cards_test", AUTOMATION_DIR / "generate_phase_cards.py"
    )
    fases = {
        "26": module.FaseConfig("IVF-INVERSÃO P/FELPAGEM", 1, "5500000000026"),
        "65": module.FaseConfig("FEL-FELPAGEM", 1, "5500000000065"),
    }

    cfg_26 = module.get_fase_config("26", fases)
    cfg_65 = module.get_fase_config("65", fases)

    assert cfg_26 is not None and cfg_26.responsavel == "5500000000026"
    assert cfg_65 is not None and cfg_65.responsavel == "5500000000065"
    assert module.get_fase_config("999", fases) is None


def test_fase_inativa_e_excluida_do_envio() -> None:
    """Fase com 'ativo': False não deve gerar card/mensagem, mesmo que exceda o threshold."""
    module = _load_module(
        "generate_phase_cards_test", AUTOMATION_DIR / "generate_phase_cards.py"
    )
    fases = {
        "26": module.FaseConfig(
            "IVF-INVERSÃO P/FELPAGEM", 1, "5500000000026", ativo=True
        ),
        "65": module.FaseConfig("FEL-FELPAGEM", 1, "5500000000065", ativo=False),
    }
    obs = [
        {
            "NUMERO_OB": 1,
            "FASE_ATUAL": "IVF-INVERSÃO P/FELPAGEM",
            "CODIGO_FASE": 26,
            "DIAS_PARADO": 2,
        },
        {
            "NUMERO_OB": 2,
            "FASE_ATUAL": "FEL-FELPAGEM",
            "CODIGO_FASE": 65,
            "DIAS_PARADO": 2,
        },
    ]

    filtradas = module._filter_obs(obs, fases, {})  # pylint: disable=protected-access

    assert [ob["NUMERO_OB"] for ob in filtradas] == [1]


def test_resolve_contato_aceita_objeto_lista_e_string_legada() -> None:
    module = _load_module(
        "generate_phase_cards_test", AUTOMATION_DIR / "generate_phase_cards.py"
    )
    assert (
        module._resolve_contato(  # pylint: disable=protected-access
            {"nome": "Fulano de Tal", "numero": "5500000000001"}
        )
        == "5500000000001"
    )
    assert (
        module._resolve_contato(  # pylint: disable=protected-access
            [
                {"nome": "Fulano de Tal", "numero": "5500000000001"},
                {"nome": "Ciclano da Silva", "numero": "5500000000002"},
            ]
        )
        == "5500000000001 @5500000000002"
    )
    assert (
        module._resolve_contato("5500000000001")  # pylint: disable=protected-access
        == "5500000000001"
    )


def test_config_real_resolve_contatos_por_variavel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regressão de ponta a ponta: 'responsavel' em fases_monitoradas referencia uma
    chave resolvida via .env (nunca um número literal), e cada variável resolve para
    o telefone configurado no ambiente."""
    monkeypatch.setenv("OBP_CONTATO_LIDER_3_TURNO", "5500000000026")
    monkeypatch.setenv("OBP_CONTATO_LIDER_RESERVA_1_TURNO", "5500000000065")
    module = _load_module(
        "generate_phase_cards_test", AUTOMATION_DIR / "generate_phase_cards.py"
    )
    cfg_path = AUTOMATION_DIR / "config.json"

    # pylint: disable-next=protected-access
    fases, _, _, _ = module._load_config(str(cfg_path))

    # Fase 26 (líder 3º turno) e fase 65 (líder reserva 1º turno) devem resolver
    # para números de telefone diferentes.
    assert fases["26"].responsavel == "5500000000026"
    assert fases["65"].responsavel == "5500000000065"
    assert fases["26"].responsavel != fases["65"].responsavel
    # Fase 25 foi explicitamente desativada (decisão de negócio), mesmo mapeada por código.
    assert fases["25"].ativo is False


def test_codigo_fase_key_normaliza_tipos_oracle() -> None:
    """CODIGO_FASE pode chegar como int, float ou str do Oracle/JSON — todos devem
    normalizar para a mesma chave string usada em fases_monitoradas."""
    # pylint: disable=protected-access
    module = _load_module(
        "generate_phase_cards_test", AUTOMATION_DIR / "generate_phase_cards.py"
    )
    assert module._codigo_fase_key({"CODIGO_FASE": 26}) == "26"
    assert module._codigo_fase_key({"CODIGO_FASE": 26.0}) == "26"
    assert module._codigo_fase_key({"CODIGO_FASE": "26"}) == "26"
    assert module._codigo_fase_key({"CODIGO_FASE": None}) is None
