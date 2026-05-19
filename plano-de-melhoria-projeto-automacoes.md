# Plano de Melhoria do Projeto Automações

Este documento define um plano de melhoria claro, objetivo e executável para o repositório `GabrielDiasNN/automacoes`.

O objetivo é orientar uma IA ou agente de desenvolvimento a aplicar melhorias incrementais, seguras e verificáveis, sem alterar comportamento produtivo sem validação.

---

## 1. Regras gerais para execução por IA

Antes de qualquer alteração, a IA deve seguir estas regras:

1. Ler o `README.md`, `CONTEXT.md`, `GEMINI.md`, `CHANGELOG.md` e documentos relevantes em `docs/`.
2. Preservar o padrão técnico PT-BR já adotado no projeto.
3. Fazer mudanças pequenas, rastreáveis e separadas por tema.
4. Nunca remover validações de governança para fazer o projeto passar artificialmente.
5. Nunca versionar segredos, `.env`, bancos locais, logs brutos ou artefatos pesados.
6. Após cada mudança, executar as validações disponíveis no repositório.
7. Atualizar documentação somente quando a mudança alterar arquitetura, operação, segurança, validação ou uso.
8. Usar commits semânticos, por exemplo:
   - `chore(ci): adiciona workflow de validacao`
   - `test(orchestrator): cobre regras de retry da fila`
   - `docs(quality): adiciona painel de qualidade`
   - `security(logs): mascara dados sensiveis em auditoria`

---

## 2. Diagnóstico resumido

O projeto já possui boa maturidade técnica, com:

- Dashboard SPA.
- Backend FastAPI.
- Worker operacional.
- Scheduler.
- SQLite com WAL.
- Governança Zero-Trust.
- Validações PowerShell.
- Evidência E2E com Playwright.
- Documentação técnica evolutiva.
- Commits semânticos.

Mesmo assim, há pontos que precisam ser fortalecidos:

- Reduzir risco de artefatos pesados versionados.
- Travar dependências para melhorar reprodutibilidade.
- Criar CI obrigatório.
- Medir qualidade com métricas objetivas.
- Ampliar cobertura de testes.
- Fortalecer varredura de segredos.
- Melhorar organização arquitetural conforme o projeto crescer.
- Criar runbooks operacionais por automação.

---

## 3. Fase 1 — Higiene do repositório

### Objetivo

Reduzir risco de arquivos desnecessários, artefatos pesados, logs, bancos locais e dados sensíveis dentro do Git.

### Tarefas

#### 3.1 Auditar arquivos grandes

A IA deve identificar arquivos grandes no repositório, especialmente:

- `.db`
- `.sqlite`
- `.sqlite3`
- `.log`
- `.zip`
- `.png`
- `.jpg`
- `.xlsx`
- `.csv`
- dumps
- relatórios gerados
- artefatos Playwright
- arquivos em `Logs/`

Comando sugerido em PowerShell:

```powershell
Get-ChildItem -Recurse -File |
    Sort-Object Length -Descending |
    Select-Object -First 50 FullName, Length
```

Critério de aceite:

- Listar os maiores arquivos.
- Classificar cada item como necessário ou gerado.
- Remover do versionamento apenas arquivos gerados ou sensíveis.
- Não apagar dados sem confirmar se são necessários para operação.

#### 3.2 Revisar `.gitignore`

Garantir que o `.gitignore` bloqueie pelo menos:

```gitignore
# Python
.venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.coverage
htmlcov/

# Node
node_modules/
npm-debug.log*
playwright-report/
test-results/

# Logs e runtime
Logs/
*.log
*.tmp
*.bak

# Bancos locais
*.db
*.sqlite
*.sqlite3
*.db-shm
*.db-wal

# Ambiente e segredos
.env
.env.*
!.env.example

# Artefatos
*.zip
*.7z
*.rar
artifacts/
```

Critério de aceite:

- `.gitignore` atualizado sem bloquear arquivos-fonte necessários.
- Criar `.env.example` se ainda não existir.
- Garantir que arquivos sensíveis não estejam versionados.

---

## 4. Fase 2 — Dependências reproduzíveis

### Objetivo

Evitar que instalações futuras quebrem por atualização indireta de pacotes.

### Tarefas

#### 4.1 Separar dependências por finalidade

Criar ou revisar os arquivos:

```text
requirements.in
requirements.txt
requirements-dev.in
requirements-dev.txt
requirements-test.in
requirements-test.txt
```

