# Governança de Contexto: Projeto Automacoes (C:\Automacoes)

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

## 🧠 Gestão de Contexto (AI-Native) - Atualizado em 09/05/2026
- **Estado:** Operacional Enterprise (v5.1.0 Estabilizado).
- **Interoperabilidade:** Implementada **B64 Bridge** para logs e suporte UTF-8/Acentos no Pydantic.
- **Governança:** Controle de **Modo Teste Global** integrado ao Dashboard.
- **Encoding:** Implementada **Trava de Regressão** (`Test-EncodingResilience.ps1`). Obrigatório manter código-fonte ASCII-Safe e I/O em UTF-8.
- **Manutenção:** Realizada faxina técnica com remoção de scripts de migração (`migrate_v4.py`) e arquivos legados.
- **Resiliência:** UI do Dashboard blindada com `try-catch` contra falhas de dados.
