# Governança de Contexto: Projeto Automacoes (C:\Automacoes)

## 🛡️ Mandatos de Encoding (Soberania PT-BR)
**ESTA REGRA É ABSOLUTA E NÃO PODE SER VIOLADA:**
1. **PowerShell (.ps1, .psm1):** DEVEM ser salvos obrigatoriamente como `UTF-8 with BOM`. O PowerShell 5.1 não reconhece acentuação nativa sem o BOM, causando corrupção nos logs do Orquestrador.
2. **Outros Arquivos (.py, .txt, .json, .md, .sql):** DEVEM ser salvos como `UTF-8` (sem BOM).
3. **Validação:** Antes de qualquer `replace` ou `write_file`, verifique se o encoding resultante respeita estas regras. Se você (IA) oscilar e causar regressão de acentuação, você falhou no pilar de Governança.

## Propósito do Contexto Local
Garantir a soberania técnica e o histórico do Hub de Automações. Este documento força a sincronização entre código e documentação para que a IA entenda o ecossistema sem re-analisar scripts Python/PowerShell repetidamente.

## Protocolo Específico do Projeto
1. **Contexto AI-Native:** Ao iniciar tarefas no Hub, leia `README.md`, `CONTEXT.md` e `SECURITY.md`.
2. **Sincronismo de Seção:** É obrigatório atualizar a seção `## 🧠 Gestão de Contexto (AI-Native)` em todos os arquivos impactados.
3. **Histórico de Mudanças:** É OBRIGATÓRIO atualizar o `CHANGELOG.md` após cada commit bem-sucedido, registrando as alterações tecnicamente conforme o padrão de categorias (Adicionado, Corrigido, Removido, etc.).
4. **Hierarquia Local:**
    - **`README.md`**: Visão geral e estado de excelência (v2.x.x).
    - **`CONTEXT.md`**: Regras de negócio (ex: OBs retidas, validação NF).
    - **`SECURITY.md`**: Políticas de Zero Trust e proteção de dados Costa Rica Malhas.

## O que Documentar (Automacoes)
- **Mudanças de Versão:** Incrementar versões nativas nos cabeçalhos e registrar no `CHANGELOG.md`.
- **Regras de Negócio:** Novos filtros de produção ou comportamentos do Oracle.
- **Resiliência:** Alterações em Retry (`stamina`), Idempotência ou Circuit Breakers, sempre alinhadas ao Protocolo V.A.L.E.G.

## Checklist Local
- [x] Os arquivos `README.md`, `CONTEXT.md` e `SECURITY.md` foram revisados?
- [x] A seção `## 🧠 Gestão de Contexto (AI-Native)` está atualizada?
- [x] O contexto permite economia de tokens na próxima interação?
- [x] Tom técnico PT-BR foi mantido?
---
## 🧠 Gestão de Contexto (AI-Native) - Atualizado em 14/05/2026
- **Estado:** Estabilizado v5.6.5 (Encoding & Saneamento).
- **SQL Tuning:** Otimização profunda do script `NFFaccaoControle.sql` com consolidação de scans e hints de materialização (Pilar E).
- **Encoding:** Padronização absoluta de todos os scripts PowerShell para `UTF-8 with BOM`. Captura de processos via `StandardErrorEncoding=UTF8`.
- **Hardening:** Implementado `misfire_grace_time=60` e proteção de I/O em logs no Orquestrador para evitar omissões de disparo por instabilidade do terminal.
- **Ferramentas:** Consolidado `tools/diagnostics.py` como ferramenta oficial de saúde do Hub. Saneamento de artefatos de teste e scratch.
- **Modo Teste (Source of Truth):** Implementada injeção de `ORCHESTRATOR_TEST_MODE` via `worker.py`.
- **Telemetria:** Implementada Telemetria Nativa para execuções de terminal via prefixo `TEL_`.
- **Idempotência:** Universalização da ADR-013 (Idempotência Granular) em todo o Hub.
---
- **Resiliência:** Implementado `Scheduler Heartbeat` resiliente e telemetria de carga de jobs (v5.6.4).
- **Broadcast:** Ativada transmissão de logs em tempo real para o Dashboard.
- **Timezone:** Padronização absoluta para Horário de Brasília (BRT - America/Sao_Paulo).
- **Auditoria:** Script `Audit-DailyStatus.ps1` ativo para telemetria AI-Native.
- **Porta:** Padronização absoluta na porta 8000 para API/Watchdog.
---
