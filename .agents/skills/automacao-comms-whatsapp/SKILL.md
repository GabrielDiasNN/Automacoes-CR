---
name: automacao-comms-whatsapp
description: Use esta skill para suporte técnico à ponte de comunicação via WhatsApp (Node.js + whatsapp-web.js).
---

# Bridge de Comunicação WhatsApp

## Objetivo
Manter e depurar a integração de saída de dados via WhatsApp no projeto Automacoes.

## Estrutura Técnica
- **Trigger**: `Trigger_Automation.vbs` com `POST_EXECUTION_BAT` apontando para `RunWhatsApp.bat`.
- **BAT**: `RunWhatsApp.bat` — resolve `%ComSpec%`, valida pré-requisitos e passa `ExecId` + `MODE` ao Node.
- **Node.js**: `sendWhatsApp.js` — carrega config, gerencia sessão e envia via `whatsapp-web.js`.
- **Config**: `whatsapp-config.json` (destino, anexo, mensagem, retry).
- **Auth**: Pasta `.wwebjs_auth` (mantém sessão do QR Code. **Não apagar.**).
- **Estado**: `whatsapp-state.json` (controle de idempotência por `execKey`).

## Fluxo de Execução
```
Trigger_Automation.vbs
  └─► RunWhatsApp.bat (ExecId + MODE=AUTO)
        └─► sendWhatsApp.js
              ├─ Carrega whatsapp-config.json
              ├─ Verifica sessão (.wwebjs_auth)
              ├─ Verifica idempotência (whatsapp-state.json)
              └─ Envia mensagem/anexo → WhatsApp
```

## Exit Codes do Node.js (`sendWhatsApp.js`)
| Code | Significado |
|---|---|
| `0` | Sucesso ou desabilitado por config |
| `11` | Anexo não encontrado |
| `20` | Erro final após todas as tentativas |
| `21` | Sessão expirada → BAT relança em modo PAIRING |
| `22` | `whatsapp-config.json` inválido |
| `99` | Erro fatal inesperado |

## Workflow de Depuração
1. **Bootstrap**: Inicie por `sendWhatsApp-bootstrap.log` — captura erros antes de qualquer `require`.
2. **Log Principal**: `ReceitasBloqueadas.txt` (ou o `logFile` configurado) — fluxo completo de execução.
3. **Autenticação**: Se `ExitCode=21`, a sessão expirou. O BAT limpa `.wwebjs_auth/session-*` e reabre em modo PAIRING (janela visível com QR).
4. **Config**: Valide o `whatsapp-config.json` com foco em `app.enabled`, `target.groupName` e `paths.attachmentPath`.

## Procedimentos de Manutenção
- **Atualizar Destinatários**: Editar `whatsapp-config.json`. Formato: `5511999999999@c.us`.
- **`npm install` corrompido**: Deletar `node_modules` e rodar `npm install` na pasta da automação.
- **Execução sob demanda**: O Node é disparado pelo VBS/BAT. Não fica em memória.

## Cuidados
- **Rate Limit**: Evitar disparos em curto intervalo para prevenir banimento.
- **Idempotência**: A `execKey` (hash de destino + ExecId + tamanho do arquivo) impede reenvios duplicados.
- **Sessão**: Não apague `.wwebjs_auth` sem necessidade — exige novo pareamento QR.
