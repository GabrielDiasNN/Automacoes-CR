# Contexto Operacional — OBs Paradas Fase (OBP-04)

## Propósito

Automação de monitoramento de OBs (Ordens de Beneficiamento) paradas por fase. Dispara cards visuais no WhatsApp do grupo de PCP/Produção Beneficiamento com as OBs que ultrapassaram o threshold de dias parados por fase.

## Sessão WhatsApp

- `clientId`: `hub-global` (compartilhada com Receitas Bloqueadas)
- Sessão salva em: `%LOCALAPPDATA%\Automacoes\wwebjs_auth\session-hub-global\` (fora do repositório; override via `WHATSAPP_AUTH_PATH`)
- Re-autenticar via: `lib/Authenticate-WhatsApp.bat`

## Idempotência

- Hash SHA-256 dos dados Oracle detecta mudanças
- `delivery_state.json` registra sucesso por fase
- Reenvio só ocorre quando hash muda ou fase falhou

## Dependências críticas

- Oracle — string de conexão via `ORACLE_CONNECT_STRING` no `.env`
- Pillow — geração de cards PNG
- `whatsapp-web.js` via `node_modules` compartilhado em `lib/` (motor `lib/WhatsApp-Core.js`, invocado sempre via `lib/Send-WhatsApp.ps1`)

## Utilitários de debug

- `format_message.py` — **utilitário legado de depuração**. Não é executado pelo `run.ps1` nem pelo Orchestrator. Serve apenas para inspecionar o layout da mensagem de texto em desenvolvimento local. Não remover sem avaliar uso manual.

## Padrão de logging

- `run_obs_paradas.py` (via `lib/python/hub_runner.py`) emite o envelope estruturado (`INFO`/`WARN`/`ERRO`/`DEBUG`) com `ExecId`; o `run.ps1` é só o shim.
- `extract_obs.py` usa `make_logger` (logger Python padrão) com output para stderr; o runner encaminha as linhas ao log da execução via `hr.run_python_step`.
- `generate_phase_cards.py` usa `make_logger("OBP-CARDS")` (`automation_log`) com `HUB_LOG_STRUCTURED=1` (step `transform`), emitindo eventos JSONL direto para `Logs/ObsParadasFase.jsonl` (`Logs/*.jsonl`) via runner.

## Histórico de decisões

- Orquestração migrada para `run_obs_paradas.py` (rollout do item 3, PR 93): `run.ps1` virou shim, o worker continua chamando `powershell.exe -File run.ps1 <ExecId>`. O envio usa `hub_whatsapp.send_whatsapp`; a reconciliação por fase segue a regra do `run.ps1` antigo (`delivery_state.json` por fase, `obs_state.json` só com todas as fases entregues), sem `resolve_whatsapp_batch_delivery`, que é de outro estado (`notified`).
- BATCH mode adotado para envio (sessão Chrome única para todas as fases)
- 40s de settle (`BATCH_SETTLE_MS_NORMAL`) após `ready` para garantir WhatsApp Web totalmente carregado antes do envio; dreno ativo com `mouse.move` a cada 3s para manter Chrome acordado durante uploads de mídia
- `cleanProfileForRetry` remove apenas LOCK files — `.log` contêm tokens de sessão válidos

---

## 🧠 Gestão de Contexto (AI-Native)
- **Obrigação:** Atualizar este contexto após mudanças nas fases monitoradas, na resolução de contatos via `.env` ou no protocolo BATCH do WhatsApp.
- **Estado (07/07/2026):** Fase 47-UMM (UMEDECIMENTO DE MALHA) adicionada ao monitoramento (`threshold_dias: 0.5`, responsável `lider_reserva_3_turno`).
- **Objetivo:** Permitir que a IA entenda o fluxo Oracle → cards PNG → WhatsApp BATCH e a idempotência via hash SHA-256 sem reanalisar o código Python.
