"""Trava a exceção de escrita ORM em routers documentada em `docs/architecture-standard.md`.

`docs/architecture-standard.md` § "Leitura vs. Escrita ORM nos Routers"
documenta 33 ocorrências de escrita ORM (`db.add`/`db.commit`/`db.refresh`/
`db.delete`) em `Orchestrator/app/routers/*.py` como exceção arquitetural
aceita (25 "escrita fina" + 8 "com lógica de negócio", cada uma listada com
`arquivo:linha`). Sem este teste, nada impede que uma 34ª escrita entre sem
revisão consciente, e a tabela de `arquivo:linha` da doc pode envelhecer sem
que ninguém perceba.

Escolha de granularidade: o teste trava o TOTAL agregado (33) e não os pares
`arquivo:linha` da doc. Uma trava por linha exata quebra a cada linha inserida
ACIMA de uma ocorrência existente (deslocamento de número de linha sem
mudança semântica alguma) — isso vira ruído que alguém acaba silenciando sem
de fato revisar a mudança. Contar o total por arquivo já é suficiente para
capturar o caso que importa (uma escrita ORM nova, em qualquer arquivo do
pacote `routers/`) e é robusto a refatorações que apenas movem linhas dentro
do mesmo arquivo. Trocar de arquivo (mover uma escrita fina existente para
`automations.py` -> `system.py`, por exemplo) não muda o total agregado e por
isso não é pego por este teste — é uma limitação aceita em troca de não gerar
falsos positivos a cada edição.

Ao falhar, o teste aponta a ação certa: revisar a escrita nova (é "escrita
fina" sobre payload já validado, ou é lógica de negócio que deveria estar em
um service?) e então atualizar CONSCIENTEMENTE `docs/architecture-standard.md`
(a tabela de `arquivo:linha` e a contagem de 33/25/8) e o número esperado
abaixo — nunca ajustar só o número deste teste sem revisar a doc.
"""

from __future__ import annotations

import re
from pathlib import Path

# Ocorrências totais documentadas em `docs/architecture-standard.md`
# § "Leitura vs. Escrita ORM nos Routers" (25 escrita fina + 8 com lógica de
# negócio movível para service = 33).
TOTAL_ESCRITA_ORM_DOCUMENTADO = 33

_PADRAO_ESCRITA_ORM = re.compile(r"\bdb\.(?:add|commit|refresh|delete)\(")


def _routers_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "app" / "routers"


def _contar_escritas_orm(caminho: Path) -> int:
    conteudo = caminho.read_text(encoding="utf-8")
    return len(_PADRAO_ESCRITA_ORM.findall(conteudo))


def test_total_de_escritas_orm_em_routers_bate_com_a_documentacao() -> None:
    routers_dir = _routers_dir()
    arquivos = sorted(routers_dir.glob("*.py"))
    assert arquivos, f"Nenhum router encontrado em {routers_dir}"

    total = sum(_contar_escritas_orm(arquivo) for arquivo in arquivos)

    assert total == TOTAL_ESCRITA_ORM_DOCUMENTADO, (
        f"Encontradas {total} ocorrencias de db.add/db.commit/db.refresh/"
        f"db.delete em Orchestrator/app/routers/*.py, mas "
        f"docs/architecture-standard.md documenta "
        f"{TOTAL_ESCRITA_ORM_DOCUMENTADO} como excecao aceita.\n\n"
        "Isto NAO e uma falha de teste a ser silenciada ajustando o numero "
        "acima: revise a escrita ORM nova/removida (e escrita fina sobre "
        "payload ja validado, ou logica de negocio que deveria estar em um "
        "service?) e entao atualize CONSCIENTEMENTE a tabela de "
        "arquivo:linha e a contagem em "
        "'docs/architecture-standard.md > Leitura vs. Escrita ORM nos "
        "Routers' junto com TOTAL_ESCRITA_ORM_DOCUMENTADO neste arquivo."
    )
