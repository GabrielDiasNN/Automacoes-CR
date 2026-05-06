# Guia de Operação e Troubleshooting

## 1. Monitor Central
O Monitor (`MonitorAutomacoes.ps1`) deve estar sempre em execução para processar os agendamentos.
- **Log:** Verifique `Logs\YYYY-MM_Monitor.log`.
- **Status:** Acesse `Dashboard\dashboard.html`.

## 2. Gestão de Notificações (WhatsApp)
O WhatsApp utiliza uma sessão headless via Node.js.
- **Lentidão/Falha:** Geralmente causada por sessão expirada ou timeout de inicialização.
- **Como Resetar Sessão:**
    1. Encerre o processo `node.exe` (se houver).
    2. Apague a pasta `.wwebjs_auth` dentro da pasta da automação.
    3. Execute o script em modo visual para novo pareamento:
       `node sendWhatsApp.js DEBUG_PAIRING VISUAL`
    4. Escaneie o QR Code na janela do navegador que abrirá no servidor.

## 3. Códigos de Erro Comuns
| Código | Causa | Solução |
|:--- | :--- | :--- |
| **20** | Timeout WhatsApp | Resetar sessão ou verificar internet do celular. |
| **21** | Reautenticação | Escanear QR Code novamente. |
| **4** | Erro Python | Verificar traceback no log da automação. |
| **9** | Pre-Flight | Verificar se o banco Oracle está acessível (Ping). |

## 4. Manutenção de Bibliotecas
- **Python:** `pip install -r requirements.txt`
- **Node.js:** `npm install` (nas pastas específicas).
