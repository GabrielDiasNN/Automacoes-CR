---
description: Execução ponta a ponta da rotina de versionamento e entrega: criar branch descritiva, commit atômico em PT-BR, abrir PR, acompanhar o CI em tempo real, corrigir eventuais falhas, realizar o merge (squash) e remover a branch.
---

# Workflow: Ciclo Completo de PR (Branch → Commit → PR → CI → Merge → Cleanup)

Este workflow formaliza o padrão operacional de ponta a ponta para criação, validação, publicação e encerramento de Pull Requests no Hub de Automações, aplicando as diretrizes das skills `git-ide-governance-skill` e `ai-engineering-discipline`.

---

## Objetivo

Automatizar com segurança máxima o ciclo de entrega de código: isolar alterações em branch temática, garantir commits atômicos em PT-BR, submeter o PR, monitorar os testes de CI até 100% de aprovação (corrigindo eventuais regressões via feedback fechado), realizar o merge via squash e efetuar a limpeza completa da branch local e remota.

---

## Visão Geral do Ciclo Operacional

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ 1. CRIAR BRANCH │ ──► │ 2. STAGE & COMMIT│ ──► │ 3. ABRIR PR     │
│ checkout -b     │     │ Atômico em PT-BR │     │ gh pr create    │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                                                          ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ 6. CLEANUP      │ ◄── │ 5. MERGE SQUASH  │ ◄── │ 4. MONITORAR CI │
│ prune & delete  │     │ gh pr merge      │     │ schedule/checks │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

---

## Procedimento Passo a Passo

### 1. Isolamento e Criação da Branch
1. Certifique-se de que a `main` está atualizada e limpa:
   ```powershell
   git checkout main; git pull origin main
   ```
2. Crie e alterne para a branch temática descritiva com base na convenção do repositório:
   ```powershell
   git checkout -b <tipo>/<nome-descritivo>
   ```
   *Prefixos recomendados:* `fix/`, `feat/`, `refactor/`, `docs/`, `perf/`, `test/`.

### 2. Stage Seletivo e Commit Atômico
3. Valide localmente antes de comitar:
   ```powershell
   pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-SourceEncoding.ps1 -RootPath .
   ```
4. Adicione seletivamente apenas os arquivos modificados dentro do escopo da demanda:
   ```powershell
   git add <arquivo1> <arquivo2> ...
   ```
5. Realize o commit com mensagem em **Português do Brasil**, fornecendo contexto claro para auditoria:
   ```powershell
   git commit -m "<tipo>(<escopo>): <descrição clara em PT-BR> [versão/ref]"
   ```
   > [!TIP]
   > Para commits com corpo detalhado de múltiplas linhas no Windows/PowerShell, grave a mensagem em um arquivo temporário (`scratch/commit_msg.txt`) e utilize `git commit -F "scratch/commit_msg.txt"`.

### 3. Publicação e Abertura do PR
6. Envie a branch para o repositório remoto:
   ```powershell
   git push -u origin <nome-da-branch>
   ```
7. Redija a descrição do PR contendo: resumo das alterações, motivação técnica e evidências de testes.
8. Submeta o PR utilizando a GitHub CLI:
   ```powershell
   gh pr create --title "<tipo>(<escopo>): <título>" --body-file "scratch/pr_body.md" --base main --head <nome-da-branch>
   ```

### 4. Acompanhamento Reativo do CI e Auto-Correção
9. Inicie o loop de acompanhamento das checagens utilizando a ferramenta `schedule` (timers de 30s):
   ```powershell
   gh pr checks <numero-do-pr>
   ```
10. **Tratamento de Falhas (Feedback Loop)**:
    - Se qualquer check falhar (status vermelho), obtenha o log de erro:
      ```powershell
      gh run view --log-failed
      ```
    - Isole a causa raiz e aplique a **menor mudança correta** no código.
    - Revalide localmente (`pytest`, `vitest`, `ValidarAutomacoes.ps1`).
    - Adicione as alterações, faça novo commit e dê push na mesma branch.
    - O GitHub Actions reexecutará automaticamente os checks.

### 5. Merge Governado e Limpeza (Cleanup)
11. > [!IMPORTANT]
    > **Merge Bloqueado até 100% Verde:** Nunca execute o merge se houver checks de CI falhando ou pendentes.
    
    Com todos os checks aprovados (verde), realize o merge via squash:
    ```powershell
    gh pr merge <numero-do-pr> --squash --delete-branch
    ```
12. Retorne para a `main`, puxe as atualizações consolidadas e remova referências órfãs:
    ```powershell
    git checkout main; git pull origin main; git fetch --prune
    ```
13. Se a branch local ainda existir, remova-a com segurança:
    ```powershell
    git branch -d <nome-da-branch>
    ```

---

## Troubleshooting Integrado

| Cenário | Causa Provável | Solução |
|---|---|---|
| **Erro de Sintaxe no PowerShell (`&&`)** | Operador `&&` incompatível com certas versões do host Windows | Utilizar `;` para encadear comandos no PowerShell |
| **Commit Bloqueado por Hook Longo** | `ValidarAutomacoes.ps1` excedendo timeout do runtime | Executar validação prévia manualmente e usar `git commit -F` |
| **CI Pendente por Longo Período** | Suíte pesada (ex: Pytest 800+ testes ou Playwright E2E) | Utilizar `schedule` com intervalos de 20-30s sem polling agressivo |
| **Conflito de Merge no PR** | `main` avançou enquanto a branch era trabalhada | Fazer rebase/merge de `origin/main` na branch de feature antes do merge |
| **Branch Remota Remanescente** | Merge manual sem flag de exclusão | Rodar `git fetch --prune` para sincronizar as referências locais |

---

## Regras Invioláveis do Ciclo

1. **Zero Merge em CI Vermelho**: O merge na `main` requer obrigatoriamente 100% de sucesso nos checks do GitHub Actions.
2. **Commits e Docs em PT-BR**: Todas as mensagens de commit, corpos de PR e documentação viva devem manter o idioma padrão em Português do Brasil.
3. **Squash Merge Padrão**: Todo PR deve ser integrado via squash para manter o histórico da branch `main` linear e auditável.
4. **Higiene Pós-Merge**: Branches de trabalho concluídas devem ser deletadas do remoto e do local imediatamente após o merge.

---

## Checklist de Encerramento

- [ ] A branch foi criada com nomenclatura padrão e escopo delimitado?
- [ ] O commit possui mensagem atômica em PT-BR auditável?
- [ ] O PR foi aberto com corpo detalhado das alterações e evidências?
- [ ] Todos os checks do pipeline de CI foram aprovados (100% verde)?
- [ ] O merge foi realizado via squash na branch `main`?
- [ ] A branch local e remota foram removidas e `git fetch --prune` executado?
