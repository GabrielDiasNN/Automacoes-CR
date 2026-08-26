# {
#   "version": "1.0.0",
#   "description": "Dataclasses do dominio OBs Restrição Branco: OB, Estoque, Avaliacao e Resumo"
# }
"""Modelos de dominio do ORB-07.

Todos frozen: uma vez coagido e validado, o dado nao muda de forma silenciosa
entre a validacao e o envio da notificacao.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Classificacoes de cor que caracterizam uma OB branca.
CLASSIFICACOES_BRANCO_ALVO: tuple[int, ...] = (6, 9)

# Finalidades de peca que a ORB-07 pode contabilizar como estoque elegivel.
# REGRA DE NEGOCIO FIXA (confirmada em 26/08/2026): somente 3 (CORES CLARAS) e
# 4 (BRANCO). SGTPRD.COR_FINALIDADE lista para as classes 6/9 um conjunto maior
# ({1, 3, 4, 6, 8, 12, 13}), mas a finalidade 1 (SEM RESTRICAO) NAO pode entrar
# no saldo desta automacao. O cadastro segue sendo consultado para resolver as
# descricoes e para falhar de forma observavel caso 3 ou 4 deixem de ser
# compativeis com as classes brancas — nunca para ampliar o conjunto.
FINALIDADES_PECA_ALVO: tuple[int, ...] = (3, 4)


@dataclass(frozen=True)
class ObRestricaoBranco:  # pylint: disable=too-many-instance-attributes
    """Uma OB branca, emitida e não montada, já coagida e validada.

    Dataclass congelada espelhando 1:1 as colunas do contrato da query — os
    atributos sao dados, nao estado mutavel; dividir em sub-objetos so
    obscureceria o mapeamento coluna -> campo.
    """

    id_ob: int
    codigo_fluxo: int
    codigo_reduzido_cru: int
    # Texto, nao numero: ART.CDARTIGOCRU e alfanumerico no Oracle ('0A231' ocorre
    # em producao). None quando a OB nao tem cadastro em ENGEITEMESTOARTCRU
    # (LEFT JOIN no SQL). Campo puramente cosmetico — nao entra em filtro,
    # prioridade, alocacao nem idempotencia.
    codigo_artigo_cru: str | None
    codigo_cor_tingimento: str | None
    codigo_classificacao_cor: int
    descricao_classificacao_cor: str
    qtd_classificacoes_cor: int
    status: int
    total_pecas: int
    kilos_programados: float
    obmontada: str
    # Os tres campos abaixo vem da cadeia LEFT JOIN ate PEDIDOCOMERCIAL/PESSOASFJ:
    # OB sem pedido comercial associado chega com todos nulos e permanece na lista.
    # dt_entrega e isoformat (serialize_rows converte DATE -> isoformat), o que
    # torna a ordenacao lexicografica equivalente a cronologica.
    dt_entrega: str | None
    id_cliente: int | None
    nome_cliente: str | None


@dataclass(frozen=True)
class EstoqueDeposito:
    """Estoque elegível agregado por reduzido no depósito 95.

    ``quantidade`` é o saldo distinto autoritativo sobre TODAS as finalidades
    compatíveis com as classificações brancas (linha total do GROUPING SETS),
    não a soma das parciais: uma peça com mais de uma finalidade cadastrada
    seria contada duas vezes numa soma.

    ``por_finalidade`` guarda, por finalidade, ``(descrição, quantidade)`` —
    a evidência exibida na mensagem, sem voltar a dividir o saldo.
    """

    codigo_reduzido: int
    quantidade: int
    linhas_brutas: int
    por_finalidade: tuple[tuple[int, str, int], ...] = ()

    @property
    def restricoes_disponiveis(self) -> tuple[tuple[int, str], ...]:
        """Finalidades com pelo menos uma peça distinta disponível, em ordem."""
        return tuple(
            (codigo, descricao)
            for codigo, descricao, quantidade in sorted(self.por_finalidade)
            if quantidade > 0
        )

    @property
    def tem_fan_out(self) -> bool:
        """True quando os joins duplicaram linhas (COUNT bruto > COUNT distinct).

        Nao invalida `quantidade` (que ja e distinct), mas sinaliza que a query
        do spec — COUNT simples — teria superestimado o estoque.
        """
        return self.linhas_brutas > self.quantidade


@dataclass(frozen=True)
class ReservaNotificacao:
    """Estoque que uma OB já anunciada mantém reservado entre ciclos.

    A Expedição não separa as peças ao receber o aviso — a OB entra numa fila e
    é montada quando chega a vez. Sem registrar QUANTO cada OB reservou, o saldo
    voltava inteiro ao pote no ciclo seguinte e duas OBs eram anunciadas como
    prontas para as MESMAS peças físicas.

    ``codigo_reduzido``/``quantidade`` ausentes (entrada em formato legado, ver
    ``parse_notified_state``) preservam a idempotência sem reservar saldo.
    """

    em: str
    codigo_reduzido: int | None
    quantidade: int


@dataclass(frozen=True)
class AvaliacaoOb:
    """Resultado da comparacao estoque x necessidade para uma OB."""

    ob: ObRestricaoBranco
    disponivel: int
    notificar: bool
    motivo: str
    restricoes_disponiveis: tuple[tuple[int, str], ...] = ()


@dataclass
class ResumoExecucao:
    """Contadores do lote, montados incrementalmente pelo extrator."""

    total_obs: int = 0
    total_notificaveis: int = 0
    total_sem_estoque: int = 0
    falhas: list[str] = field(default_factory=list)
    tempo_consulta_ms: int = 0
