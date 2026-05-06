# Contexto: Receitas Bloqueadas

## Objetivo de Negócio
Gerenciar o fluxo de **Receitas de Produção Retidas** no sistema Oracle por falta de insumos ou inconsistências técnicas. A automação garante que a equipe de planejamento (PCP) receba atualizações rápidas para renegociar prazos com a produção.

## Arquitetura Moderna (v2.1.0)
- **Extração:** Python conectado diretamente ao Oracle (`processar_receitas.py`).
- **Inteligência de Estado:** Compara o ciclo atual com o anterior (`receitas_state.json`), classificando em:
    - ✨ **Novas:** Bloqueios inéditos.
    - ⚠️ **Alteradas:** Mudança de data de última produção ou bloqueio.
    - ✅ **Liberadas:** Receitas que saíram da lista de bloqueio.
- **Formatação:** Geração de planilha Excel analítica via `openpyxl` com máscaras PT-BR e realce de divergências.
- **Entrega:** Notificação multicanal via Outlook (HTML Profissional) e WhatsApp (Node.js).

## Operação
- **Horários:** 07:30 e 14:30 (Segunda a Sexta).
- **Modo Teste:** Controlado pela variável de ambiente `AUTOMACAO_TEST_EMAIL`.

---
*Este módulo foi totalmente migrado do legado VBA em Maio/2026.*
