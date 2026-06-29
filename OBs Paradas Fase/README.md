# OBs Paradas Fase (OBP-04)

Monitora Ordens de Beneficiamento paradas por fase no processo produtivo e envia cards visuais via WhatsApp para o grupo de PCP/Produção.

## Funcionamento

1. **Extração Oracle** — `extract_obs.py` consulta `SRVDB02` e grava `obs_result.json`
2. **Geração de cards** — `generate_phase_cards.py` gera um PNG por fase com Pillow
3. **Idempotência** — `delivery_state.json` evita reenvio do mesmo lote
4. **Envio WhatsApp** — sessão `hub-global` envia todas as fases em lote único (BATCH mode)

## Configuração

| Arquivo | Finalidade |
|---------|-----------|
| `whatsapp-config.json` | chatId do grupo e clientId da sessão |
| `config.json` | threshold de dias parados por fase |

## Pré-requisitos Python

- **Pillow** — geração de cards PNG (`pip install pillow`)

## Autenticação WhatsApp

```
C:\Automacoes\lib\Authenticate-WhatsApp.bat
```

## Agendamento

Seg–Sex às 07:30 e 13:00 (America/Sao_Paulo)

## Exit Codes

| Código | Significado |
|--------|-------------|
| 0 | Sucesso — todas as fases enviadas |
| 2 | Idempotência — sem alterações desde o último envio |
| 3 | Falha Oracle após 3 tentativas |
| 4 | Falha no envio WhatsApp |
| 9 | Falha no pre-flight |
| 21 | Sessão WhatsApp expirada — reautenticar |
| 24 | Chrome não inicializa — verificar processos zumbi e reautenticar |
