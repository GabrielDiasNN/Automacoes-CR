# Workflow: Criacao e Registro de Nova Automacao

Roteiro padronizado para criar uma nova automacao no Hub de Automacoes com scaffolding valido, manifesto estruturado e registro no Orchestrator.

---

## 1. Regras Fundamentais
- Toda automacao deve possuir obrigatoriamente um `automation.manifest.json` valido em sua pasta raiz.
- O manifesto ausente e classificado como `incident` e bloqueia criacao/atualizacao no preflight.
- O entrypoint padrao de execucao deve ser `run.ps1` (salvo automacoes orientadas a snapshot como Producao Beneficiamento).
- Toda credencial e configuracao de banco deve ser lida via `.env` utilizando `lib/Lib-Config.psm1`.

---

## 2. Passo a Passo

### Passo 1: Scaffolding a partir de `_Template`
Utilize a ferramenta oficial do repositorio para gerar a estrutura inicial a partir do template padronizado:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/New-Automation.ps1 -Name "Nome da Automacao" -Criticality "high" -SlaMinutes 30
```
*Nota: O slug e o ID interno são gerados automaticamente a partir do `-Name`. Parâmetros opcionais incluem `-WithOracle`, `-WithWhatsApp`, `-WithoutEmail` e `-OwnerArea`.*

---

### Passo 2: Configuracao do `automation.manifest.json`
Edite o manifesto gerado na pasta da automacao para ajustar dependências, SLAs e descrições conforme o contrato canônico do repositório:

```json
{
  "id": "COD-01",
  "name": "Nome da Automacao",
  "slug": "nome-da-automacao",
  "criticality": "high",
  "sla_minutes": 30,
  "owner_area": "Operações / PCP",
  "entrypoint": "run.ps1",
  "runtime": "powershell",
  "channels": ["email"],
  "queue_group": "nome_da_automacao",
  "max_runtime_minutes": 30,
  "max_retries": 0,
  "schedule_summary": "Manual",
  "runbook_path": "docs/runbooks/nome-da-automacao-runbook.md",
  "context_path": "Nome da Automacao/CONTEXT.md",
  "readme_path": "Nome da Automacao/README.md",
  "orchestrator": {
    "script_path": "./Nome da Automacao/run.ps1"
  },
  "dependencies": {
    "oracle": false,
    "outlook": true,
    "whatsapp": false
  },
  "smoke_tests": [
    "Orchestrator/tests/test_nome_da_automacao.py"
  ]
}
```
*Atenção: `criticality` deve ser estritamente `critical`, `high`, `medium` ou `low`. A validação é rigorosa via Pydantic (`CatalogManifest`).*

---

### Passo 3: Implementacao do Script Principal (`run.ps1`)
Certifique-se de que o script `run.ps1`:
1. Esta salvo em **UTF-8 with BOM**.
2. Utiliza apenas caminhos relativos ou `$PSScriptRoot`.
3. Importa `Lib-Config.psm1` para ler credenciais.
4. Possui tratamento de erro estruturado (`try/catch`) com codigo de saida diferente de 0 em falhas.

---

### Passo 4: Validacao de Preflight da Nova Automacao
Execute a validacao completa de governanca e manifesto antes de testar a execucao:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-SourceEncoding.ps1 -RootPath . -Paths @("Nome da Automacao/run.ps1", "Nome da Automacao/automation.manifest.json")
```

---

### Passo 5: Registro no Orchestrator
Com a API do Orchestrator ativa, valide a conformidade de governança via rota de preflight:

As rotas `/api/automations/*` exigem autenticacao (`X-API-Key`). A chave sai do
`.env` (`ORCHESTRATOR_API_KEY`) — nunca a digite no comando nem a cole neste
arquivo.

```powershell
# A validacao preflight checa o manifesto e a governanca da automacao
.venv\Scripts\python -c "import os, requests; from dotenv import load_dotenv; load_dotenv(); print(requests.post('http://127.0.0.1:8000/api/automations/preflight', headers={'X-API-Key': os.environ['ORCHESTRATOR_API_KEY']}, json={'name': 'Nome da Automacao', 'script_path': 'Nome da Automacao/run.ps1'}).json())"
```

Para efetivar o cadastro da nova automação no catálogo ativo do Orchestrator:

```powershell
.venv\Scripts\python -c "import os, requests; from dotenv import load_dotenv; load_dotenv(); print(requests.post('http://127.0.0.1:8000/api/automations/', headers={'X-API-Key': os.environ['ORCHESTRATOR_API_KEY']}, json={'name': 'Nome da Automacao', 'script_path': 'Nome da Automacao/run.ps1', 'queue_group': 'nome_da_automacao', 'sla_minutes': 30}).json())"
```

> Alternativa preferida quando ja' houver sessao de agente ativa: use o driver
> em `.claude/skills/run-orchestrator/driver.py`, que ja' resolve a chave e o
> login do dashboard pelo mesmo caminho.
