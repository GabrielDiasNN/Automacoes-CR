# Runbook — Recuperação da máquina (formatação ou host novo)

[⬅️ Voltar para o Hub Central](../../README.md)

Clonar o repositório **não** devolve o hub funcionando. O código volta inteiro do
Git, mas credenciais e dados operacionais são deliberadamente não versionados —
e três deles não têm origem para serem reconstruídos.

## Antes de formatar — copie estes três itens

Sem eles a recuperação é possível, mas com perda. Cabem num pendrive.

| Item | Tamanho | O que se perde sem backup |
|---|---|---|
| `.env` | 4 KB | Credenciais Oracle e `ORCHESTRATOR_API_KEY`. Refazível **se** você tiver as senhas Oracle à mão; a API Key pode ser gerada nova (basta atualizar o Dashboard). |
| `Orchestrator/automacoes.db` | ~10 MB | Cadastro das 5 automações (agendamento, criticidade, fila), todo o histórico de execuções, métricas e audit log. O cadastro é refazível pelo Dashboard; **histórico e métricas, não**. |
| `Produção Beneficimento/snapshots/beneficiamento_historico.db` | ~70 MB | `fato_producao_historica` — série histórica acumulada execução após execução. As queries Oracle trazem o período corrente, então **o acumulado não se reconstrói**. |

Guarde o `.env` como credencial: quem o tem acessa o Oracle de produção.

> O `.env` é o único dos três que muda pouco. Os dois bancos crescem a cada
> execução — se o backup for antigo, você recupera o hub funcionando e perde só
> a série entre o backup e a formatação.

## Não precisa de backup

Tudo abaixo é regenerado sozinho ou por um comando:

- `.venv/`, `node_modules/`, `Dashboard/dist/`, `__pycache__/`, caches de lint — reinstaláveis a partir dos locks versionados.
- `Logs/`, `*.pid`, `debug.log` — descartáveis.
- `delivery_state.json`, `*_state.json`, `*_result.json`, `phase_cards.json` — estado de idempotência das automações. Ausentes, a primeira execução se comporta como conteúdo novo: no pior caso **reenvia uma notificação**, que é o lado seguro do contrato (ver `lib/Lib-Idempotency.psm1`).
- `snapshots/latest/*.analytics.json` — regeneram no primeiro refresh do Beneficiamento.
- Sessão do WhatsApp em `%LOCALAPPDATA%\Automacoes\wwebjs_auth\` — refeita com QR code. **Não** copie este diretório para a máquina nova: são credenciais de sessão, e o objetivo de tê-las tirado do repositório foi justamente parar de transportá-las (ver `CHANGELOG.md` [1.3.1]).

## Restauração

### 1. Pré-requisitos externos

- **Python 3.12** (mesma minor — o lock é resolvido para ela)
- **Node.js LTS**
- **PowerShell 7+** (`pwsh`) — o hub usa PS 5.1 e 7; ambos precisam existir
- **Git**
- **Oracle Instant Client** — obrigatório: `lib/python/oracle_client.py` ativa Thick Mode, e sem o client nenhuma extração roda

### 2. Clonar e restaurar os arquivos guardados

```powershell
git clone https://github.com/GabrielDiasNN/Automacoes-CR.git C:\Automacoes
```

Copie de volta, nos mesmos caminhos: `.env`, `Orchestrator/automacoes.db` e
`Produção Beneficimento/snapshots/beneficiamento_historico.db`.

Sem o `.env`, parta de `.env.example` e preencha as credenciais.

### 3. Ambientes

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-test.txt -r requirements-dev.txt
```

```powershell
cd Dashboard; npm ci; npm run build
```

```powershell
cd lib; npm ci
```

### 4. Banco e serviço

```powershell
cd Orchestrator; ..\.venv\Scripts\alembic upgrade head
```

Vale mesmo com o `.db` restaurado — se o backup for de um schema anterior, o
Alembic o migra.

```powershell
pwsh -File Infrastructure\Install-OrchestratorTask.ps1
pwsh -File Infrastructure\Start-Orchestrator.ps1
```

A tarefa agendada guarda o caminho absoluto do script, então precisa ser
registrada de novo em qualquer host — e reregistrada se a pasta mudar de lugar.

### 5. Sessão do WhatsApp

```powershell
pwsh -File lib\Keep-WhatsApp-Open.ps1
```

Autentique pelo QR code. Confirme que o perfil nasceu no caminho canônico:

```powershell
Test-Path "$env:LOCALAPPDATA\Automacoes\wwebjs_auth\session-hub-global"
```

### 6. Verificação

```powershell
pwsh -File Tools\ValidarAutomacoes.ps1 -BasePath .
cd Orchestrator; ..\.venv\Scripts\pytest -q
Invoke-Pester -Path lib\tests
```

Com o Orchestrator no ar, o smoke pós-deploy fecha a checagem:

```powershell
pwsh -File Tools\Test-OrchestratorIntegrity.ps1
```

Ele exige `ORCHESTRATOR_API_KEY` no ambiente — por isso fica fora do
`ValidarAutomacoes.ps1`, que roda offline no pre-commit.

## O nome da pasta

`C:\Automacoes` não é obrigatório: o Git não registra o nome do diretório e os
`script_path` das automações no banco são relativos (`.\Receitas Bloqueadas\run.ps1`).
Clone onde quiser. O que se prende ao caminho absoluto é a **tarefa agendada** e
os executáveis do **`.venv`** — os dois são recriados nos passos 3 e 4, então
escolher o diretório na hora do clone não custa nada. Mudar de lugar **depois**
custa recriar ambos.
