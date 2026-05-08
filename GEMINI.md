# Governança de Contexto: Projeto Automacoes (C:\Automacoes)

## Propósito do Contexto Local
Garantir a soberania técnica e o histórico do Hub de Automações. Este documento força a sincronização entre código e documentação para que a IA entenda o ecossistema sem re-analisar scripts Python/PowerShell repetidamente.

## Protocolo Específico do Projeto
1. **Contexto AI-Native:** Ao iniciar tarefas no Hub, leia `README.md`, `CONTEXT.md` e `SECURITY.md`.
2. **Sincronismo de Seção:** É obrigatório atualizar a seção `## 🧠 Gestão de Contexto (AI-Native)` em todos os arquivos impactados.
3. **Hierarquia Local:**
    - **`README.md`**: Visão geral e estado de excelência (v2.x.x).
    - **`CONTEXT.md`**: Regras de negócio (ex: OBs retidas, validação NF).
    - **`SECURITY.md`**: Políticas de Zero Trust e proteção de dados Costa Rica Malhas.

## O que Documentar (Automacoes)
- **Mudanças de Versão:** Incrementar versões nativas nos cabeçalhos.
- **Regras de Negócio:** Novos filtros de produção ou comportamentos do Oracle.
- **Resiliência:** Alterações em Retry (`stamina`), Idempotência ou Circuit Breakers, sempre alinhadas ao Protocolo V.A.L.E.G.

## Checklist Local
- [ ] Os arquivos `README.md`, `CONTEXT.md` e `SECURITY.md` foram revisados?
- [ ] A seção `## 🧠 Gestão de Contexto (AI-Native)` está atualizada?
- [ ] O contexto permite economia de tokens na próxima interação?
- [ ] Tom técnico PT-BR foi mantido?