Separação sugerida:

- `requirements.in`: dependências de runtime.
- `requirements-dev.in`: ferramentas de desenvolvimento.
- `requirements-test.in`: ferramentas de teste.
- `requirements.txt`: dependências travadas de runtime.
- `requirements-dev.txt`: dependências travadas de desenvolvimento.
- `requirements-test.txt`: dependências travadas de teste.

#### 4.2 Travar versões

Usar `pip-tools` ou processo equivalente.

Comandos sugeridos:

```powershell
python -m pip install pip-tools
pip-compile requirements.in -o requirements.txt
pip-compile requirements-dev.in -o requirements-dev.txt
pip-compile requirements-test.in -o requirements-test.txt
```

Critério de aceite:

- Dependências de runtime separadas das dependências de desenvolvimento.
- Arquivos travados gerados.
- Instalação limpa funcionando em ambiente novo.

---

## 5. Fase 3 — CI obrigatório

### Objetivo

Garantir que validações sejam executadas automaticamente antes de mudanças entrarem no `main`.

### Tarefas

#### 5.1 Criar workflow de CI

Criar arquivo:

```text
.github/workflows/ci.yml
```

O workflow deve executar em:

- Pull request para `main`.
- Push em `main`.

Etapas mínimas:

1. Checkout do repositório.
2. Configuração do Python.
3. Instalação das dependências.
4. Execução de formatação em modo check.
5. Execução de lint.
6. Execução de type checking.
7. Execução de testes.
8. Execução das validações de governança PowerShell.

Exemplo base:

```yaml
name: CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  validate:
    runs-on: windows-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          if (Test-Path requirements-dev.txt) { pip install -r requirements-dev.txt }
          if (Test-Path requirements-test.txt) { pip install -r requirements-test.txt }
        shell: pwsh

      - name: Black check
        run: python -m black --check .

      - name: Isort check
        run: python -m isort --check-only .

      - name: Pytest
        run: python -m pytest --cov

      - name: Mypy
        run: python -m mypy .

      - name: Pylint
        run: python -m pylint Orchestrator

      - name: Native governance
        run: ./Tools/ValidarAutomacoes.ps1 -OnlyGovernance
        shell: pwsh
```

A IA deve adaptar caminhos e comandos conforme a estrutura real do projeto.

Critério de aceite:

- Workflow criado.
- CI executa sem depender de arquivos locais não versionados.
- Falhas reais não devem ser ignoradas sem justificativa documentada.

#### 5.2 Proteger branch `main`

A IA deve documentar em `docs/repository-governance.md` a política recomendada:

- Alterações devem entrar via PR.
- CI deve estar verde.
- Commits devem ser semânticos.
- Evidência Playwright é obrigatória para mudanças de UI ou fluxo operacional.

Critério de aceite:

- Documento criado ou atualizado.
- Regras claras para humanos e agentes de IA.

---

## 6. Fase 4 — Métricas de qualidade

### Objetivo

Criar métricas objetivas para acompanhar evolução do projeto.

### Tarefas

#### 6.1 Criar painel de qualidade

Criar arquivo:

```text
docs/quality-dashboard.md
```

Conteúdo mínimo:

```markdown
# Painel de Qualidade

| Métrica | Meta | Atual | Status |
|---|---:|---:|---|
| Cobertura pytest | >= 60% | A medir | Pendente |
| Erros mypy | 0 em módulos críticos | A medir | Pendente |
| Pylint | >= 8.5 | A medir | Pendente |
| Tempo do CI | <= 5 min | A medir | Pendente |
| Secrets detectados | 0 | A medir | Pendente |
| Evidências Playwright pendentes | 0 | A medir | Pendente |
| Tamanho do repo | <= 150 MB | A medir | Pendente |
```

Critério de aceite:

- Arquivo criado.
- Métricas iniciais preenchidas quando possível.
- Campos desconhecidos marcados como `A medir`, sem inventar números.

#### 6.2 Criar script de snapshot de qualidade

Criar arquivo:

```text
Tools/Get-QualitySnapshot.ps1
```

O script deve coletar, quando possível:

- Tamanho total do repositório.
- Quantidade de arquivos grandes.
- Resultado de testes.
- Cobertura.
- Resultado de governança.
- Status de dependências.
- Possíveis arquivos sensíveis.

Critério de aceite:

- Script executável em PowerShell.
- Saída clara em terminal.
- Não deve expor segredos.

