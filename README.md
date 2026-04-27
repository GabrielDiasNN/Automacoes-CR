# Central de Automacoes (Automacoes Hub)

Este repositorio e o nucleo tecnico para orquestracao de automacoes fiscais e operacionais. Utiliza um modelo **Monitor-Trigger-Action** para garantir execucao resiliente, logs centralizados e monitoramento em tempo real.

O projeto opera sob o **Padrao Ouro de Engenharia**, focando em soberania tecnica, resiliencia extrema contra politicas de TI restritivas e integridade total de dados (PT-BR).

## 🏗️ Arquitetura Tecnica

```mermaid
graph TD
    A[MonitorAutomacoes.ps1] -->|Agenda/Hot-Reload| B(config.json)
    A -->|Inicia| P[run.ps1]
    
    subgraph "Camada de Execucao (Modo Resiliente)"
        P -->|1. Nativo (Python)| PY[Python + oracledb]
        P -->|2. Fallback (Hibrido)| D[Excel VBA / Power Query]
    end

    D -->|SQL/PQ| E[(Oracle DB)]
    PY -->|SQL Nativo CTE| E
    
    D -->|Saidas| F[Email / Dashboard]
    PY -->|Geracao HTML| F
    
    P -->|Opcional| G[lib/Send-WhatsApp.ps1]
    G -->|Node.js| H[WhatsApp Business]
```

---

## 🚀 Modulos de Automacao

### 1. **Receitas Emitidas** (Nativo v2.5.0) 🌟

- **Status**: **100% Nativo (Pure-Python)**.
- **Objetivo**: Controle semanal para conferencia fisica na Cozinha de Quimicos.
- **Diferencial Nativo**:
    - **Soberania**: Zero dependencia de Excel.
    - **Resiliencia**: Extracao inteligente via Oracle CTE (Common Table Expressions) com Fetch-Streaming para evitar timeouts (`ORA-00028`).
    - **IPC Estavel**: Comunicacao via *Stdio* blindada com limpeza de BOM (`utf-8-sig`) e logs Base64.
- **Tecnologia**: Python (oracledb), PowerShell (Outlook COM).

### 2. **Montagem de Terceirizados** (Native-First / Hybrid-Fallback v1.1) 🚀

- **Status**: **Migracao Nativa com Fallback Automatico**.
- **Objetivo**: Validacao fiscal deterministica de ordens de montagem externa.
- **Diferencial de Resiliencia**:
    - **Estrategia**: Tenta a extracao 100% nativa (Python) primeiro. Se o banco derrubar a conexao, aciona instantaneamente o **Fallback Hibrido (Excel)** para garantir a entrega.
    - **Inteligencia**: Validacao e Idempotencia processadas em Python (sem arquivos de texto).
- **Tecnologia**: Python (openpyxl), PowerShell (Base64 Bridge), Excel/VBA (Reserva de Extracao).

### 3. **Receitas Bloqueadas** (VBA + WhatsApp v1.2)

- **Status**: **Legado VBA + WhatsApp Bridge (Outlook-Safe)**.
- **Objetivo**: Processamento de receitas retidas e distribuicao multicanal.
- **Diferencial**:
    - **Seguranca de Envio**: Implementado *Buffer de Estabilidade* de 5 segundos para garantir o esvaziamento da *Outbox* do Outlook.
    - **Multi-instancia**: Gestao de processos para evitar trancamento do Excel ou instancias zumbis.
- **Tecnologia**: Excel/VBA, Power Query, Node.js.

---

## 🛠️ Operacao e Monitoramento

### Monitor Central (`MonitorAutomacoes.ps1`)

- Executa em background controlado por um **Mutex** global.
- **Pre-Flight Check**: Diagnostico de saude (Disco, Oracle Ping, Paths) antes de cada disparo.
- **Hot-Reload**: Alteracoes no `config.json` aplicadas em tempo real via Hash SHA-256.
- **Estado Operacional**: Dashboard visual em `Dashboard/dashboard.html`.

### Tabela de Erros Padronizada

| Codigo  | Descricao                                           |
| :------ | :-------------------------------------------------- |
| **0**   | Sucesso                                             |
| **1-3** | Falha de Arquivo ou Ambiente                        |
| **4**   | Falha tecnica (Invocacao de Macro ou Python)        |
| **5**   | Timeout (Oracle/Processamento)                      |
| **6**   | Erro Fatal (Logica de Negocio ou Falha COM)         |
| **7**   | Arquivo bloqueado (Somente leitura)                 |
| **9**   | Falha Critica de Pre-Flight (Ambiente Inapropriado) |

---

## 📏 Padroes de Engenharia (Padrao Ouro)

O projeto segue regras rigorosas de soberania e seguranca:

1.  **ASCII-Safe Source**: Mensagens de log em codigo-fonte utilizam apenas caracteres ASCII ou *Unicode Escape Sequences*.
2.  **Base64 Bridge Protocol**: Logs e strings acentuadas viajam via Base64 para garantir PT-BR impecavel.
3.  **Zero-Zumbis**: Gestao de objetos COM com liberacao explicita (`Marshal.ReleaseComObject`) e proibicao de `.Quit()` que mate o Outlook do usuario.
4.  **Seguranca**: Proibido hardcode de senhas; uso obrigatorio de `.env` e *Auto-Masking* proativo.

---

Mantido pela equipe de Automacoes & Antigravity AI
