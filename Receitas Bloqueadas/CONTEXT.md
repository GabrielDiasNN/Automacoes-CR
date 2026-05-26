# Contexto: Receitas Bloqueadas

## Objetivo de Negócio
Gerenciar o fluxo de **Receitas de Produção Retidas** no sistema Oracle por falta de insumos ou inconsistências técnicas. O foco está no acompanhamento das **Ordens de Beneficiamento (OB)**.

## Arquitetura Soberana (v2.3.2)
- **Extração:** Python com **Oracle Thick Mode** e resiliência via biblioteca `stamina` (Retry exponencial para quedas de rede ORA-00028).
- **Separação de Preocupações:** SQL isolado no arquivo `SQL-ReceitasBloqueadas.sql` para facilitar a manutenção DBA.
- **Inteligência de Estado:**
    - ✨ **Novas:** Bloqueios inéditos desde o último ciclo.
    - ⚠️ **Alteradas:** Mudança em datas críticas no sistema.
    - ✅ **Liberadas:** Receitas resolvidas pelo laboratório.
- **Idempotência Unificada (Zero Spam):**
    - **E-mail & WhatsApp:** Ambos condicionados ao hash de conteúdo gerado pelo Python. Se não houver alteração, nenhuma notificação é disparada.
    - **WhatsApp:** Motor v1.3 com **Ack Monitoring**, **Graceful Degradation** para erros de validação de contato (LID handling) e hardening de bootstrap com `protocolTimeout` maior + retentativa curta de inicialização.
- **Formatação:** Planilha Excel analítica com máscaras **PT-BR** e realce de divergências de processo.

## Operação
- **Horários:** 07:30, 10:00 e 14:00 (Segunda a Sexta).
- **Modo Teste:** Sincronizado com o Orquestrador (Dashboard). Fonte da verdade: `ORCHESTRATOR_TEST_MODE`. Fallback via `AUTOMACAO_TEST_EMAIL`.
- **Diagnóstico do Canal:** O log canônico do WhatsApp é `Logs/WhatsApp_Global.log`; `Logs/ReceitasBloqueadas.log` registra apenas a orquestração de alto nível.
- **Streaming Online:** durante a etapa WhatsApp, o detalhamento do wrapper/bridge deve aparecer online no modal de execução do Orchestrator, sem depender do fechamento do processo para ficar visível.
- **Falha Parcial de Canal:** se o e-mail concluir e o WhatsApp falhar, a execução deve fechar com erro de canal para triagem/requeue, preservando o estado parcial do e-mail.

---
*Este módulo opera sob o padrão de idempotência cruzada e resiliência de banco de dados desde Maio/2026.*

---

## 🧠 Gestão de Contexto (AI-Native) - Atualizado em 22/05/2026
- **Detecção de Alterações (v2.3.2 - 22/05/2026):** Ajuste fino na regra de inteligência de estado para marcar receitas como `MODIFIED` ("⚠ DATA ALTERADA") exclusivamente quando a data na coluna "Data Bloqueio" sofrer modificações. Mudanças na coluna "Data Última Prod." são ignoradas para este fim, alinhando a automação ao seu objetivo estratégico.
- **Obrigação:** Manter este contexto sincronizado com o arquivo `receitas_state.json` e as regras de negócio de OBs retidas.
- **Objetivo:** Permitir que a IA entenda as condições de disparo (Novas/Alteradas/Liberadas) sem gastar tokens lendo o SQL.
