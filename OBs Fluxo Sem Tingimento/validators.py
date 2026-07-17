# {
#   "version": "1.0.0",
#   "skill": "protocolo-valeg",
#   "description": "Validacoes e simulacoes de dados do OFST-06 — funcoes puras, sem I/O"
# }
"""Camada de confiabilidade do OFST-06.

Regra do modulo: **nenhuma funcao aqui abre conexao ou le arquivo**. Todas
recebem linhas ja buscadas. Quem faz I/O e `extract_ofst.py` (producao) e
`test_ofst_simulation.py` (simulacao contra Oracle real). Essa separacao e o
que permite exercitar 100% da regra de decisao sem Oracle nos testes
(Orchestrator/tests/test_ofst.py) — se as validacoes abrissem a
conexao, so seriam testaveis com o banco de pe.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from errors import DadoIncompletoError, SchemaInvalidoError
from models import AvaliacaoOb, EstoqueDeposito, ObSemTingimento

FLUXO_ESPERADO = 204
STATUS_EMITIDA = 1
OBMONTADA_PENDENTE = "0"
DEPOSITO_ALVO = 95
# PESSOASFJ.IDPESSOAFJ = 1 -> CR-MATRIZ/PR, o deposito de malhas da empresa.
# OBs desse cliente vao para o fim da lista (ver priorizar_obs).
ID_CLIENTE_MATRIZ = 1

COLUNAS_OB_OBRIGATORIAS: tuple[str, ...] = (
    "NUMERO_OB",
    "CODIGO_FLUXO",
    "CODIGO_REDUZIDO_CRU",
    "STATUS",
    "TOTAL_PECAS",
    "KILOS_PROGRAMADOS",
    "OBMONTADA",
    "CODIGO_ARTIGO_CRU",
    "DT_ENTREGA",
    "ID_CLIENTE",
    "NOME_CLIENTE",
)

COLUNAS_ESTOQUE_OBRIGATORIAS: tuple[str, ...] = (
    "CODIGO_REDUZIDO_PROD",
    "QTD_PECAS_DISPONIVEIS",
    "QTD_LINHAS_BRUTAS",
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
    total: int = 0
    amostra: list[dict[str, Any]] = field(default_factory=list)
    problemas: list[str] = field(default_factory=list)
    obs: list[ObSemTingimento] = field(default_factory=list)

    def falhar(self, motivo: str) -> None:
        self.ok = False
        self.problemas.append(motivo)


def _to_int(valor: Any, campo: str, contexto: Any) -> int:
    """Coage NUMBER do Oracle (Decimal/float/str) para int, ou levanta DadoIncompletoError."""
    if valor is None:
        raise DadoIncompletoError(f"{contexto}: campo '{campo}' esta nulo")
    try:
        return int(valor)
    except (TypeError, ValueError) as exc:
        raise DadoIncompletoError(
            f"{contexto}: campo '{campo}' nao e numerico (valor={valor!r})"
        ) from exc


def _to_float(valor: Any, campo: str, contexto: Any) -> float:
    if valor is None:
        raise DadoIncompletoError(f"{contexto}: campo '{campo}' esta nulo")
    try:
        return float(valor)
    except (TypeError, ValueError) as exc:
        raise DadoIncompletoError(
            f"{contexto}: campo '{campo}' nao e numerico (valor={valor!r})"
        ) from exc


def coerce_ob_row(record: dict[str, Any]) -> ObSemTingimento:
    """Converte uma linha crua da query de OBs em ObSemTingimento validada.

    Levanta DadoIncompletoError (escopo de uma OB — o chamador loga e pula) para
    qualquer campo nulo, nao-numerico ou fora do dominio esperado.
    """
    id_ob = record.get("NUMERO_OB")
    contexto = f"OB #{id_ob}"

    ob = ObSemTingimento(
        id_ob=_to_int(id_ob, "NUMERO_OB", contexto),
        codigo_fluxo=_to_int(record.get("CODIGO_FLUXO"), "CODIGO_FLUXO", contexto),
        codigo_reduzido_cru=_to_int(
            record.get("CODIGO_REDUZIDO_CRU"), "CODIGO_REDUZIDO_CRU", contexto
        ),
        # Opcional (LEFT JOIN no SQL): OB sem cadastro de artigo cru continua
        # notificavel — a mensagem mostra "—" no lugar do artigo.
        codigo_artigo_cru=(
            None
            if record.get("CODIGO_ARTIGO_CRU") is None
            else _to_int(record.get("CODIGO_ARTIGO_CRU"), "CODIGO_ARTIGO_CRU", contexto)
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

    if ob.codigo_fluxo != FLUXO_ESPERADO:
        raise DadoIncompletoError(
            f"{contexto}: CODIGO_FLUXO={ob.codigo_fluxo}, esperado {FLUXO_ESPERADO}"
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
        relatorio.falhar(f"Colunas obrigatorias ausentes: {', '.join(faltando)}")
        return relatorio  # schema quebrado: nenhuma linha e confiavel

    for record in rows:
        try:
            relatorio.obs.append(coerce_ob_row(record))
        except DadoIncompletoError as exc:
            relatorio.falhar(str(exc))

    relatorio.amostra = [dict(r) for r in rows[:TAMANHO_AMOSTRA]]
    return relatorio


def validate_estoque_row(record: dict[str, Any]) -> EstoqueDeposito:
    """Valida uma linha agregada da query de estoque.

    SchemaInvalidoError = contrato da query quebrado (aborta o lote).
    DadoIncompletoError = valor ruim numa linha (pula o codigo).
    """
    faltando = [c for c in COLUNAS_ESTOQUE_OBRIGATORIAS if c not in record]
    if faltando:
        raise SchemaInvalidoError(
            f"Query de estoque sem as colunas: {', '.join(faltando)}"
        )

    codigo = _to_int(
        record.get("CODIGO_REDUZIDO_PROD"), "CODIGO_REDUZIDO_PROD", "estoque"
    )
    contexto = f"estoque peca {codigo}"
    estoque = EstoqueDeposito(
        codigo_reduzido=codigo,
        quantidade=_to_int(
            record.get("QTD_PECAS_DISPONIVEIS"), "QTD_PECAS_DISPONIVEIS", contexto
        ),
        linhas_brutas=_to_int(
            record.get("QTD_LINHAS_BRUTAS"), "QTD_LINHAS_BRUTAS", contexto
        ),
    )
    if estoque.quantidade < 0:
        raise DadoIncompletoError(
            f"{contexto}: QTD_PECAS_DISPONIVEIS={estoque.quantidade} — negativo e impossivel"
        )
    return estoque


def validate_estoque_query(
    codigo_reduzido: int, rows: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    """Simula a consulta de estoque de UM codigo e devolve o veredito.

    Ausencia de linha e resultado valido: significa zero pecas no deposito 95
    (o GROUP BY simplesmente nao emite linha para o codigo).

    Retorna {codigo, quantidade, validado, fan_out, motivo}.
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
            "motivo": "sem linha no retorno — zero pecas no deposito 95",
        }

    try:
        estoque = validate_estoque_row(correspondentes[0])
    except (SchemaInvalidoError, DadoIncompletoError) as exc:
        return {
            "codigo": codigo_reduzido,
            "quantidade": 0,
            "validado": False,
            "fan_out": False,
            "motivo": str(exc),
        }

    return {
        "codigo": estoque.codigo_reduzido,
        "quantidade": estoque.quantidade,
        "validado": True,
        "fan_out": estoque.tem_fan_out,
        "motivo": (
            f"fan-out de join: {estoque.linhas_brutas} linhas brutas para "
            f"{estoque.quantidade} pecas distintas"
            if estoque.tem_fan_out
            else "ok"
        ),
    }


