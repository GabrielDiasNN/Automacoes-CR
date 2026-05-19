# Mapa de Criticidade e SLAs de Automações

[⬅️ Voltar para o Hub Central](../README.md)

> [!NOTE]
> Este documento estabelece formalmente a classificação de criticidade, os Acordos de Nível de Serviço (SLAs) para resposta/resolução de falhas e o impacto operacional de cada robô integrado ao Hub de Automações.

---

## 🎯 Definição de Níveis de Criticidade

Classificamos nossas automações de negócio em quatro níveis com base no impacto financeiro, operacional e na experiência do cliente em caso de interrupção:

| Criticidade | Descrição | SLA de Resolução | Escalonamento Técnico |
| :--- | :--- | :--- | :--- |
| **🚨 CRÍTICA (Tier 1)** | Falha causa parada imediata da linha de produção ou bloqueio fiscal/faturamento direto. | **1 hora** | Suporte N3, Product Owner e Gerência de TI. |
| **⚠️ ALTA (Tier 2)** | Falha afeta fluxos operacionais importantes (expedição, controle de terceiros, laboratório), gerando gargalos ou atrasos em menos de 12 horas. | **3 horas** | Suporte N2, Desenvolvedor e Product Owner. |
| **💡 MÉDIA (Tier 3)** | Falha impacta relatórios de suporte ao planejamento, auditorias internas ou consultas diárias sem parada operacional. | **6 horas** | Suporte N2 e Desenvolvedor. |
| **📘 BAIXA (Tier 4)** | Rotinas semanais, arquivamentos históricos ou limpezas automáticas de logs. | **24 horas** | Suporte N1 e fila de desenvolvimento. |

---

## 🗺️ Matriz Geral de Automações do Hub

A tabela abaixo consolida a governança, cadência e prazos operacionais de todos os robôs activos no ecossistema:

| Código / ID | Automação | Criticidade | SLA de Recuperação | Cadência / Disparo | Área de Negócio Impactada | Consequência da Parada |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`RB-01`** | **[Receitas Bloqueadas](runbooks/receitas-bloqueadas-runbook.md)** | **⚠️ ALTA** | **3 horas** | Seg-Sex às 07:30, 10:00 e 14:00 | Laboratório de Receitas, PCP e Tinturaria | Atraso no tingimento de Ordens de Beneficiamento (OBs) liberadas, ociosidade em teares e perda de visibilidade de receitas retidas. |
| **`MT-02`** | **Montagem de Terceirizados** | **⚠️ ALTA** | **3 horas** | Seg-Sex às 08:00 e 15:00 | Faturamento, Controladoria e Expedição de Terceirizados | Risco de divergências fiscais na entrada de NFs de parceiros/facções, atraso na liberação de estoque de produtos acabados. |
| **`RE-03`** | **Receitas Emitidas** | **💡 MÉDIA** | **6 horas** | Seg-Sex às 17:00 | Planejamento, Tinturaria e PCP | Perda de visibilidade das receitas expedidas para a produção no dia, afetando a acurácia do planejamento produtivo do dia seguinte. |

---

## 📈 Protocolo de Escalonamento e Monitoramento de SLAs

### 1. Monitoramento Automático (Watchdog)
O script de auditoria diária `Tools/Audit-DailyStatus.ps1` e o endpoint `/api/system/diagnostics` monitoram continuamente o tempo de resposta e as falhas operacionais:
* Se uma execução com criticidade **CRÍTICA** ou **ALTA** falhar, o orquestrador tenta o autorecovery e o requeue automático (limite configurado por `max_retries`).
* Caso a falha persista após as tentativas automáticas, um alerta crítico é enviado para o canal de suporte via e-mail e WhatsApp em menos de 10 minutos.

### 2. Fluxo de Ações por Criticidade
* **Para Incidentes Tier 1 (🚨 CRÍTICO):**
  1. O operador de plantão deve ser acionado via ligação/WhatsApp.
  2. O procedimento de contingência manual ou o requeue forçado deve ser executado no painel da Control Tower.
  3. Caso o banco Oracle ou a infraestrutura do servidor esteja inoperante, o suporte de infraestrutura/DBA deve ser envolvido imediatamente.
* **Para Incidentes Tier 2 (⚠️ ALTO):**
  1. Triagem dos logs em `Logs/NomeDaAutomacao.log` e diagnóstico via `/api/system/diagnostics`.
  2. Execução das ações descritas no Runbook da automação afetada em até 1 hora.
  3. Reexecução segura (idempotente) via botão **Requeue** no Dashboard.

---

## 🧠 Gestão de Contexto (AI-Native)
* **Obrigação:** Manter este mapa atualizado sempre que uma nova automação for adicionada ao Hub ou quando as cadências e SLAs de atendimento forem repactuados com as áreas de negócio.
* **Objetivo:** Permitir que o orquestrador inteligente e os agentes priorizem automaticamente alertas de fila, ordens de execução e incidentes em conformidade com as regras de prioridade estabelecidas.