---

## 7. Fase 5 — Testes automatizados

### Objetivo

Ampliar confiança nas partes críticas do Orchestrator.

### Tarefas

#### 7.1 Mapear módulos críticos

A IA deve identificar os arquivos responsáveis por:

- Fila de execução.
- Retry.
- `queue_group`.
- Diagnóstico do sistema.
- Scheduler.
- Validação de `.env`.
- Validação de `schedule`.
- Endpoints administrativos.
- Worker.

Critério de aceite:

- Criar ou atualizar `docs/test-coverage-map.md`.
- Listar módulos críticos e status de cobertura.

#### 7.2 Criar testes unitários

Priorizar testes para:

1. Requeue respeitando `queue_group` ativo.
2. Retry limitado por `max_retries`.
3. Classificação de falhas conhecidas.
4. Diagnóstico de worker offline.
5. Diagnóstico de fila parada.
6. Validação de schedule inválido.
7. Validação de `.env` sem expor segredo.

Critério de aceite:

- Testes criados em pasta apropriada.
- Testes executam com `pytest`.
- Testes não dependem de ambiente produtivo.

#### 7.3 Criar testes de contrato da API

Para endpoints críticos, validar:

- Status HTTP.
- Estrutura do JSON.
- Campos obrigatórios.
- Tratamento de erro.
- Não vazamento de segredo.

Critério de aceite:

- Contratos principais cobertos.
- Falhas retornam mensagens operacionais sem detalhes sensíveis.

---

## 8. Fase 6 — Segurança

### Objetivo

Reduzir risco de vazamento de credenciais, dados sensíveis e payloads operacionais.

### Tarefas

#### 8.1 Adicionar varredura de segredos

Opções aceitas:

- `gitleaks`.
- Script PowerShell próprio.
- Validação integrada ao CI.

A varredura deve detectar padrões como:

- API keys.
- Tokens.
- Senhas.
- Connection strings.
- Credenciais Oracle.
- Conteúdo de `.env`.

Critério de aceite:

- Varredura executável localmente.
- Varredura integrada ao CI.
- Falsos positivos documentados, não ignorados em silêncio.

#### 8.2 Sanitizar logs

Criar ou revisar função central de sanitização.

Sugestão de função:

```python
def sanitize_log_payload(payload: object) -> object:
    """Remove ou mascara dados sensíveis antes de registrar logs."""
```

A sanitização deve mascarar:

- Senhas.
- Tokens.
- API keys.
- E-mails, quando necessário.
- CPF/CNPJ, se existirem no domínio.
- URLs com credenciais.
- Connection strings.

Critério de aceite:

- Logs operacionais continuam úteis.
- Dados sensíveis não aparecem em logs.
- Testes cobrindo sanitização.

#### 8.3 Revisar evidências Playwright

Garantir que evidências E2E registrem apenas:

- URL local validada.
- Fluxos navegados.
- Resultado final.
- Quantidade de erros e warnings.
- Artefato visual permitido.

Não devem conter:

- API keys.
- Senhas.
- Payloads brutos.
- Dados pessoais.
- Conteúdo sensível de banco.

Critério de aceite:

- `Tools/Test-PlaywrightEvidence.ps1` continua passando.
- Evidências não expõem dados sensíveis.

---

## 9. Fase 7 — Arquitetura e modularização

### Objetivo

Preparar o projeto para crescer sem acumular lógica misturada entre API, worker, banco e UI.

### Estrutura alvo sugerida

A IA deve avaliar a estrutura atual antes de mover arquivos. Não mover por estética.

Estrutura sugerida para evolução gradual:

```text
Orchestrator/
  api/
    routers/
    schemas/
    middleware/
  core/
    worker/
    scheduler/
    queue/
  domain/
    automacoes/
    execucoes/
    diagnosticos/
  infra/
    database/
    logging/
    config/
  tests/
```

### Tarefas

1. Separar regras de negócio dos endpoints FastAPI.
2. Separar acesso a banco da lógica operacional.
3. Centralizar schemas e contratos de API.
4. Centralizar configuração.
5. Evitar imports circulares.
6. Criar testes antes ou junto de qualquer refatoração.

Critério de aceite:

- Nenhuma mudança arquitetural deve quebrar endpoints existentes.
- Contratos públicos devem ser preservados ou versionados.
- Documentar mudanças em ADR quando forem relevantes.

---

## 10. Fase 8 — Operação e runbooks

### Objetivo

