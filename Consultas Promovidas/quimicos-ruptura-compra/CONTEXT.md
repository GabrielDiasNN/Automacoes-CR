# Contexto: Sentinela Ruptura Quimicos (CP-04)

- **Modo atual:** `sombra` (envios WhatsApp redirecionados para `AUTOMACAO_ALERT_WHATSAPP`).
- **Arquitetura:** Modelo 2 (`run.ps1` shim -> `promovidas.run_promocao` -> snapshot em `Consultas Promovidas/snapshots/latest/quimicos-ruptura-compra.json`).
- **Calibração pendente (Fase 2a):** na `CTE PARAMETROS` de `consulta.sql`, `SEGURANCA_KG=0`, `COBERTURA_MIN_DIAS=0` e `PRAZO_PADRAO_DIAS=NULL` (porque `PRAZOENTREGA` é `0` no ERP). Enquanto não forem calibrados com PCP/Compras, itens sem prazo caem em `DADOS_INCOMPLETOS` (com `QTD_SUGERIDA_COMPRA_KG` nulo) e apenas ruptura já consumada (`ESTOQUE_DISPONIVEL_KG - PREVISTO_CONFIRMADO_KG <= 0`) gera `CRITICO`.
