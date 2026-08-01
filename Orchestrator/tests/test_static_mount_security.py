"""Regressão: nenhum diretório de código-fonte pode ser servido como estático.

Até 31/07/2026 `Orchestrator/app/main.py` montava `app.mount("/lib",
StaticFiles(directory=lib_path))`, publicando a árvore inteira de `lib/` —
`Lib-Oracle.psm1`, `Lib-Email.psm1`, `Send-WhatsApp.ps1`, `WhatsApp-Core.js`,
`lib/python/*.py`, `package-lock.json` e `node_modules/`. O mount não passava
por `Depends(get_api_key)` e o `RateLimitMiddleware` só age em `/api`, então o
conteúdo era baixável sem chave e sem limite de taxa.

O mount era resíduo do dashboard vanilla anterior ao React e não tinha
consumidor: nenhuma referência a `/lib/...` existe em `Dashboard/src` ou
`Dashboard/dist`.
"""

import pytest
from fastapi.testclient import TestClient

# Arquivos reais de `lib/` que o mount expunha. Se o mount voltar, pelo menos um
# destes responde 200 com o conteúdo do arquivo.
CAMINHOS_SENSIVEIS = [
    "/lib/Lib-Config.psm1",
    "/lib/Lib-Oracle.psm1",
    "/lib/Lib-Email.psm1",
    "/lib/Send-WhatsApp.ps1",
    "/lib/WhatsApp-Core.js",
    "/lib/python/oracle_extract.py",
    "/lib/package-lock.json",
]


@pytest.mark.integracao
@pytest.mark.parametrize("caminho", CAMINHOS_SENSIVEIS)
def test_lib_nao_e_servido_como_estatico(client: TestClient, caminho: str) -> None:
    """`lib/` não pode ser alcançável por HTTP, com ou sem API Key."""
    resposta = client.get(caminho)
    assert resposta.status_code != 200, (
        f"{caminho} respondeu 200 — o mount de `lib/` voltou a existir. "
        "Esse diretório contém código operacional e configuração; se algum "
        "asset for necessário, monte apenas `lib/assets/`, nunca a raiz."
    )


@pytest.mark.integracao
def test_dashboard_continua_servido(client: TestClient) -> None:
    """Guarda contra o teste acima passar por a aplicação estar quebrada."""
    resposta = client.get("/dashboard/")
    assert resposta.status_code == 200
