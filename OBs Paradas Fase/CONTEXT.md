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

- `run.ps1` usa `Write-AutomacaoLog` (via `Lib-Logging.psm1`) para todas as mensagens estruturadas com nível (`INFO`/`WARN`/`ERRO`/`DEBUG`) e `ExecId`.
- `extract_obs.py` usa `make_logger` (logger Python padrão) com output para stderr; o output é capturado pelo PowerShell via `Invoke-OraclePythonScript`.
- `generate_phase_cards.py` usa `print()` direto para stdout/stderr — deliberado para simplicidade, já que o script não roda em contexto de longa duração e toda saída é capturada pelo caller PowerShell via `Invoke-NativeProcess`.

## Histórico de decisões

- BATCH mode adotado para envio (sessão Chrome única para todas as fases)
- 40s de settle (`BATCH_SETTLE_MS_NORMAL`) após `ready` para garantir WhatsApp Web totalmente carregado antes do envio; dreno ativo com `mouse.move` a cada 3s para manter Chrome acordado durante uploads de mídia
- `cleanProfileForRetry` remove apenas LOCK files — `.log` contêm tokens de sessão válidos

---

## 🧠 Gestão de Contexto (AI-Native)
- **Obrigação:** Atualizar este contexto após mudanças nas fases monitoradas, na resolução de contatos via `.env` ou no protocolo BATCH do WhatsApp.
- **Estado (07/07/2026):** Fase 47-UMM (UMEDECIMENTO DE MALHA) adicionada ao monitoramento (`threshold_dias: 0.5`, responsável `lider_reserva_3_turno`).
- **Objetivo:** Permitir que a IA entenda o fluxo Oracle → cards PNG → WhatsApp BATCH e a idempotência via hash SHA-256 sem reanalisar o código Python.
