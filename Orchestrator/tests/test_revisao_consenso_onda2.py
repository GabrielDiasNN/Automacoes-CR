"""Regressões dos achados 2/4 da revisão por consenso estocástico (31/07/2026).

Um teste por defeito, com a âncora do achado no docstring.
"""

import os
from typing import Any, cast

import pytest
from app.constants import MAX_DB_LOGS_CHARS
from app.middleware import _api_keys_match
from app.path_safety import is_contained
from app.routers.executions import _artifact_is_downloadable
from app.security import truncate_log_payload
from app.utils import get_client_ip, validate_script_path
from conftest import AUTH_HEADERS
from fastapi.testclient import TestClient

# Raízes sintéticas montadas a partir de `os.sep` — o gate de portabilidade
# proíbe caminho absoluto literal no código, e um teste de contenção precisa
# comparar caminhos absolutos.
_RAIZ = os.path.abspath(os.path.join(os.sep, "Projeto"))
_IRMAO_MESMO_PREFIXO = _RAIZ + "_bkp"
_IRMAO_SUFIXO_NUMERICO = _RAIZ + "2"


class _FakeClient:  # pylint: disable=too-few-public-methods
    def __init__(self, host: str) -> None:
        self.host = host


class _FakeRequest:  # pylint: disable=too-few-public-methods
    """Substituto mínimo de `fastapi.Request` para `get_client_ip`."""

    def __init__(self, host: str, headers: dict[str, str] | None = None) -> None:
        self.client = _FakeClient(host)
        self.headers = headers or {}


class _FakeExecution:  # pylint: disable=too-few-public-methods
    def __init__(self, artifacts: str | None) -> None:
        self.artifacts = artifacts


# ---------------------------------------------------------------------------
# C8 — contenção de path por prefixo de string
# ---------------------------------------------------------------------------


@pytest.mark.unitario
def test_diretorio_irmao_nao_e_considerado_dentro_do_projeto() -> None:
    """Um diretório irmão de mesmo prefixo satisfazia o `startswith`.

    Prefixo de string não respeita fronteira de diretório: a pasta do projeto
    com um sufixo colado (`_bkp`, `2`) passava como "dentro do projeto" — e esse
    é o caminho do script que o worker vai executar.
    """
    assert is_contained(_RAIZ, os.path.join(_RAIZ, "sub", "run.ps1")) is True
    assert is_contained(_RAIZ, os.path.join(_IRMAO_MESMO_PREFIXO, "run.ps1")) is False
    assert is_contained(_RAIZ, os.path.join(_IRMAO_SUFIXO_NUMERICO, "run.ps1")) is False


@pytest.mark.unitario
def test_contencao_ignora_diferenca_de_caixa() -> None:
    """No Windows a caixa não distingue diretórios; o `startswith` distinguia.

    O mesmo caminho grafado em minúsculas era rejeitado indevidamente.
    """
    assert is_contained(_RAIZ, os.path.join(_RAIZ.lower(), "sub", "run.ps1")) is True


@pytest.mark.unitario
def test_script_path_fora_do_projeto_e_rejeitado() -> None:
    ok, detalhe = validate_script_path(
        os.path.join("..", "..", "fora", "evil.ps1"), _RAIZ
    )
    assert ok is False
    assert "fora do diretório permitido" in detalhe


# ---------------------------------------------------------------------------
# C10 — download de artefato sem allowlist
# ---------------------------------------------------------------------------


@pytest.mark.unitario
def test_config_sensivel_nao_e_baixavel_como_artefato() -> None:
    """`?filename=whatsapp-config.json` devolvia o contactId do destinatário."""
    execucao = _FakeExecution(artifacts='["relatorio.xlsx"]')
    assert _artifact_is_downloadable(cast(Any, execucao), "relatorio.xlsx") is True
    assert (
        _artifact_is_downloadable(cast(Any, execucao), "whatsapp-config.json") is False
    )
    assert (
        _artifact_is_downloadable(cast(Any, execucao), "delivery_state.json") is False
    )


@pytest.mark.unitario
def test_execucao_legada_sem_artifacts_cai_na_allowlist_de_extensao() -> None:
    """Compatibilidade: `artifacts` nulo não pode liberar arquivo de estado."""
    legada = _FakeExecution(artifacts=None)
    assert _artifact_is_downloadable(cast(Any, legada), "relatorio.xlsx") is True
    assert _artifact_is_downloadable(cast(Any, legada), "relatorio.pdf") is True
    assert _artifact_is_downloadable(cast(Any, legada), "whatsapp-config.json") is False
    assert _artifact_is_downloadable(cast(Any, legada), "run.ps1") is False
    assert _artifact_is_downloadable(cast(Any, legada), "config.json.bak") is False


# ---------------------------------------------------------------------------
# C11 — API Key não-ASCII virava 500 e escapava da detecção de brute-force
# ---------------------------------------------------------------------------


@pytest.mark.unitario
def test_api_key_nao_ascii_nao_levanta_typeerror() -> None:
    """`hmac.compare_digest` sobre str não-ASCII levantava TypeError.

    O request virava 500 e pulava o log `[AUTH_FAIL]`, tornando invisível uma
    varredura de chaves com bytes altos.
    """
    assert _api_keys_match("café", "chave-esperada") is False
    assert _api_keys_match("chave-esperada", "chave-esperada") is True
    assert _api_keys_match("ключ", "chave-esperada") is False


