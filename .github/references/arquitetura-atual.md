# Arquitetura Atual — Automacoes Hub

## Visão geral

O projeto é um hub de automações fiscais e operacionais consolidado na stack **Python/PowerShell/Node.js**.
A arquitetura atingiu o estado **Soberano**, onde cada camada possui autonomia de contexto e resiliência a falhas de protocolo.

---

## Stack Moderna (100% Ativa)

### Orquestração e Controle
- **Linguagem:** PowerShell Core.
- **Monitor Central:** `MonitorAutomacoes.ps1` (Gestão de ciclo de vida e Mutex).
- **Entrypoints:** Scripts `run.ps1` (Ponto único de entrada por automação).

### Inteligência de Negócio e Dados
- **Linguagem:** Python 3.12+.
- **Soberania de Ambiente:** Uso nativo de `python-dotenv`. Os scripts Python carregam seu próprio contexto do `.env`, eliminando dependência da injeção de variáveis pelo orquestrador.
- **Data Engine:** Pandas / NumPy (Vetorização O(n)).
- **Formatação:** OpenPyXL (Geração de Excel Analítico com máscaras PT-BR).
- **Comunicação IPC:** Stdio Pipes ou Hashes de Estado (MD5).

### Camada de Dados (Oracle)
- **Driver:** `oracledb` em modo **Thick Client** (Obrigatório para suporte a protocolos de segurança e senhas legadas).
- **Resiliência:** Tratamento específico para quedas de sessão (`ORA-00028`, `ORA-03113`) com recuperação automática no próximo ciclo.
- **Regra de Ouro:** Colunas explícitas em todas as queries. BAN total em `SELECT *`.

### Saídas e Notificações (Soberanas)
- **E-mail:** PowerShell + Outlook COM (Preservação de assinatura e anexos dinâmicos).
- **WhatsApp (Motor Soberano v1.3):** Node.js Headless com protocolo de **Persistência de Ack**. O motor aguarda a confirmação física do servidor do WhatsApp antes de encerrar o navegador, eliminando falsos-positivos.
- **Dashboard:** HTML5/CSS3 moderno com refresh via JSON.

---

## Paradigma de Inteligência: Idempotência Estrita

O hub implementa um controle de estado cruzado para evitar notificações redundantes (Spam):
1.  **Cálculo de Hash:** O Python gera um hash MD5 do conteúdo consolidado.
2.  **Trava Cross-Channel:** Tanto o orquestrador de e-mail quanto o motor de WhatsApp consultam arquivos de estado (`*_state.json`) e suprimem o disparo se a informação já tiver sido entregue com sucesso.

---

## Governança e Segurança (Padrão Ouro)

### Zero Trust Security
O repositório é blindado. Credenciais residem apenas no `.env`. O linter de portabilidade impede o uso de caminhos absolutos (`C:\...`), garantindo que o projeto funcione em qualquer diretório.

### Base64 Bridge Protocol & ASCII-Safe
Para garantir integridade PT-BR entre camadas (PS -> PY -> NODE), todas as mensagens viajam em Base64. O código-fonte é rigorosamente auditado para ser **ASCII-Safe**, prevenindo corrupção de encoding.

---

## Regra de Mudança (AI-Native)

1.  Preservar o `ExecId` para rastreabilidade universal.
2.  Manter a portabilidade absoluta (Caminhos relativos).
3.  Seguir o padrão de cores corporativo (#0f4c81).
4.  Garantir blocos `catch` com exceções específicas.