def validate_comparison_logic(ob_total: int, estoque_count: int) -> bool:
    """Regra de decisao: ha estoque suficiente para montar a OB?

    Fonte unica da comparacao — a simulacao e a producao chamam esta mesma
    funcao, entao o que Gabriel valida na Fase 1 e literalmente o que roda
    depois em producao.
    """
    return estoque_count >= ob_total


def dedupe_obs(
    obs: Sequence[ObSemTingimento],
) -> tuple[list[ObSemTingimento], list[int]]:
    """Remove linhas duplicadas por NUMERO_OB (fan-out residual de join).

    A query de OBs nao projeta coluna alguma dos joins de pedido comercial,
    entao uma duplicata e sempre a MESMA OB repetida — manter a primeira
    ocorrencia e seguro. Retorna (unicas, ids_duplicados) para o chamador logar.
    """
    vistos: set[int] = set()
    unicas: list[ObSemTingimento] = []
    duplicados: list[int] = []
    for ob in obs:
        if ob.id_ob in vistos:
            duplicados.append(ob.id_ob)
            continue
        vistos.add(ob.id_ob)
        unicas.append(ob)
    return unicas, duplicados


def merge_notified_state(
    previamente: dict[str, str],
    avaliacoes: Sequence[AvaliacaoOb],
    novas: Sequence[AvaliacaoOb],
    agora: str,
) -> dict[str, str]:
    """Proximo conteudo do state de idempotencia (`notified`).

    Poda por presenca na QUERY, nunca por notificabilidade: OB montada sai da
    query e portanto do state (se voltar a ficar pendente, avisa de novo); OB
    ja avisada cujo estoque apenas oscilou para baixo PERMANECE no state, para
    nao re-avisar a cada cruzamento do limiar com execucao horaria.
    """
    ids_na_query = {str(a.ob.id_ob) for a in avaliacoes}
    estado = {k: v for k, v in previamente.items() if k in ids_na_query}
    estado.update({str(a.ob.id_ob): agora for a in novas})
    return estado


