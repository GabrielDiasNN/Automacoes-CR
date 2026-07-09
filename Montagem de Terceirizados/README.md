# Automacao - Montagem de Terceirizados (v2.0 - Pure-Native) ⚙️

[⬅️ Voltar para o Hub Central](../README.md)

## Visao Geral

Este projeto automatiza a validacao fiscal deterministica de ordens de montagem externa. O foco e garantir o cruzamento preciso entre Notas Fiscais (NF) e Ordens de Fabricacao (OBs) de terceirizados, notificando divergencias a equipe fiscal de forma proativa atraves de uma interface moderna e inteligente.

A versao 2.0 marca a migracao definitiva para a **Arquitetura Pure-Native**, eliminando totalmente as dependencias de Excel/VBA e utilizando queries SQL de alta performance otimizadas via CTEs.

## Fluxo de Execucao (Modo Nativo)

`MonitorAutomacoes.ps1` (Monitor) -> `run.ps1` (Orquestrador)
  -> **Fase 1 (Extracao)**: Executa a extracao 100% Python direta do Oracle (`extract_oracle.py`) consumindo o payload `SQL-MontagemTerceirizados.sql`.
  -> **Fase 2 (Inteligencia)**: Python valida os dados, aplica regras de negocio e gera o relatorio HTML (`validate_and_generate_html.py`).
  -> **Fase 3 (Entrega)**: PowerShell dispara o e-mail oficial via Outlook COM (Outlook-Safe).

---

## Arquitetura de Componentes

### 1. Orquestrador PowerShell (`run.ps1`)
O motor de execucao nativa:
- Gerencia o ciclo de vida sem overhead de interface grafica (Excel).
- Utiliza o **Secure File-Payload Protocol** para garantir que dados pesados nao corrompam na memoria.
- Implementa o **Base64 Bridge Protocol** para logs e e-mails PT-BR perfeitos.

### 2. Camada de Dados e Inteligencia
- **`SQL-MontagemTerceirizados.sql`**: Query ultra-otimizada utilizando CTEs (Common Table Expressions) e agregados de I/O reduzido. Substitui a dependencia da View lenta do Oracle.
- **`extract_oracle.py`**: Extrator nativo que carrega dinamicamente o SQL externo.
- **`validate_and_generate_html.py`**: Nucleo de validacao. Implementa idempotencia (cache `.cache_erros.json`), calcula a quantidade de pecas vinculadas a NF incorreta em cada OB e gera o dashboard visual com cards e destaques de erro.
- **Placa kanban no e-mail**: quando a extracao retornar `NR_KANBAN`, o HTML da notificacao passa a exibir a placa por OB nas tabelas resumida e detalhada para acelerar a triagem operacional.

---

## Operacao e Diagnostico

### Logs e Auditoria
- **Localizacao**: `Logs/Montagem_Terceirizados_...log`.
- **Rastreabilidade**: Todas as fases sao correlacionadas pelo `ExecId` unico.
- **PT-BR Blindado**: Mensagens de log em codigo-fonte sao ASCII-Safe, convertidas em tempo de execucao via Base64.

### Performance
A migracao para o modo nativo reduziu o tempo de execucao de minutos (via Excel COM) para **segundos** (via Python/cx_Oracle), eliminando falhas de interface e deadlocks de processos do Office.

---

## Regras de Negocio Criticas
1. **Idempotencia**: O sistema utiliza cache de estado para enviar alertas apenas quando surgem novos erros ou mudancas significativas.
2. **Filtros de Producao**: A automacao foca exclusivamente em OBs Montadas (Setor 5), com Destino Receita 1 e Programacao do tipo `%T`.
3. **Quantidade para Expedicao**: Os e-mails de divergencia informam quantas pecas estao ligadas a NF incorreta na montagem, permitindo retirada fisica precisa por OB.

---

## 🧠 Gestão de Contexto (AI-Native)
Este arquivo é o mapa cognitivo local do robô de Montagem de Terceirizados.
- **Obrigação**: Deve ser atualizado após mudanças nas regras fiscais de validação NF vs OB, na query SQL otimizada, no `Secure File-Payload Protocol` ou na lógica de idempotência.
- **Sincronismo**: Garante que a IA compreenda a transição Legacy -> Pure-Native e a lógica de cache de erros em JSON.
- **Objetivo**: Manter a IA ciente da arquitetura "Pure-Native" e da ausência de dependências de interface COM.
- **Atualização 17/05/2026**: A notificacao agora destaca, por OB e no resumo do e-mail, a quantidade de pecas vinculadas a NF incorreta na montagem a partir de `QT_PC_NF`.
- **Atualização 17/05/2026**: A extracao Python direta passou a usar `load_dotenv(..., override=True)` para garantir que o `.env` do repositorio prevaleca sobre variaveis stale da sessao local, alinhando a execucao manual ao contrato do Orchestrator.
- **Atualização 07/06/2026**: O e-mail de divergencias passou a expor a placa kanban (`NR_KANBAN`) por OB quando disponivel, com fallback visual `N/A` quando o Oracle nao retornar placa.
