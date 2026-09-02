# Contexto Operacional — OBs Restrição Branco (ORB-07)

## Estado

Implementada e ativa em 25/08/2026 no Orchestrator (`id=6`, `enabled=true`), com
agenda cron de 120 minutos no grupo `oracle`. O preview foi aprovado e a mensagem
operacional contendo as seis OBs foi confirmada no grupo Expedição Tinturaria com
ACK 1. O ciclo normal seguinte retornou código 2 (todas já notificadas), sem novo
envio.

## Decisões canônicas

1. As finalidades de peça contabilizadas como estoque elegível são **fixas por
   regra de negócio**: `3` (CORES CLARAS) e `4` (BRANCO), em
   `FINALIDADES_PECA_ALVO` (`models.py`). A finalidade `1` (SEM RESTRIÇÃO)
   **não pode** entrar no saldo, ainda que represente a maioria das peças do
   depósito 95. Em 26/08/2026 uma alteração passou a derivar o conjunto de
   `SGTPRD.COR_FINALIDADE` (que devolve `{1, 3, 4, 6, 8, 12, 13}` para as
   classes 6 e 9) — foi revertida no mesmo dia, antes de qualquer execução, por
   contrariar essa regra. `COR_FINALIDADE` continua sendo consultada, mas
   **somente** para resolver as descrições oficiais e para falhar de forma
   observável se 3 ou 4 deixarem de constar como compatíveis com as classes
   brancas; nunca para ampliar o conjunto.
   `CLASSIFICACOES_BRANCO_ALVO` guarda as classes-alvo (6, 9).
2. A OB é branca somente quando `CD_CLASSIFICACAO_COR IN (6,9)`:
   `BRANCO` ou `BRANCO 2 FIBRAS`.
3. A cor `00001` não é filtro: no cadastro Oracle ela também aparece em classes
   não brancas. O código da fase 40 é apenas evidência na mensagem e nos dados.
4. `COR_FINALIDADE` é lida na direção **classe → finalidades**, nunca no
   inverso: uma mesma finalidade (3, 4) também é compatível com as classes 10,
   17 e 18, fora do escopo desta automação, então partir da finalidade traria
   OBs indevidas. Partir das classes 6 e 9 é o que dá o conjunto correto.
   `validate_finalidades_query` exige que 6 e 9 devolvam conjuntos
   **idênticos**: a consulta de estoque é agregada por reduzido e não conhece a
   classificação da OB, então conjuntos divergentes tornariam o saldo ambíguo —
   nesse caso a execução falha de forma observável em vez de degradar.
5. Todos os fluxos são aceitos; a seleção exige `STATUS=1`, `OBMONTADA='0'` e
   exclui pedidos terminados em R/S.
6. Estoque é alocado por reduzido em **duas passadas** sobre a fila já
   priorizada (lojas antes da matriz, por data de entrega): primeiro as OBs que
   o saldo cobre por inteiro, depois as parciais, que levam o saldo remanescente.
   Desde 01/09/2026 a cobertura integral **não é mais condição para notificar** —
   virou condição de prioridade. Uma OB com 5 peças restritas disponíveis e
   necessidade de 55 é anunciada como *montagem parcial*: a Montagem de Lotes não
   pode montá-la só com peça sem restrição e deixar as 5 restritas paradas no
   depósito, que é justamente a peça que precisa escoar. `MINIMO_PECAS_NOTIFICAVEL`
   é 1; saldo zero é o único motivo de não notificar. `AvaliacaoOb.alocado` é o
   que a OB de fato segura (≤ `total_pecas`) e é ele — nunca a necessidade — que
   vai para a reserva do state e para a mensagem.
   **Trade-off aceito:** a preferência por quem fecha 100% vale dentro de UM
   ciclo. Como a OB parcial reserva o saldo, uma OB que fecharia integralmente
   no ciclo seguinte (porque chegou estoque novo) enxerga só o saldo livre, e
   não as peças já prometidas à parcial. Antes da mudança essas peças ficavam
   soltas esperando alguém que fechasse 100% — que era justamente o problema.
   A reserva expira em `JANELA_RESERVA_HORAS` e a OB volta a concorrer.