def priorizar_obs(obs: Sequence[ObSemTingimento]) -> list[ObSemTingimento]:
    """Ordena as OBs pela prioridade de negocio: lojas antes da matriz.

    OBs de lojas (id_cliente != ID_CLIENTE_MATRIZ) sao onde a malha e de fato
    vendida — vem primeiro, por data de entrega ascendente. OBs da matriz
    (CR-MATRIZ/PR, o deposito de malhas) vao para o fim da lista, tambem
    ordenadas por data de entrega entre si. Dentro de cada grupo, OB sem data
    de entrega vai por ultimo; o desempate final por NUMERO_OB torna a ordem
    deterministica. dt_entrega e isoformat, entao a comparacao lexicografica
    equivale a cronologica.
    """

    def _chave(ob: ObSemTingimento) -> tuple[bool, bool, str, int]:
        return (
            ob.id_cliente == ID_CLIENTE_MATRIZ,
            ob.dt_entrega is None,
            ob.dt_entrega or "",
            ob.id_ob,
        )

    return sorted(obs, key=_chave)


def alocar_estoque(
    obs: Sequence[ObSemTingimento], estoques: Mapping[int, EstoqueDeposito]
) -> list[AvaliacaoOb]:
    """Aloca o estoque do deposito 95 sequencialmente, na ordem recebida.

    O estoque e por produto (codigo reduzido) e as OBs concorrem por ele:
    percorre as OBs na ordem de prioridade (ver priorizar_obs) mantendo um
    saldo por codigo. Uma OB so e notificavel se o saldo RESTANTE cobre a
    necessidade dela (validate_comparison_logic); ao notificar, a quantidade
    e deduzida do saldo — assim a mensagem nunca lista mais OBs do que o
    estoque fisico permite montar. `disponivel` registra o saldo no momento
    da avaliacao daquela OB, nao o estoque bruto do deposito.
    """
    saldos: dict[int, int] = {
        codigo: estoque.quantidade for codigo, estoque in estoques.items()
    }
    avaliacoes: list[AvaliacaoOb] = []
    for ob in obs:
        saldo = saldos.get(ob.codigo_reduzido_cru, 0)
        notificar = validate_comparison_logic(ob.total_pecas, saldo)
        if notificar:
            saldos[ob.codigo_reduzido_cru] = saldo - ob.total_pecas
            motivo = (
                f"estoque alocado: precisa {ob.total_pecas} un, saldo do "
                f"deposito {DEPOSITO_ALVO} era {saldo} un "
                f"(restam {saldo - ob.total_pecas} un)"
            )
        else:
            motivo = (
                f"estoque insuficiente: precisa {ob.total_pecas} un, saldo "
                f"restante do deposito {DEPOSITO_ALVO} e {saldo} un "
                f"(faltam {ob.total_pecas - saldo} un)"
            )
        avaliacoes.append(
            AvaliacaoOb(ob=ob, disponivel=saldo, notificar=notificar, motivo=motivo)
        )
    return avaliacoes
