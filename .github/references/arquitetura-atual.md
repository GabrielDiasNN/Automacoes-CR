# Arquitetura Atual — Automacoes Hub

## Visão geral

O projeto é um hub de automações fiscais e operacionais consolidado na stack **Python/PowerShell/Node.js**. 
Abandonou-se a dependência de runtime Excel/VBA, utilizando-o apenas como formato de saída analítica (anexos) gerados programaticamente.

---

## Stack Moderna (100% Ativa)

### Orquestração e Controle
- **Linguagem:** PowerShell Core.
- **Monitor Central:** `MonitorAutomacoes.ps1` (Gestão de ciclo de vida e Mutex).
- **Entrypoints:** Scripts `run.ps1` (Ponto único de entrada por automação).

### Inteligência de Negócio
- **Linguagem:** Python 3.12+.
- **Data Engine:** Pandas / NumPy (Vetorização O(n)).
- **Formatação:** OpenPyXL (Geração de Excel Profissional).
- **Comunicação IPC:** Stdio Pipes ou JSON State Files (Idempotência).

### Camada de Dados
- **Banco:** Oracle SQL.
- **Driver:** `oracledb` (Thin/Thick mode).
- **Regra de Ouro:** Colunas explícitas em todas as queries. BAN total em `SELECT *`.

### Saídas e Notificações
- **E-mail:** PowerShell + Outlook COM (Preservação de assinatura oficial).
- **WhatsApp:** Node.js (Puppeteer/WhatsApp-Web.js) em modo Headless.
- **Dashboard:** HTML5/CSS3 moderno com refrescamento via JSON.

---

## Modelo Operacional: Monitor-Trigger-Action

1.  **Monitor:** Verifica o `config.json` a cada 20s. Valida se a automação deve rodar e se o ambiente está saudável (Pre-Flight).
2.  **Trigger:** Dispara o `run.ps1` da automação específica.
3.  **Action (Python):** Conecta ao Oracle, extrai dados, compara com o "Estado Anterior" (Idempotência), gera o HTML do e-mail e a planilha Excel formatada.
4.  **Delivery:** O PowerShell retoma o controle, anexa os arquivos e dispara para e-mail/WhatsApp.

---

## Governança e Segurança

### Zero Trust Security
O repositório é blindado contra vazamento de credenciais. O arquivo `.env` (não versionado) é a única fonte de verdade para secrets. O script `Tools/Test-ZeroTrust.ps1` valida isso no pre-commit.

### Base64 Bridge Protocol
Para evitar corrupção de caracteres especiais (acentuação PT-BR) entre as camadas (PS -> PY -> NODE), todas as strings críticas viajam codificadas em Base64.

### Gerenciamento de Memória
A arquitetura é proativa na liberação de recursos. Objetos COM do Outlook são liberados via `[System.GC]::Collect()` para evitar processos zumbis que degradam a performance do servidor.

---

## Componentes de Legado (Arquivados)

As pastas `Legacy/` em cada módulo contêm os artefatos antigos (`.xlsm`, `.bas`, `.pq`). Estes arquivos:
- **NÃO** devem sofrer manutenção.
- Servem apenas como referência histórica.
- Devem ser ignorados pelo monitoramento ativo.

---

## Regra de Mudança (AI-Native)

Qualquer alteração futura deve:
1.  Atualizar o cabeçalho JSON do arquivo fonte.
2.  Preservar o `ExecId` para rastreabilidade.
3.  Manter a portabilidade (caminhos relativos).
4.  Seguir o padrão de cores corporativo (#0f4c81).
