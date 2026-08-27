# {
#   "version": "1.1.0",
#   "description": "Dataclasses do dominio OBs Fluxo Sem Tingimento: OB, Estoque, Avaliacao e Resumo"
# }
"""Modelos de dominio do OFST-06.

Todos frozen: uma vez coagido e validado, o dado nao muda de forma silenciosa
entre a validacao e o envio da notificacao.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ObSemTingimento:  # pylint: disable=too-many-instance-attributes
    """Uma OB de fluxo 204 (sem tingimento) candidata a montagem, ja coagida e validada.

    Dataclass congelada espelhando 1:1 as colunas do contrato da query — os 11
    atributos sao dados, nao estado mutavel; dividir em sub-objetos so
    obscureceria o mapeamento coluna -> campo.
    """

    id_ob: int
    codigo_fluxo: int
    codigo_reduzido_cru: int
    # Texto, nao numero: ART.CDARTIGOCRU e alfanumerico no Oracle. None quando a
    # OB nao tem cadastro em ENGEITEMESTOARTCRU (LEFT JOIN no SQL). A ocorrencia
    # real ('0A231') apareceu na ORB-07, que compartilha este codigo; aqui o
    # defeito era latente so' porque a populacao de fluxo sem tingimento nao tem
    # esses artigos. Campo puramente cosmetico (uma linha da mensagem).
    codigo_artigo_cru: str | None
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
    """Estoque agregado de um codigo reduzido no deposito 95."""

    codigo_reduzido: int
    quantidade: int
    linhas_brutas: int

    @property
    def tem_fan_out(self) -> bool:
        """True quando os joins duplicaram linhas (COUNT bruto > COUNT distinct).

        Nao invalida `quantidade` (que ja e distinct), mas sinaliza que a query
        do spec — COUNT simples — teria superestimado o estoque.
        """
        return self.linhas_brutas > self.quantidade


@dataclass(frozen=True)
class AvaliacaoOb:
    """Resultado da comparacao estoque x necessidade para uma OB."""

    ob: ObSemTingimento
    disponivel: int
    notificar: bool
    motivo: str


@dataclass
class ResumoExecucao:
    """Contadores do lote, montados incrementalmente pelo extrator."""

    total_lidas: int = 0
    total_obs: int = 0
    total_notificaveis: int = 0
    total_sem_estoque: int = 0
    falhas: list[str] = field(default_factory=list)
    tempo_consulta_ms: int = 0
