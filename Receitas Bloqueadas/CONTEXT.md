# Contexto: Receitas Bloqueadas

## Objetivo de Negócio
Gerenciar o fluxo de **Receitas de Produção Retidas** no sistema Oracle por falta de insumos ou inconsistências técnicas. O foco está no acompanhamento das **Ordens de Beneficiamento (OB)**.

## Arquitetura Soberana (v2.1.1)
- **Extração:** Python com **Oracle Thick Mode** e soberania de ambiente via `python-dotenv`.
- **Inteligência de Estado:**
    - ✨ **Novas:** Bloqueios inéditos desde o último ciclo.
    - ⚠️ **Alteradas:** Mudança em datas críticas no sistema.
    - ✅ **Liberadas:** Receitas resolvidas pelo laboratório.
- **Idempotência Estrita (Zero Spam):**
    - **E-mail:** Controlado pelo `email_state.json`. Só envia se o hash do conteúdo mudar.
    - **WhatsApp:** Motor v1.3 com **Ack Monitoring**, garantindo entrega física antes do fechamento.
- **Formatação:** Planilha Excel analítica com máscaras **PT-BR** e realce de divergências de processo.

## Operação
- **Horários:** 07:30, 10:00 e 14:00 (Segunda a Sexta).
- **Modo Teste:** Redirecionamento automático via variável `AUTOMACAO_TEST_EMAIL`.

---
*Este módulo opera sob o padrão de idempotência cruzada desde Maio/2026.*
