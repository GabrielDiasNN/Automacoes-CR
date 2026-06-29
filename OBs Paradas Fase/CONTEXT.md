# Contexto Operacional — OBs Paradas Fase (OBP-04)

## Propósito

Automação de monitoramento de OBs (Ordens de Beneficiamento) paradas por fase. Dispara cards visuais no WhatsApp do grupo de PCP/Produção Beneficiamento com as OBs que ultrapassaram o threshold de dias parados por fase.

## Sessão WhatsApp

- `clientId`: `hub-global` (compartilhada com Receitas Bloqueadas)
- Sessão salva em: `lib/.wwebjs_auth/session-hub-global/`
- Re-autenticar via: `lib/Authenticate-WhatsApp.bat`

## Idempotência

- Hash SHA-256 dos dados Oracle detecta mudanças
- `delivery_state.json` registra sucesso por fase
- Reenvio só ocorre quando hash muda ou fase falhou

## Dependências críticas

- Oracle `SRVDB02:1521/dbprd` — query em `extract_obs.py`
- Pillow — geração de cards PNG
- `whatsapp-web.js` via `node_modules` em `Receitas Bloqueadas/`

## Histórico de decisões

- BATCH mode adotado para envio (sessão Chrome única para todas as fases)
- 20s de settle após `ready` para garantir WhatsApp Web totalmente carregado antes do envio
- `cleanProfileForRetry` remove apenas LOCK files — `.log` contêm tokens de sessão válidos
