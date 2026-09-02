# {
#   "version": "1.0.0",
#   "skill": "protocolo-valeg",
#   "description": "Validacoes e simulacoes de dados do ORB-07 — funcoes puras, sem I/O"
# }
"""Camada de confiabilidade do ORB-07.

Regra do modulo: **nenhuma funcao aqui abre conexao ou le arquivo**. Todas
recebem linhas ja buscadas. Quem faz I/O e `extract_orb.py` (producao) e
`test_orb_simulation.py` (simulacao contra Oracle real). Essa separacao e o
que permite exercitar 100% da regra de decisao sem Oracle nos testes
(Orchestrator/tests/test_orb.py) — se as validacoes abrissem a
conexao, so seriam testaveis com o banco de pe.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

# Import de lib/python via sys.path.insert() dinamico — mesmo padrao de
# extract_orb.py. Necessario aqui (e nao so no extrator) porque os testes de
# unidade carregam validators.py isoladamente, sem passar por extract_orb.py.
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "python")
)

from errors import (  # noqa: E402  pylint: disable=wrong-import-position
    DadoIncompletoError,
    SchemaInvalidoError,
)
from models import (  # noqa: E402  pylint: disable=wrong-import-position
    AvaliacaoOb,
    EstoqueDeposito,
    ObRestricaoBranco,
    ReservaNotificacao,
)
from oracle_coerce import (  # noqa: E402  pylint: disable=wrong-import-position,import-error
    coerce_float,
    coerce_int,
)

STATUS_EMITIDA = 1
OBMONTADA_PENDENTE = "0"
DEPOSITO_ALVO = 95
CLASSIFICACOES_BRANCO: dict[int, str] = {
    6: "BRANCO",
    9: "BRANCO 2 FIBRAS",
}
# PESSOASFJ.IDPESSOAFJ = 1 -> CR-MATRIZ/PR, o deposito de malhas da empresa.
# OBs desse cliente vao para o fim da lista (ver priorizar_obs).
ID_CLIENTE_MATRIZ = 1

# Validade da reserva de estoque criada ao anunciar uma OB (ver ReservaNotificacao).
# 24h cobre a espera normal na fila da Expedicao mais uma virada de noite, com a
# automacao rodando a cada 60 min (24 ciclos dentro da janela; eram 12 quando a
# cadencia era de 120 min, ate 01/09/2026). Prazo unico e
# nomeado de proposito: a expiracao remove a OB do `notified` POR COMPLETO, entao
# ela volta a concorrer pelo estoque e pode ser re-anunciada — liberar o saldo sem
# tirar a OB do state recriaria o bug original de forma invisivel.
JANELA_RESERVA_HORAS = 24

# Saldo restrito minimo para anunciar uma OB (ver validate_partial_logic).
# Uma peca basta: o objetivo da automacao e escoar a peca com restricao, e
# deixar 5 pecas para tras porque a OB pede 55 e exatamente o que a Montagem
# de Lotes nao pode fazer.
MINIMO_PECAS_NOTIFICAVEL = 1

COLUNAS_OB_OBRIGATORIAS: tuple[str, ...] = (
    "NUMERO_OB",
    "CODIGO_FLUXO",
    "CODIGO_REDUZIDO_CRU",
    "STATUS",
    "TOTAL_PECAS",
    "KILOS_PROGRAMADOS",
    "OBMONTADA",
    "CODIGO_ARTIGO_CRU",
    "CODIGO_COR_TINGIMENTO",
    "CD_CLASSIFICACAO_COR",
    "DS_CLASSIFICACAO_COR",
    "QTD_CLASSIFICACOES_COR",
    "DT_ENTREGA",
    "ID_CLIENTE",
    "NOME_CLIENTE",
)

COLUNAS_ESTOQUE_OBRIGATORIAS: tuple[str, ...] = (
    "CODIGO_REDUZIDO_PROD",
    "FINALIDADE",
    "EH_TOTAL",
    "QTD_PECAS_DISPONIVEIS",
    "QTD_LINHAS_BRUTAS",
)

COLUNAS_FINALIDADES_OBRIGATORIAS: tuple[str, ...] = (
    "CODCLASSIFICACAO_COR",
    "CODFINALIDADE",
    "DESCRICAO_FINALIDADE",
)

TAMANHO_AMOSTRA = 3


@dataclass
class RelatorioValidacao:
    """Resultado de uma simulacao: veredito + evidencia legivel.

    `obs` guarda as linhas ja coagidas com sucesso (na ordem original) — quem
    chama `validate_ob_query` nao precisa rodar `coerce_ob_row` de novo sobre
    o retorno cru para obter os objetos validados.
    """

    ok: bool = True
    schema_ok: bool = True
    total: int = 0
    amostra: list[dict[str, Any]] = field(default_factory=list)
    problemas: list[str] = field(default_factory=list)
    obs: list[ObRestricaoBranco] = field(default_factory=list)

    def falhar(self, motivo: str) -> None:
        """Marca o relatório como inválido e registra a causa."""
        self.ok = False
        self.problemas.append(motivo)


def _to_int(valor: Any, campo: str, contexto: Any) -> int:
    """Coage NUMBER do Oracle (Decimal/float/str) para int, ou levanta DadoIncompletoError."""
    return coerce_int(valor, campo, contexto, DadoIncompletoError)


def _to_float(valor: Any, campo: str, contexto: Any) -> float:
    return coerce_float(valor, campo, contexto, DadoIncompletoError)


def coerce_ob_row(record: dict[str, Any]) -> ObRestricaoBranco:
    """Converte uma linha crua da query de OBs em ObRestricaoBranco validada.

    Levanta DadoIncompletoError (escopo de uma OB — o chamador loga e pula) para
    qualquer campo nulo, nao-numerico ou fora do dominio esperado.
    """
    id_ob = record.get("NUMERO_OB")
    contexto = f"OB #{id_ob}"

    ob = ObRestricaoBranco(
        id_ob=_to_int(id_ob, "NUMERO_OB", contexto),
        codigo_fluxo=_to_int(record.get("CODIGO_FLUXO"), "CODIGO_FLUXO", contexto),
        codigo_reduzido_cru=_to_int(
            record.get("CODIGO_REDUZIDO_CRU"), "CODIGO_REDUZIDO_CRU", contexto
        ),
        # Opcional (LEFT JOIN no SQL) e ALFANUMERICO: ART.CDARTIGOCRU e texto no
        # Oracle e '0A231'/'0A230' ocorrem em producao — coagir para int descartava
        # a OB inteira (DadoIncompletoError) por um campo que so' aparece numa linha
        # da mensagem. Guardado como texto cru; a apresentacao ja trata texto
        # (_fmt_codigo em format_message.py). OB sem cadastro de artigo continua
        # notificavel — a mensagem mostra "—" no lugar do artigo.
        codigo_artigo_cru=(
            None
            if record.get("CODIGO_ARTIGO_CRU") is None
            else str(record.get("CODIGO_ARTIGO_CRU")).strip() or None
        ),
        codigo_cor_tingimento=(
            None
            if record.get("CODIGO_COR_TINGIMENTO") is None
            else str(record.get("CODIGO_COR_TINGIMENTO")).strip() or None
        ),
        codigo_classificacao_cor=_to_int(
            record.get("CD_CLASSIFICACAO_COR"), "CD_CLASSIFICACAO_COR", contexto
        ),
        descricao_classificacao_cor=str(record.get("DS_CLASSIFICACAO_COR", "")).strip(),
        qtd_classificacoes_cor=_to_int(
            record.get("QTD_CLASSIFICACOES_COR"), "QTD_CLASSIFICACOES_COR", contexto
        ),
        status=_to_int(record.get("STATUS"), "STATUS", contexto),
        total_pecas=_to_int(record.get("TOTAL_PECAS"), "TOTAL_PECAS", contexto),
        kilos_programados=_to_float(
            record.get("KILOS_PROGRAMADOS"), "KILOS_PROGRAMADOS", contexto
        ),
        obmontada=str(record.get("OBMONTADA", "")).strip(),
        # Opcionais (cadeia LEFT JOIN ate PEDIDOCOMERCIAL/PESSOASFJ): OB sem
        # pedido comercial associado permanece na lista com os tres nulos.
        dt_entrega=(
            None
            if record.get("DT_ENTREGA") is None
            else str(record.get("DT_ENTREGA")).strip()
        ),
        id_cliente=(
            None
            if record.get("ID_CLIENTE") is None
            else _to_int(record.get("ID_CLIENTE"), "ID_CLIENTE", contexto)
        ),
        nome_cliente=(
            None
            if record.get("NOME_CLIENTE") is None
            else str(record.get("NOME_CLIENTE")).strip() or None
        ),
    )

    descricao_esperada = CLASSIFICACOES_BRANCO.get(ob.codigo_classificacao_cor)
    if descricao_esperada is None:
        raise DadoIncompletoError(
            f"{contexto}: CD_CLASSIFICACAO_COR={ob.codigo_classificacao_cor}, "
            "esperado 6 (BRANCO) ou 9 (BRANCO 2 FIBRAS)"
        )
    if ob.descricao_classificacao_cor.upper() != descricao_esperada:
        raise DadoIncompletoError(
            f"{contexto}: classificação {ob.codigo_classificacao_cor} descrita como "
            f"{ob.descricao_classificacao_cor!r}, esperado {descricao_esperada!r}"
        )
    if ob.qtd_classificacoes_cor != 1:
        raise DadoIncompletoError(
            f"{contexto}: QTD_CLASSIFICACOES_COR={ob.qtd_classificacoes_cor}, "
            "esperado exatamente 1"
        )
    if ob.status != STATUS_EMITIDA:
        raise DadoIncompletoError(
            f"{contexto}: STATUS={ob.status}, esperado {STATUS_EMITIDA} (emitida)"
        )
    if ob.obmontada != OBMONTADA_PENDENTE:
        raise DadoIncompletoError(
            f"{contexto}: OBMONTADA={ob.obmontada!r}, esperado {OBMONTADA_PENDENTE!r}"
        )
    if ob.total_pecas <= 0:
        raise DadoIncompletoError(
            f"{contexto}: TOTAL_PECAS={ob.total_pecas} — sem necessidade a atender"
        )
    return ob


def validate_ob_query(
    columns: Sequence[str], rows: Sequence[dict[str, Any]]
) -> RelatorioValidacao:
    """Valida o retorno da query de OBs: schema, dominios e amostra.

    Nao levanta: retorna o relatorio para que a simulacao mostre TODOS os
    problemas de uma vez, em vez de parar no primeiro.
    """
    relatorio = RelatorioValidacao(total=len(rows))

    faltando = [c for c in COLUNAS_OB_OBRIGATORIAS if c not in columns]
    if faltando:
        relatorio.schema_ok = False
        relatorio.falhar(f"Colunas obrigatorias ausentes: {', '.join(faltando)}")
        return relatorio  # schema quebrado: nenhuma linha e confiavel

    for record in rows:
        try:
            relatorio.obs.append(coerce_ob_row(record))
        except DadoIncompletoError as exc:
            relatorio.falhar(str(exc))

    relatorio.amostra = [dict(r) for r in rows[:TAMANHO_AMOSTRA]]
    return relatorio


def validate_finalidades_query(
    classificacoes: Sequence[int], rows: Sequence[Mapping[str, Any]]
) -> dict[int, str]:
    """Resolve as finalidades de peça compatíveis com as classificações alvo.

    Recebe o retorno de SQL-FinalidadesCompativeis.sql e devolve
    ``{finalidade: descricao}``. Todas as classificações pedidas precisam ter
    ao menos uma finalidade cadastrada e — enquanto o alvo forem 6 e 9 — os
    conjuntos precisam COINCIDIR: a consulta de estoque é agregada por reduzido
    e não sabe a classificação da OB, então um conjunto por classe tornaria o
    saldo ambíguo. Divergência é falha observável, não degradação silenciosa
    (guardrail do CONTEXT.md: mudança nas classes 6/9 exige nova confrontação).
    """
    if not classificacoes:
        raise SchemaInvalidoError("nenhuma classificacao alvo informada")

    faltando_colunas = [
        c for c in COLUNAS_FINALIDADES_OBRIGATORIAS if rows and c not in rows[0]
    ]
    if faltando_colunas:
        raise SchemaInvalidoError(
            f"Query de finalidades sem as colunas: {', '.join(faltando_colunas)}"
        )

    por_classe: dict[int, dict[int, str]] = {int(c): {} for c in classificacoes}
    for record in rows:
        classe = _to_int(
            record.get("CODCLASSIFICACAO_COR"), "CODCLASSIFICACAO_COR", "finalidades"
        )
        if classe not in por_classe:
            continue
        finalidade = _to_int(
            record.get("CODFINALIDADE"), "CODFINALIDADE", f"classificacao {classe}"
        )
        descricao = str(record.get("DESCRICAO_FINALIDADE") or "").strip()
        if not descricao:
            raise DadoIncompletoError(
                f"finalidade {finalidade} da classificacao {classe} sem descricao "
                f"em TIPO_FINALIDADE_FIO"
            )
        por_classe[classe][finalidade] = descricao

    vazias = sorted(c for c, m in por_classe.items() if not m)
    if vazias:
        raise DadoIncompletoError(
            "COR_FINALIDADE nao tem finalidade cadastrada para a(s) "
            f"classificacao(oes) {', '.join(str(c) for c in vazias)}"
        )

    conjuntos = {c: frozenset(m) for c, m in por_classe.items()}
    if len(set(conjuntos.values())) > 1:
        detalhe = "; ".join(f"{c}={sorted(conjuntos[c])}" for c in sorted(conjuntos))
        raise DadoIncompletoError(
            "classificacoes brancas com conjuntos de finalidade divergentes "
            f"({detalhe}) — o saldo por reduzido ficaria ambiguo"
        )

    resolvido: dict[int, str] = {}
    for mapa in por_classe.values():
        resolvido.update(mapa)
    return dict(sorted(resolvido.items()))


def validate_estoque_rows(  # pylint: disable=too-many-locals
    records: Sequence[Mapping[str, Any]], descricoes: Mapping[int, str]
) -> EstoqueDeposito:
    """Consolida as linhas do GROUPING SETS de UM reduzido em um EstoqueDeposito.

    A linha com ``EH_TOTAL = 1`` é o saldo autoritativo (COUNT DISTINCT sobre a
    união das finalidades); as demais são o detalhamento por finalidade.

    SchemaInvalidoError = contrato da query quebrado (aborta o lote).
    DadoIncompletoError = valor ruim numa linha (pula o codigo).
    """
    if not records:
        raise SchemaInvalidoError("validate_estoque_rows exige ao menos uma linha")

    faltando = [c for c in COLUNAS_ESTOQUE_OBRIGATORIAS if c not in records[0]]
    if faltando:
        raise SchemaInvalidoError(
            f"Query de estoque sem as colunas: {', '.join(faltando)}"
        )

    codigo = _to_int(
        records[0].get("CODIGO_REDUZIDO_PROD"), "CODIGO_REDUZIDO_PROD", "estoque"
    )
    contexto = f"estoque peca {codigo}"

    total: tuple[int, int] | None = None
    parciais: list[tuple[int, str, int]] = []
    for record in records:
        quantidade = _to_int(
            record.get("QTD_PECAS_DISPONIVEIS"), "QTD_PECAS_DISPONIVEIS", contexto
        )
        brutas = _to_int(record.get("QTD_LINHAS_BRUTAS"), "QTD_LINHAS_BRUTAS", contexto)
        if quantidade < 0 or brutas < 0:
            raise DadoIncompletoError(
                f"{contexto}: contagem negativa e impossivel "
                f"(distintas={quantidade}, brutas={brutas})"
            )
        if _to_int(record.get("EH_TOTAL"), "EH_TOTAL", contexto) == 1:
            if total is not None:
                raise DadoIncompletoError(
                    f"{contexto}: mais de uma linha total no GROUPING SETS"
                )
            total = (quantidade, brutas)
            continue
        finalidade = _to_int(record.get("FINALIDADE"), "FINALIDADE", contexto)
        descricao = descricoes.get(finalidade)
        if descricao is None:
            # Finalidade fora do conjunto pedido por bind: so' acontece se a
            # query e o mapa de descricoes sairem de conjuntos diferentes.
            raise DadoIncompletoError(
                f"{contexto}: finalidade {finalidade} retornada mas nao consta "
                f"entre as compativeis com as classificacoes brancas"
            )
        parciais.append((finalidade, descricao, quantidade))

    if total is None:
        raise DadoIncompletoError(
            f"{contexto}: GROUPING SETS nao devolveu a linha total"
        )

    quantidade_total, linhas_brutas = total
    maior_parcial = max((q for _, _, q in parciais), default=0)
    soma_parciais = sum(q for _, _, q in parciais)
    # Coerencia entre a linha total e as parciais do mesmo GROUP BY: o total e'
    # COUNT DISTINCT sobre a uniao, entao fica entre a maior parcial e a soma
    # delas. Violacao = query alterada de forma que quebra a relacao — falha
    # observavel em vez de saldo silenciosamente errado.
    if quantidade_total < maior_parcial:
        raise DadoIncompletoError(
            f"{contexto}: saldo total {quantidade_total} menor que a maior "
            f"contagem por finalidade ({maior_parcial})"
        )
    if quantidade_total > soma_parciais:
        raise DadoIncompletoError(
            f"{contexto}: saldo total {quantidade_total} maior que a soma das "
            f"finalidades ({soma_parciais})"
        )

    return EstoqueDeposito(
        codigo_reduzido=codigo,
        quantidade=quantidade_total,
        linhas_brutas=linhas_brutas,
        por_finalidade=tuple(sorted(parciais)),
    )


def validate_estoque_query(
    codigo_reduzido: int,
    rows: Sequence[dict[str, Any]],
    descricoes: Mapping[int, str] | None = None,
) -> dict[str, Any]:
    """Simula a consulta de estoque de UM codigo e devolve o veredito.

    Ausencia de linha e resultado valido: significa zero pecas no deposito 95
    (o GROUP BY simplesmente nao emite linha para o codigo).

    Retorna {codigo, quantidade, validado, fan_out, restricoes, motivo}.
    """
    correspondentes = [
        r
        for r in rows
        if str(r.get("CODIGO_REDUZIDO_PROD", "")).strip() == str(codigo_reduzido)
    ]
    if not correspondentes:
        return {
            "codigo": codigo_reduzido,
            "quantidade": 0,
            "validado": True,
            "fan_out": False,
            "restricoes": [],
            "motivo": "sem linha no retorno — zero pecas no deposito 95",
        }

    try:
        estoque = validate_estoque_rows(correspondentes, descricoes or {})
    except (SchemaInvalidoError, DadoIncompletoError) as exc:
        return {
            "codigo": codigo_reduzido,
            "quantidade": 0,
            "validado": False,
            "fan_out": False,
            "restricoes": [],
            "motivo": str(exc),
        }

    return {
        "codigo": estoque.codigo_reduzido,
        "quantidade": estoque.quantidade,
        "validado": True,
        "fan_out": estoque.tem_fan_out,
        "restricoes": [
            {"codigo": codigo, "descricao": descricao}
            for codigo, descricao in estoque.restricoes_disponiveis
        ],
        "motivo": (
            f"fan-out de join: {estoque.linhas_brutas} linhas brutas para "
            f"{estoque.quantidade} pecas distintas"
            if estoque.tem_fan_out
            else "ok"
        ),
    }


def validate_comparison_logic(ob_total: int, estoque_count: int) -> bool:
    """O estoque restrito cobre a OB INTEIRA?

    Deixou de ser a regra de notificacao em 01/09/2026 (ver
    `validate_partial_logic`) e passou a ser a regra de PRIORIDADE: quem fecha
    100% aloca antes, na primeira passada de `alocar_estoque`.

    Fonte unica da comparacao — a simulacao e a producao chamam esta mesma
    funcao, entao o que Gabriel valida na Fase 1 e literalmente o que roda
    depois em producao.
    """
    return estoque_count >= ob_total


def validate_partial_logic(estoque_count: int) -> bool:
    """Regra de decisao: vale anunciar a OB com o saldo restrito que existe?

    Basta UMA peca (`MINIMO_PECAS_NOTIFICAVEL`). A Montagem de Lotes nao pode
    montar a OB so' com peca sem restricao e deixar as restritas para tras: a
    peca restrita e a que precisa ser escoada, entao qualquer saldo aproveitavel
    justifica o aviso — a OB e completada com material sem restricao.
    """
    return estoque_count >= MINIMO_PECAS_NOTIFICAVEL


def chave_prioridade(ob: ObRestricaoBranco) -> tuple[bool, bool, str, int]:
    """Chave de ordenacao de negocio — FONTE UNICA de `priorizar_obs` e `dedupe_obs`.

    Lojas antes da matriz; dentro de cada grupo, por data de entrega ascendente,
    com OB sem data por ultimo; desempate final por NUMERO_OB para tornar a
    ordem deterministica. dt_entrega e isoformat, entao a comparacao
    lexicografica equivale a cronologica.

    Existe como funcao nomeada porque as duas eram chaves DIFERENTES: o dedupe
    ordenava so' por (sem_data, data) e, quando as linhas duplicadas divergiam
    em id_cliente, ele podia manter a linha da MATRIZ e rebaixar uma OB de loja
    — decidindo antes, e a prioridade herdava a escolha errada.
    """
    return (
        ob.id_cliente == ID_CLIENTE_MATRIZ,
        ob.dt_entrega is None,
        ob.dt_entrega or "",
        ob.id_ob,
    )


@dataclass(frozen=True)
class DivergenciaDuplicata:
    """Duplicata cujas linhas discordam nos campos de pedido comercial."""

    id_ob: int
    campos: tuple[str, ...]
    mantida: str
    descartada: str


def _rotulo_linha(ob: ObRestricaoBranco) -> str:
    return (
        f"cliente={ob.id_cliente} ({ob.nome_cliente or '—'}), "
        f"entrega={ob.dt_entrega or '—'}"
    )


def _campos_divergentes(a: ObRestricaoBranco, b: ObRestricaoBranco) -> tuple[str, ...]:
    return tuple(
        campo
        for campo, valores in (
            ("id_cliente", (a.id_cliente, b.id_cliente)),
            ("nome_cliente", (a.nome_cliente, b.nome_cliente)),
            ("dt_entrega", (a.dt_entrega, b.dt_entrega)),
        )
        if valores[0] != valores[1]
    )


def dedupe_obs(
    obs: Sequence[ObRestricaoBranco],
) -> tuple[list[ObRestricaoBranco], list[int], list[DivergenciaDuplicata]]:
    """Remove linhas duplicadas por NUMERO_OB (fan-out do LEFT JOIN de pedido comercial).

    A query projeta DT_ENTREGA/ID_CLIENTE/NOME_CLIENTE dos joins de pedido
    comercial (ver SQL-ObsRestricaoBranco.sql) — uma OB ligada a mais de um
    pedido gera uma linha por pedido, e essas linhas PODEM divergir nesses
    campos. `serialize_rows` so ordena por NUMERO_OB (extract_orb.py), entao a
    ordem entre duplicatas nao e garantida: mantemos a linha de MAIOR prioridade
    de negocio, pela mesma `chave_prioridade` que `priorizar_obs` usa, em vez da
    primeira do cursor.

    Retorna (unicas, ids_duplicados, divergencias). A terceira lista existe
    porque o caso divergente nunca ocorreu em producao: e o log dela que vai
    revelar a frequencia real.
    """
    por_ob: dict[int, ObRestricaoBranco] = {}
    duplicados: list[int] = []
    divergencias: list[DivergenciaDuplicata] = []
    for ob in obs:
        atual = por_ob.get(ob.id_ob)
        if atual is None:
            por_ob[ob.id_ob] = ob
            continue
        duplicados.append(ob.id_ob)
        vencedora, perdedora = (
            (ob, atual)
            if chave_prioridade(ob) < chave_prioridade(atual)
            else (atual, ob)
        )
        por_ob[ob.id_ob] = vencedora
        campos = _campos_divergentes(atual, ob)
        if campos:
            divergencias.append(
                DivergenciaDuplicata(
                    id_ob=ob.id_ob,
                    campos=campos,
                    mantida=_rotulo_linha(vencedora),
                    descartada=_rotulo_linha(perdedora),
                )
            )
    return list(por_ob.values()), duplicados, divergencias


def _instante(valor: str) -> datetime | None:
    """isoformat -> datetime, ou None quando o carimbo nao e legivel."""
    try:
        return datetime.fromisoformat(valor)
    except (TypeError, ValueError):
        return None


def parse_notified_state(bruto: Any) -> dict[str, ReservaNotificacao]:
    """Le o `notified` do disco nos DOIS formatos, sem nunca levantar.

    Formato atual: ``{"185719": {"em": iso, "reduzido": 26, "reservado": 55}}``.
    Formato legado (produção antes desta versão): ``{"185719": iso}`` — vira
    reserva de quantidade DESCONHECIDA, registrada como 0. A escolha e
    deliberada: preserva a idempotencia (a OB nao e re-avisada ao grupo) sem
    inventar um saldo reservado que o arquivo antigo nao registrou. A entrada
    legada se converte sozinha no ciclo seguinte ao vencimento da janela, quando
    a OB volta a concorrer e e reservada com a quantidade real.
    """
    estado: dict[str, ReservaNotificacao] = {}
    for id_ob, valor in bruto.items():
        chave = str(id_ob)
        if isinstance(valor, Mapping):
            try:
                reduzido = valor.get("reduzido")
                estado[chave] = ReservaNotificacao(
                    em=str(valor.get("em", "")),
                    codigo_reduzido=None if reduzido is None else int(reduzido),
                    quantidade=max(int(valor.get("reservado") or 0), 0),
                    # Ausente nas entradas anteriores a 02/09/2026: a OB segue
                    # idempotente e reservando o restrito, apenas sem reservar
                    # complemento — que era o comportamento vigente quando
                    # aquela entrada foi escrita.
                    complemento=max(int(valor.get("complemento") or 0), 0),
                )
                continue
            except (TypeError, ValueError):
                # Entrada malformada: degrada para reserva desconhecida em vez de
                # sumir do state, que re-avisaria a OB ao grupo.
                pass
            estado[chave] = ReservaNotificacao(
                em=str(valor.get("em", "")), codigo_reduzido=None, quantidade=0
            )
            continue
        estado[chave] = ReservaNotificacao(
            em=str(valor), codigo_reduzido=None, quantidade=0
        )
    return estado


def serialize_notified_state(
    estado: Mapping[str, ReservaNotificacao],
) -> dict[str, dict[str, Any]]:
    """Forma serializavel do state — inversa de `parse_notified_state`."""
    return {
        id_ob: {
            "em": reserva.em,
            "reduzido": reserva.codigo_reduzido,
            "reservado": reserva.quantidade,
            "complemento": reserva.complemento,
        }
        for id_ob, reserva in estado.items()
    }


def reservas_vivas(
    estado: Mapping[str, ReservaNotificacao], agora: str
) -> dict[str, ReservaNotificacao]:
    """Descarta as reservas vencidas (> JANELA_RESERVA_HORAS antes de `agora`).

    Quem sai daqui sai do `notified` inteiro: a OB volta a concorrer pelo
    estoque no ciclo atual e pode ser re-anunciada se vencer de novo. Carimbo
    ilegivel (ou `agora` ilegivel) NAO expira — na duvida, preservar a
    idempotencia e melhor do que arriscar um aviso duplicado ao grupo; a poda
    por ausencia na query continua removendo a OB quando ela for montada.
    """
    referencia = _instante(agora)
    if referencia is None:
        return dict(estado)
    limite = referencia - timedelta(hours=JANELA_RESERVA_HORAS)
    vivas: dict[str, ReservaNotificacao] = {}
    for id_ob, reserva in estado.items():
        em = _instante(reserva.em)
        if em is not None and em < limite:
            continue
        vivas[id_ob] = reserva
    return vivas


def reservas_por_reduzido(estado: Mapping[str, ReservaNotificacao]) -> dict[int, int]:
    """Soma, por codigo reduzido, o estoque preso por OBs ja anunciadas."""
    total: dict[int, int] = {}
    for reserva in estado.values():
        if reserva.codigo_reduzido is None or reserva.quantidade <= 0:
            continue
        total[reserva.codigo_reduzido] = (
            total.get(reserva.codigo_reduzido, 0) + reserva.quantidade
        )
    return total


def reservas_complemento_por_reduzido(
    estado: Mapping[str, ReservaNotificacao],
) -> dict[int, int]:
    """Soma, por reduzido, o saldo SEM RESTRICAO preso por OBs ja anunciadas.

    Irma de `reservas_por_reduzido`, para o outro pote. Uma OB parcial anunciada
    vai consumir esse complemento quando for montada; sem descontar, a OB
    seguinte do mesmo reduzido seria aprovada contando com peca ja prometida.
    Entradas de state anteriores a 02/09/2026 tem `complemento=0` e nao
    reservam nada — mesma degradacao consciente do formato legado.
    """
    total: dict[int, int] = {}
    for reserva in estado.values():
        if reserva.codigo_reduzido is None or reserva.complemento <= 0:
            continue
        total[reserva.codigo_reduzido] = (
            total.get(reserva.codigo_reduzido, 0) + reserva.complemento
        )
    return total


def merge_notified_state(
    previamente: Mapping[str, ReservaNotificacao],
    avaliacoes: Sequence[AvaliacaoOb],
    novas: Sequence[AvaliacaoOb],
    agora: str,
) -> dict[str, ReservaNotificacao]:
    """Proximo conteudo do state de idempotencia (`notified`).

    Poda por presenca na QUERY, nunca por notificabilidade: OB montada sai da
    query e portanto do state (se voltar a ficar pendente, avisa de novo) — e e
    assim que a reserva termina no caso normal, sem depender da validade; OB
    ja avisada cujo estoque apenas oscilou para baixo PERMANECE no state, para
    nao re-avisar a cada cruzamento do limiar entre execucoes agendadas.

    Recebe `previamente` JA podado por `reservas_vivas` — a expiracao acontece
    num lugar so', antes da alocacao, para que a OB expirada concorra pelo
    estoque no mesmo ciclo em que a reserva dela e liberada.
    """
    ids_na_query = {str(a.ob.id_ob) for a in avaliacoes}
    estado = {k: v for k, v in previamente.items() if k in ids_na_query}
    estado.update(
        {
            str(a.ob.id_ob): ReservaNotificacao(
                em=agora,
                codigo_reduzido=a.ob.codigo_reduzido_cru,
                # O que a OB de fato segura, nao o que ela precisa: numa
                # cobertura parcial, reservar `total_pecas` tiraria do pote
                # pecas que o deposito nunca teve.
                quantidade=a.alocado,
                complemento=a.complemento_alocado,
            )
            for a in novas
        }
    )
    return estado


def priorizar_obs(obs: Sequence[ObRestricaoBranco]) -> list[ObRestricaoBranco]:
    """Ordena as OBs pela prioridade de negocio: lojas antes da matriz.

    OBs de lojas (id_cliente != ID_CLIENTE_MATRIZ) sao onde a malha e de fato
    vendida — vem primeiro, por data de entrega ascendente. OBs da matriz
    (CR-MATRIZ/PR, o deposito de malhas) vao para o fim da lista, tambem
    ordenadas por data de entrega entre si. A regra inteira vive em
    `chave_prioridade`, compartilhada com `dedupe_obs`.
    """
    return sorted(obs, key=chave_prioridade)


def alocar_estoque(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    # Os seis parametros sao os dois potes de estoque (restrito e complemento),
    # cada um com o seu mapa de reservas vivas, mais as OBs e o indice de OBs ja
    # anunciadas. Agrupa-los num objeto seria abstracao de uso unico: nenhum
    # outro ponto do dominio precisa desse agregado, e o wrapper so' esconderia
    # a simetria entre os dois potes, que e' justamente o que torna a funcao
    # legivel.
    obs: Sequence[ObRestricaoBranco],
    estoques: Mapping[int, EstoqueDeposito],
    reservado: Mapping[int, int] | None = None,
    ja_reservadas: Mapping[str, ReservaNotificacao] | None = None,
    complementos: Mapping[int, EstoqueDeposito] | None = None,
    reservado_complemento: Mapping[int, int] | None = None,
) -> list[AvaliacaoOb]:
    """Aloca o estoque do deposito 95 em duas passadas sobre a fila priorizada.

    O estoque e por produto (codigo reduzido) e as OBs concorrem por ele,
    mantendo um saldo por codigo. Desde 01/09/2026 a cobertura INTEGRAL deixou
    de ser condicao para notificar e virou condicao de PRIORIDADE:

    - passada 1: na ordem de `priorizar_obs`, as OBs que o saldo cobre por
      inteiro alocam `total_pecas`;
    - passada 2: as demais, na mesma ordem, levam todo o saldo que restou do
      seu reduzido (>= `MINIMO_PECAS_NOTIFICAVEL`) e sao anunciadas como
      cobertura parcial — desde que exista COMPLEMENTO sem restricao para
      fechar o lote (`complementos`, finalidades 1 e 8). Sem complemento
      suficiente a OB nao e anunciada: a Montagem nao conseguiria montar o
      lote, entao o aviso seria ruido, e as pecas restritas ficam livres para
      a proxima OB do mesmo reduzido (regra de 02/09/2026).

    `reservado_complemento` faz pelo pote sem restricao o que `reservado` faz
    pelo restrito: desconta o que OBs anunciadas em ciclos anteriores ainda
    seguram. A reserva da OFST-06 (que consome finalidade 1 do mesmo deposito)
    NAO e considerada — risco conhecido e aceito, ver CONTEXT.md.

    A ordem de retorno e a de entrada (prioridade), nao a de alocacao.
    `alocado` e o que a OB reservou; `disponivel` registra o saldo no momento
    da avaliacao daquela OB, nao o estoque bruto do deposito.

    `reservado` (ver reservas_por_reduzido) desconta o que OBs anunciadas em
    ciclos ANTERIORES ainda seguram: sem isso a deducao valia so' dentro de um
    ciclo e o saldo voltava inteiro ao pote na execucao seguinte, anunciando
    duas OBs para as mesmas pecas fisicas.

    `ja_reservadas` (as chaves de `reservas_vivas`, tipicamente `vivas`) e o
    conjunto de OBs cuja quantidade JA esta descontada em `saldos` via
    `reservado` — para elas o loop abaixo pula a deducao, senao a mesma
    reserva sai do saldo duas vezes (uma em `presos`, outra no loop) e
    OBs novas legitimas ficam de fora por um saldo menor do que o real.
    Essas OBs continuam em `avaliacoes` (precisam continuar, para
    `merge_notified_state` nao as podar do state por ausencia).

    Pular a deducao acima so' vale quando a reserva tem quantidade REAL
    conhecida (> 0) — e' essa quantidade que `reservas_por_reduzido` soma em
    `presos`. Uma reserva degradada (formato legado ou entrada malformada em
    `parse_notified_state`, `quantidade=0`/`codigo_reduzido=None`) NAO entra em
    `presos` — pular a deducao aqui tambem a deixaria sem desconto em lugar
    nenhum, e uma OB nova do mesmo reduzido veria o saldo bruto e seria
    aprovada para as mesmas pecas fisicas. Para essa reserva a OB compete
    normalmente pelo saldo atual, como uma OB nunca notificada.
    """
    presos = reservado or {}
    ja_reservadas = ja_reservadas or {}
    presos_complemento = reservado_complemento or {}
    saldos: dict[int, int] = {
        codigo: max(estoque.quantidade - presos.get(codigo, 0), 0)
        for codigo, estoque in estoques.items()
    }
    livres: dict[int, int] = {
        codigo: max(estoque.quantidade - presos_complemento.get(codigo, 0), 0)
        for codigo, estoque in (complementos or {}).items()
    }

    def montar(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        ob: ObRestricaoBranco,
        saldo: int,
        notificar: bool,
        alocado: int,
        motivo: str,
        complemento_alocado: int = 0,
    ) -> AvaliacaoOb:
        estoque = estoques.get(ob.codigo_reduzido_cru)
        return AvaliacaoOb(
            ob=ob,
            disponivel=saldo,
            notificar=notificar,
            motivo=motivo,
            restricoes_disponiveis=(
                estoque.restricoes_disponiveis if estoque is not None else ()
            ),
            alocado=alocado,
            complemento_alocado=complemento_alocado,
        )

    avaliadas: dict[int, AvaliacaoOb] = {}
    pendentes: list[tuple[int, ObRestricaoBranco]] = []

    # Passada 0 — OBs ja anunciadas: a quantidade delas ja saiu do saldo via
    # `presos`, entao nao concorrem de novo. `reserva_viva.quantidade` e o que
    # foi alocado no anuncio original (pode ser parcial).
    for indice, ob in enumerate(obs):
        reserva_viva = ja_reservadas.get(str(ob.id_ob))
        if reserva_viva is not None and reserva_viva.quantidade > 0:
            avaliadas[indice] = montar(
                ob,
                saldos.get(ob.codigo_reduzido_cru, 0),
                notificar=True,
                alocado=reserva_viva.quantidade,
                complemento_alocado=reserva_viva.complemento,
                motivo=(
                    f"ja reservada em ciclo anterior: {reserva_viva.quantidade} un do "
                    f"deposito {DEPOSITO_ALVO} ja descontadas via reserva viva"
                    + (
                        f" (+ {reserva_viva.complemento} un sem restricao)"
                        if reserva_viva.complemento
                        else ""
                    )
                ),
            )
        else:
            pendentes.append((indice, ob))

    # Passada 1 — cobertura integral primeiro. Dentro da fila ja priorizada
    # (lojas -> data de entrega), quem fecha 100% aloca antes: o saldo escoa do
    # mesmo jeito nas duas ordens, mas assim ele fecha a OB que pode ser montada
    # so' com peca restrita em vez de ficar espalhado em varias parciais.
    parciais: list[tuple[int, ObRestricaoBranco]] = []
    for indice, ob in pendentes:
        saldo = saldos.get(ob.codigo_reduzido_cru, 0)
        if not validate_comparison_logic(ob.total_pecas, saldo):
            parciais.append((indice, ob))
            continue
        saldos[ob.codigo_reduzido_cru] = saldo - ob.total_pecas
        avaliadas[indice] = montar(
            ob,
            saldo,
            notificar=True,
            alocado=ob.total_pecas,
            motivo=(
                f"estoque alocado: precisa {ob.total_pecas} un, saldo livre do "
                f"deposito {DEPOSITO_ALVO} era {saldo} un "
                f"(restam {saldo - ob.total_pecas} un)"
            ),
        )

    # Passada 2 — o que sobrou vai para as parciais, na mesma ordem de
    # prioridade. Cada uma leva TODO o saldo restante do seu reduzido: a OB e
    # completada com peca sem restricao, e uma peca restrita guardada para a
    # proxima OB e uma peca deixada para tras.
    for indice, ob in parciais:
        saldo = saldos.get(ob.codigo_reduzido_cru, 0)
        if not validate_partial_logic(saldo):
            avaliadas[indice] = montar(
                ob,
                saldo,
                notificar=False,
                alocado=0,
                motivo=(
                    f"sem peca restrita disponivel: precisa {ob.total_pecas} un e "
                    f"o saldo livre restante do deposito {DEPOSITO_ALVO} e zero"
                ),
            )
            continue

        faltante = ob.total_pecas - saldo
        livre = livres.get(ob.codigo_reduzido_cru, 0)
        if livre < faltante:
            # A OB tem peca restrita, mas o lote nao fecha: nao anunciar, e
            # DEIXAR o saldo restrito intacto para a proxima OB do reduzido —
            # uma OB menor pode ser montavel com as mesmas pecas.
            avaliadas[indice] = montar(
                ob,
                saldo,
                notificar=False,
                alocado=0,
                motivo=(
                    f"lote nao fecha: precisa {ob.total_pecas} un, ha {saldo} un "
                    f"restritas mas so {livre} un sem restricao livres para "
                    f"completar as {faltante} un que faltam"
                ),
            )
            continue

        saldos[ob.codigo_reduzido_cru] = 0
        livres[ob.codigo_reduzido_cru] = livre - faltante
        avaliadas[indice] = montar(
            ob,
            saldo,
            notificar=True,
            alocado=saldo,
            complemento_alocado=faltante,
            motivo=(
                f"cobertura parcial: precisa {ob.total_pecas} un, alocadas as "
                f"{saldo} un livres do deposito {DEPOSITO_ALVO} + {faltante} un "
                f"sem restricao (restam {livre - faltante} un sem restricao)"
            ),
        )

    return [avaliadas[indice] for indice in range(len(obs))]
