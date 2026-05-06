# Guia de Operação e Troubleshooting

## 1. Monitor Central
O Monitor (`MonitorAutomacoes.ps1`) coordena os agendamentos via `config.json`.
- **Saúde:** Se o monitor parar, os robôs não disparam. Reinicie executando o script como Administrador.
- **Log:** `Logs\YYYY-MM_Monitor.log`.

## 2. Gestão de Notificações (WhatsApp Soberano)
O motor v1.3 utiliza **Ack Monitoring** para garantir a entrega.
- **Falso Positivo:** Se o log diz "Sucesso" mas a mensagem não chegou, o Motor Soberano agora detecta isso via Ack Nível 0 e encerra com **ExitCode 24**.
- **Como Resetar Sessão:**
    1. Apague a pasta `.wwebjs_auth` na pasta da automação.
    2. No terminal: `node sendWhatsApp.js REAUTH VISUAL`
    3. Escaneie o QR Code na janela que abrirá.

## 3. Troubleshooting de Banco de Dados (Oracle)
As automações utilizam **Oracle Thick Mode**.
- **Queda de Sessão:** Erros como `ORA-00028` ou `ORA-03113` indicam que o servidor derrubou a conexão. O robô está programado para falhar com segurança e tentar novamente no próximo agendamento.
- **Ambiente:** Verifique no `.env` se `ORACLE_CLIENT_PATH` aponta para a pasta correta do Instant Client (ex: `client_2`).

## 4. Códigos de Erro Comuns
| Código | Descrição | Ação Corretiva |
|:--- | :--- | :--- |
| **20** | Timeout Inicialização | Verifique se o servidor tem internet ou reinicie a sessão. |
| **24** | Falha de Entrega Real | A mensagem foi disparada mas o WhatsApp não confirmou saída. |
| **21** | Reautenticação | O token expirou. Realize o pareamento visual (Item 2). |
| **4** | Erro Python | Verifique o hash de estado ou conflito de bibliotecas. |
| **9** | Pre-Flight | O disco pode estar cheio ou o banco Oracle offline. |

## 5. Manutenção de Ambiente (.env)
O arquivo `.env` na raiz é vital. Ele deve conter:
- `ORACLE_CLIENT_PATH`: Caminho para o driver binário.
- `TNS_ADMIN`: Caminho para a pasta `network/admin` (tnsnames.ora).
- `ORACLE_READONLY_USER`/`PASSWORD`: Credenciais de acesso.
- `AUTOMACAO_TEST_EMAIL`: Endereço para redirecionamento em modo teste.
