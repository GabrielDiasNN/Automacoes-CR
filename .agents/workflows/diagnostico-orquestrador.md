# Workflow: Diagnostico e Saude do Orchestrator

Procedimento operacional para inspecao de integridade, smoke testing e recuperacao segura do motor de automacao (FastAPI + Worker + SQLite WAL).

---

## 1. Quando Executar
- Antes de reiniciar processos do Orchestrator (esta maquina roda o servico em producao).
- Quando tarefas ficarem presas em estado `running` ou `pending`.
- Apos atualizacoes de schema ou alteracoes em `Orchestrator/app/`.

---

## 2. Roteiro de Diagnostico

### Passo 1: Smoke Test da Instancia Viva (Nao Destrutivo)
Verifique se a API e o worker ja estao ativos e respondendo na porta 8000:

```powershell
.venv\Scripts\python .claude\skills\run-orchestrator\driver.py smoke
```
*Se retornar status saudavel, NAO reinicie os processos desnecessariamente.*

---

### Passo 2: Inspecao de Processos Ativos
Caso o servico nao responda, inspecione processos Python associados ao Orchestrator:

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'Orchestrator' -or $_.CommandLine -match 'uvicorn' } | Select-Object ProcessId, CommandLine
```
*Nota: Nunca use `Get-Process` no Windows PowerShell 5.1 para inspecao de linha de comando.*

---

### Passo 3: Verificacao do Banco SQLite WAL e Migracoes
Verifique a integridade do banco e certifique-se de que todas as migracoes estao aplicadas:

```powershell
cd Orchestrator && ..\.venv\Scripts\alembic current
```

---

### Passo 4: Procedimento de Recuperacao Segura (Se Necessario)
Se a instancia estiver travada ou inconsistente, utilize o script canônico de recuperacao com cleanup gracioso:

```powershell
pwsh -File Infrastructure\Recover-Orchestrator.ps1
```

E para iniciar a partir do zero:
```powershell
pwsh -File Infrastructure\Start-Orchestrator.ps1
```

---

### Passo 5: Validacao Pos-Recuperacao
Apos o inicio dos servicos, valide novamente com o smoke test:

```powershell
.venv\Scripts\python .claude\skills\run-orchestrator\driver.py smoke
```
