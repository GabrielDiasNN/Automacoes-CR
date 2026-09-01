# Runbook — OBs Restrição Branco (ORB-07)

## Objetivo

Avisar a Expedição Tinturaria quando uma OB branca, emitida e não montada, pode
usar peças do depósito 95 com restrição 3 (`CORES CLARAS`) ou 4 (`BRANCO`).

## Diagnóstico

```powershell
Get-Content "OBs Restricao Branco\Logs\Orb.jsonl" -Tail 50
.venv\Scripts\python.exe "OBs Restricao Branco\test_orb_simulation.py"
```

Classificações aceitas: `6 = BRANCO` e `9 = BRANCO 2 FIBRAS`. A cor `00001`
isolada não autoriza notificação.

O saldo é `COUNT(DISTINCT IDPECASPRODUTO)` por reduzido, com contagens de
auditoria separadas para as finalidades 3 e 4. A mensagem usa artigo com três
dígitos (`32` → `032`) e cor programada com dois (`00001` → `01`), sem
truncar códigos maiores que a largura mínima.

## Códigos de saída

| Código | Significado |
|---|---|
| 0 | Envio confirmado e state consolidado |
| 2 | Nada novo a enviar; state reconciliado |
| 3 | Falha definitiva de extração Oracle |
| 4 | Falha de mensagem, canal ou orquestração |
| 9 | Falha de preflight |
| 21 | Sessão WhatsApp requer reautenticação |
| 22 | Canal ocupado/cooldown; state não consolidado |

## Promoção

1. [x] Rodar testes e governança.
2. [x] Executar a simulação Oracle e confrontar amostras com o SGT.
3. [x] Gerar e aprovar o preview da mensagem.
4. [x] Chamar `POST /api/automations/preflight` com o manifesto.
5. [x] Cadastrar no Orchestrator (`id=6`, fila `oracle`).
6. [x] Executar o envio confirmado e manter a agenda habilitada.

## Incidente de entrega e reconciliação (25/08/2026)

O primeiro ciclo terminou com exit code 0 porque o `whatsapp-web.js` devolveu
`undefined` e o motor tratou isso como despacho; a mensagem não apareceu no
primeiro diagnóstico e o state foi marcado indevidamente. O motor compartilhado
foi corrigido para exigir `waitUntilMsgSent` e confirmar o ID pelo retorno ou pelo
evento `message_create`. A versão instalada expõe o identificador no campo interno
`$1`, sem `_serialized`, por isso ambos os formatos são aceitos. Sem confirmação,
o processo falha e não consolida `orb_state.json`.

Após o ajuste, a mensagem exata do preview foi observada no grupo correto com ACK
1; as seis OBs foram reconciliadas no state. O ciclo normal seguinte retornou 2 e
não enviou novamente.

## `orb_state.json` — reserva de estoque entre ciclos

Desde 25/08/2026 o state guarda, além do carimbo do aviso, **quanto** cada OB
notificada reservou:

```json
{ "notified": { "185719": { "em": "2026-08-25T16:54:40", "reduzido": 26, "reservado": 55 } } }
```

- A reserva é descontada do saldo do depósito antes da alocação do ciclo
  seguinte. Sem ela, duas OBs eram anunciadas como prontas para as mesmas peças
  físicas — a Expedição não separa a malha ao receber o aviso.
- Em **cobertura parcial** (desde 01/09/2026), `reservado` é o que a OB de fato
  segura, não o que ela pede: uma OB de 55 peças anunciada sobre 5 peças
  restritas grava `"reservado": 5`. Se o saldo subir depois, ela **não** é
  re-anunciada — a idempotência é por OB e a reserva original é mantida.
- A reserva termina na montagem: a OB sai da query (`OBMONTADA='0'`) e é podada
  do state por ausência.
- Validade de **24 h** (`JANELA_RESERVA_HORAS` em `validators.py`), só para a OB
  que fica pendente indefinidamente. Ao expirar, a OB sai do `notified` inteiro,
  volta a concorrer pelo estoque e pode ser re-anunciada; o extrator loga a
  expiração em WARN (`reserva(s) vencida(s) apos 24h`).
- O formato antigo (`"185719": "<iso>"`) continua sendo lido como reserva de
  quantidade **desconhecida** (`reservado: 0`): a OB não é re-avisada, mas
  também não segura saldo. Cada entrada legada se converte sozinha quando a
  janela vence e a OB é reservada de novo com a quantidade real.
- Um `orb_state.json` com JSON inválido continua sendo tratado como vazio, o que
  **re-avisa** todas as OBs prontas. Ao editá-lo à mão, valide o JSON antes.

## Rollback

Pausar ORB-07 no Orchestrator e preservar logs, preview e state para diagnóstico.
Não apagar `orb_state.json` sem autorização, pois isso permite reavisar OBs já
notificadas.