Transformar cada automação em unidade operacional clara, auditável e recuperável.

### Tarefas

#### 10.1 Criar template de runbook

Criar arquivo:

```text
docs/templates/automation-runbook-template.md
```

Template mínimo:

```markdown
# Runbook — Nome da Automação

## Objetivo

## Entradas

## Saídas

## Dependências

## Agenda

## Riscos operacionais

## Como validar execução correta

## Como diagnosticar falha

## Como recuperar falha

## Logs relevantes

## Dono operacional

## Histórico de mudanças relevantes
```

Critério de aceite:

- Template criado.
- Pelo menos uma automação crítica documentada usando o template.

#### 10.2 Criar ranking de automações críticas

Criar ou atualizar:

```text
docs/automation-criticality-map.md
```

Classificar automações por:

- Impacto no negócio.
- Frequência de execução.
- Dependência externa.
- Risco de falha.
- Facilidade de recuperação.

Critério de aceite:

- Lista de automações classificada.
- Prioridade de testes definida com base nesse ranking.

---

## 11. Fase 9 — Dashboard operacional

### Objetivo

Melhorar a utilidade prática do dashboard para operação diária.

### Melhorias sugeridas

1. Exibir SLA por automação:
   - Última execução OK.
   - Última falha.
   - Próxima execução.
   - Tempo médio.
   - Falhas nas últimas 24h.

2. Exibir fila por impacto:
   - Alta prioridade.
   - Média prioridade.
   - Baixa prioridade.
   - Bloqueadas por `queue_group`.

3. Criar modo operador:
   - Reexecutar.
   - Pausar.
   - Retomar.
   - Clonar.
   - Ver log resumido.
   - Abrir evidência.
   - Diagnosticar.

4. Criar resumo de saúde:
   - Worker online/offline.
   - Scheduler ativo/inativo.
   - Banco OK/risco.
   - WAL saudável/alto risco.
   - Pendências de recovery.

Critério de aceite:

- Mudanças de UI devem ter evidência Playwright final.
- Console do navegador deve registrar zero erros e zero warnings, salvo exceção justificada.
- Contratos frontend/backend devem ser validados.

---

## 12. Fase 10 — Documentação de governança

### Objetivo

Manter documentação útil para humanos e agentes de IA.

### Tarefas

Criar ou atualizar:

```text
docs/repository-governance.md
docs/development-workflow.md
docs/testing-strategy.md
docs/security-policy.md
docs/release-checklist.md
```

Conteúdo mínimo:

- Como criar branch.
- Como rodar validações.
- Como executar testes.
- Como validar Playwright.
- Como atualizar changelog.
- Como fazer release.
- Como lidar com falha de CI.
- Como evitar vazamento de segredo.

Critério de aceite:

- Documentos curtos, objetivos e operacionais.
- Evitar documentação decorativa sem comando executável.

---

## 13. Ordem recomendada de execução

A IA deve executar nesta ordem:

1. Auditar arquivos grandes e `.gitignore`.
2. Separar e travar dependências.
3. Criar CI mínimo.
4. Criar painel de qualidade.
5. Criar snapshot de qualidade.
6. Mapear cobertura de testes.
7. Criar testes dos módulos críticos.
8. Adicionar varredura de segredos.
9. Sanitizar logs.
10. Criar runbooks.
11. Melhorar dashboard operacional.
12. Refatorar arquitetura gradualmente.

---

## 14. Critérios globais de conclusão

Este plano será considerado bem executado quando:

- O CI estiver ativo e executando validações principais.
- Dependências estiverem separadas e travadas.
- O repositório não versionar artefatos pesados ou sensíveis.
- Testes cobrirem fluxos críticos do Orchestrator.
- Varredura de segredos estiver ativa.
- Logs forem sanitizados.
- Existir painel de qualidade atualizado.
- Existirem runbooks para automações críticas.
- Mudanças de UI tiverem evidência Playwright final.
- Documentação operacional estiver clara para humanos e agentes de IA.

---

## 15. Observação final para agentes de IA

Não trate este documento como sugestão genérica. Ele é um roteiro operacional.

Ao executar qualquer item:

1. Leia o contexto atual.
2. Faça a menor mudança segura.
3. Rode validações.
4. Atualize documentação necessária.
5. Registre evidência.
6. Pare antes de fazer mudanças amplas demais no mesmo ciclo.

Mudanças grandes sem validação incremental devem ser consideradas falha de execução.
