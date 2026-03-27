---
name: automacao-comms-email
description: Use esta skill para suporte técnico à automação de envio de e-mails via Outlook (VBA).
---

# Automação de E-mail (Outlook)

## Objetivo
Garantir o envio confiável de e-mails e anexos através do Microsoft Outlook a partir das macros VBA do projeto.

## Padrão de Implementação (VBA)
- **Objeto**: `CreateObject("Outlook.Application")`.
- **Verificação do Anexo**: Sempre validar existência e tamanho (`> 0`) via `Dir()` ou `FSO` antes de anexar ao `MailItem`.
- **Envio**: Usar `.Send` para envio automático.
- **Assinatura**: Usar `.HTMLBody = "<salutation>" & .HTMLBody` para preservar a assinatura padrão do Outlook.

## Troubleshooting Comum
| Sintoma | Causa Provável | Ação |
|---|---|---|
| Erro ao criar objeto Outlook | Outlook não está instalado/aberto | Verificar se Outlook está no path; iniciar ou alertar |
| Pop-up de segurança | Política de segurança do Office | Desabilitar via GPO ou usar add-in confiável |
| Anexo não encontrado | Excel bloqueado por outro processo ou macro não salvou | Incluir `wb.Save` antes do envio; validar com `FSO.FileExists` |
| E-mail vai para Rascunhos | `.Send` substituído por `.Display` acidentalmente | Verificar chamada do método |

## Melhores Práticas
1. **HTML Body**: Usar `.HTMLBody` para e-mails com formatação profissional.
2. **BCC para Auditoria**: `mail.BCC = "auditoria@empresa.com"` se necessário.
3. **Tratamento de Erro**: Envolver a rotina em `On Error GoTo ErrHandler` para capturar falhas de conexão.
4. **Limpeza de Objeto**: Executar `Set mail = Nothing` e `Set outlookApp = Nothing` ao final.

## Checklist de Revisão
- [ ] O destinatário (`To`) está correto e existe no Outlook?
- [ ] O assunto (`Subject`) inclui a data de referência?
- [ ] O anexo foi validado (existe + `tamanho > 0`)?
- [ ] O processo Excel libera o objeto Outlook ao final (sem instâncias orphans)?
- [ ] O corpo do e-mail usa `.HTMLBody` para preservar a assinatura?