@pytest.mark.integracao
def test_api_key_nao_ascii_devolve_403_e_nao_500(client: TestClient) -> None:
    """Antes: TypeError → 500, sem passar pelo log `[AUTH_FAIL]`.

    O header vai como BYTES latin-1, que é como um cliente HTTP real transmite
    caractere acentuado — e é assim que o Starlette o decodifica de volta,
    produzindo a `str` não-ASCII que fazia `compare_digest` explodir.
    """
    resposta = client.get(
        "/api/automations/all", headers={"X-API-Key": "café".encode("latin-1")}
    )
    assert resposta.status_code == 403, (
        f"Esperado 403 (chave inválida), recebido {resposta.status_code}. "
        "Um 500 significa que a comparação voltou a levantar TypeError."
    )


# ---------------------------------------------------------------------------
# C12 — X-Forwarded-For spoofável definia o actor da auditoria
# ---------------------------------------------------------------------------


@pytest.mark.unitario
def test_x_forwarded_for_e_ignorado_sem_proxy_confiavel() -> None:
    """O header definia `AuditLog.actor`, o artefato de não-repúdio."""
    request = _FakeRequest("127.0.0.1", {"X-Forwarded-For": "1.2.3.4"})
    assert get_client_ip(cast(Any, request)) == "127.0.0.1"


@pytest.mark.unitario
def test_x_forwarded_for_e_aceito_atras_de_proxy_declarado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O suporte a proxy continua, agora explícito."""
    monkeypatch.setenv("ORCHESTRATOR_TRUSTED_PROXIES", "10.0.0.1, 10.0.0.2")
    request = _FakeRequest("10.0.0.1", {"X-Forwarded-For": "1.2.3.4, 10.0.0.1"})
    assert get_client_ip(cast(Any, request)) == "1.2.3.4"


@pytest.mark.unitario
def test_actor_tem_tamanho_limitado(monkeypatch: pytest.MonkeyPatch) -> None:
    """`String(100)` não é imposto pelo SQLite: cabia conteúdo arbitrário."""
    monkeypatch.setenv("ORCHESTRATOR_TRUSTED_PROXIES", "10.0.0.1")
    request = _FakeRequest("10.0.0.1", {"X-Forwarded-For": "A" * 500})
    assert len(get_client_ip(cast(Any, request))) <= 45


# ---------------------------------------------------------------------------
# C20 — parâmetros de listagem sem teto
# ---------------------------------------------------------------------------


@pytest.mark.integracao
@pytest.mark.parametrize(
    "url",
    [
        "/api/system/audit?limit=100000000",
        "/api/system/history?hours=1000000",
        "/api/automations/?per_page=-1",
        "/api/automations/?page=-5",
    ],
)
def test_parametros_fora_do_intervalo_sao_rejeitados(
    client: TestClient, url: str
) -> None:
    """`per_page` negativo virava `LIMIT -1` (sem limite) no SQLite."""
    resposta = client.get(url, headers=AUTH_HEADERS)
    assert resposta.status_code == 422


@pytest.mark.integracao
def test_parametros_validos_continuam_aceitos(client: TestClient) -> None:
    """Guarda contra o teste acima passar por bloquear tudo."""
    assert (
        client.get("/api/system/audit?limit=10", headers=AUTH_HEADERS).status_code
        == 200
    )
    assert (
        client.get(
            "/api/automations/?page=1&per_page=20", headers=AUTH_HEADERS
        ).status_code
        == 200
    )


# ---------------------------------------------------------------------------
# C14 — fallback SPA devolvia 200 para asset ausente
# ---------------------------------------------------------------------------


@pytest.mark.integracao
def test_asset_ausente_devolve_404_e_nao_index_html(client: TestClient) -> None:
    """Deploy quebrado virava tela branca sem nenhum 404 no servidor."""
    resposta = client.get("/dashboard/assets/index-inexistente-abc123.js")
    assert resposta.status_code == 404, (
        "Asset ausente respondeu com index.html e status 200 — o browser falha "
        "por MIME type e o deploy quebrado fica invisível."
    )


@pytest.mark.integracao
def test_rota_client_side_continua_caindo_no_index(client: TestClient) -> None:
    """Guarda: o fallback do react-router precisa continuar funcionando."""
    resposta = client.get("/dashboard/execucoes")
    assert resposta.status_code == 200
    assert "text/html" in resposta.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# C21 — telemetria externa gravava log sem truncamento
# ---------------------------------------------------------------------------


@pytest.mark.unitario
def test_truncamento_de_log_esta_disponivel_para_a_telemetria() -> None:
    """Era o único caminho de escrita que ignorava MAX_DB_LOGS_CHARS."""

    gigante = "x" * (MAX_DB_LOGS_CHARS * 2)
    assert len(truncate_log_payload(gigante)) <= MAX_DB_LOGS_CHARS + 200


# ---------------------------------------------------------------------------
# C5 — o script de retenção precisa rodar em PowerShell 5.1
# ---------------------------------------------------------------------------


@pytest.mark.unitario
def test_script_de_retencao_existe_no_caminho_esperado() -> None:
    """`run_file_cleanup` passou de `pwsh.exe` (PS7) para `powershell.exe`."""
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert os.path.isfile(os.path.join(raiz, "Tools", "AplicarPoliticaRetencao.ps1"))