7. Idempotência é por OB e o commit ocorre somente após confirmação do canal.
   O `orb_state.json` guarda, por OB notificada, o carimbo do aviso **e a
   reserva de estoque** que ele criou (`{"em", "reduzido", "reservado"}` — em
   cobertura parcial, `reservado` é o que existia, não o que a OB pedia).
   Uma OB anunciada como parcial **não é re-anunciada** se o saldo subir depois:
   a idempotência é por OB, e a reserva original é mantida como está. A
   reserva é descontada do saldo nos ciclos seguintes: a Expedição não separa as
   peças ao receber o aviso — a OB entra numa fila e é montada quando chega a
   vez —, então sem reserva persistente duas OBs eram anunciadas como prontas
   para as mesmas peças físicas. A reserva termina naturalmente na montagem (a
   OB sai da query por `OBMONTADA='0'` e é podada por ausência). A validade de
   **24 h** (`JANELA_RESERVA_HORAS`) existe só para a OB que fica pendente
   indefinidamente e seguraria o saldo para sempre; ao expirar, a OB sai do
   `notified` **por completo** e volta a concorrer, podendo ser re-anunciada.
   O formato antigo (`{"185719": "<iso>"}`) continua legível como reserva de
   quantidade desconhecida — preserva a idempotência sem reservar saldo.
8. O destino é o mesmo da OFST-06, via `OFST_WHATSAPP_TARGET`.
9. A mensagem normaliza artigo para três dígitos e cor programada para dois
   dígitos; nunca trunca códigos maiores que a largura mínima. `CDARTIGOCRU` é
   **alfanumérico** no Oracle (`0A231` ocorre em produção) e é guardado como
   texto: é um campo puramente cosmético, e coagi-lo para número descartava a OB
   inteira. Quando várias OBs disputam o mesmo reduzido, a linha "Estoque
   disponível" dos blocos seguintes traz "(após as OBs acima)" — o número é o
   saldo no momento da avaliação daquela OB, não um segundo saldo do depósito.
10. `sendMessage` é considerado confirmado pelo ID retornado ou pelo evento
    `message_create`; no `whatsapp-web.js` instalado, o ID pode estar em `$1` em
    vez de `_serialized`. Sem confirmação, a execução falha e o state não é
    promovido.

## Arquitetura

`run.ps1` faz preflight, lock e handoff. `extract_orb.py` consulta Oracle
(finalidades compatíveis → OBs → estoque) e gera
`orb_result.json`/`orb_state.json.tmp`. A consulta de estoque
(`SQL-EstoqueFinalidadesBranco.sql`) usa `GROUPING SETS`: a linha total é o
`COUNT(DISTINCT)` autoritativo e as parciais por finalidade são a evidência da
mensagem — somar as parciais contaria em dobro uma peça com mais de uma
finalidade cadastrada. `validators.py` contém regras puras.
`format_message.py` gera somente o texto. O envio usa o motor compartilhado em
`lib/Send-WhatsApp.ps1` e `lib/WhatsApp-Core.js`.

## Guardrails

- Oracle somente leitura e valores variáveis sempre por bind.
- Nenhuma credencial ou ID real em arquivos versionados.
- Classificação não resolvida é rejeitada com WARN e sem envio; quebra de
  schema ou finalidade também é observável e falha segura.
- Lock/cooldown do WhatsApp não consolida state nem abre falso incidente.
- Alterações futuras nas classes 6/9 exigem nova confrontação com
  `CLASSIFICACAO_COR`, `TIPO_FINALIDADE_FIO` e `COR_FINALIDADE`. Mudanças no
  cadastro de finalidades, ao contrário, são absorvidas sozinhas — é justamente
  por isso que o conjunto deixou de ser constante no código.
- A finalidade 1 (SEM RESTRIÇÃO) é a única finalidade da OFST-06
  (`SQL-EstoqueDeposito95.sql`, `FINALIDADE = 1`) e está **fora** do escopo da
  ORB-07, que só conta 3 e 4. As duas automações não disputam as mesmas peças
  por finalidade, mas ambas operam sobre o depósito 95 e cada uma reserva
  apenas dentro do próprio state — não há reserva compartilhada entre
  elas. Escopos são disjuntos por OB (branco x sem tingimento), mas o pote de
  peças é comum: se a Expedição relatar peça prometida duas vezes, é aqui.
