# Automacao - Montagem de Terceirizados (v2.0 - Pure-Native) ⚙️

[⬅️ Voltar para o Hub Central](../README.md)

## Visao Geral

Este projeto automatiza a validacao fiscal deterministica de ordens de montagem externa. O foco e garantir o cruzamento preciso entre Notas Fiscais (NF) e Ordens de Fabricacao (OBs) de terceirizados, notificando divergencias a equipe fiscal de forma proativa atraves de uma interface moderna e inteligente.

A versao 2.0 marca a migracao definitiva para a **Arquitetura Pure-Native**, eliminando totalmente as dependencias de Excel/VBA e utilizando queries SQL de alta performance otimizadas via CTEs.

## Fluxo de Execucao (Modo Nativo)

`Orchestrator` -> `run.ps1` (shim) -> `run_montagem.py` (orquestra, sobre `lib/python/hub_runner.py`)
  -> **Fase 1 (Extracao)**: `extract_oracle.py` extrai do Oracle o SQL `SQL-MontagemTerceirizados.sql` e grava `.data_<ExecId>.json`.
  -> **Fase 2 (Inteligencia)**: `validate_and_generate_html.py` valida os dados, aplica regras de negocio e grava `.payload_<ExecId>.json`.
  -> **Fase 3 (Entrega)**: `run_montagem.py` envia o e-mail pela CLI `lib/Invoke-OutlookEmail.ps1` (Outlook COM), com idempotencia por hash do payload. A CLI repassa `-Cc` e `-PreviewOnly` a `Send-OutlookEmail`.

---

## Arquitetura de Componentes

### 1. Orquestrador Python (`run_montagem.py`)
Gerencia o fluxo sobre o runner compartilhado `lib/python/hub_runner.py`: pre-flight (disco, paths e check Oracle), lock global `MT-02`, extract (3 tentativas), transform (2 tentativas), dispatch por e-mail e commit do cache de erros. Fecha toda execucao com o evento de fim e a telemetria.

`run.ps1` agora e um **shim**: resolve o interpretador do projeto, chama `run_montagem.py`, repassa o `ExecId`, o `-DryRun` e os switches de e-mail do run.ps1 antigo (`-EmailPreviewOnly`, `-EmailToTest`, `-EmailCcTest`) e sai com o mesmo exit code, porque o worker do Orchestrator le o exit code de `powershell.exe -File run.ps1`.

Modo teste: `ORCHESTRATOR_TEST_MODE` vence; sem ele, `-EmailToTest` ou o `AUTOMACAO_TEST_EMAIL` do escopo User (registro do Windows) redirecionam o envio, como no run.ps1 antigo.

Execucao manual de validacao (nao usar em producao; nao envia e-mail nem confirma o estado; pega o lock `MT-02`):

```powershell
.venv\Scripts\python.exe "Montagem de Terceirizados\run_montagem.py" VALIDACAO_MANUAL_0001 --dry-run
```

### 2. Camada de Dados e Inteligencia
- **`SQL-MontagemTerceirizados.sql`**: Query ultra-otimizada utilizando CTEs (Common Table Expressions) e agregados de I/O reduzido. Substitui a dependencia da View lenta do Oracle.
- **`extract_oracle.py`**: Extrator nativo que carrega dinamicamente o SQL externo.
- **`validate_and_generate_html.py`**: Nucleo de validacao. Implementa idempotencia (cache `.cache_erros.json`), calcula a quantidade de pecas vinculadas a NF incorreta em cada OB e gera o dashboard visual com cards e destaques de erro.
- **Placa kanban no e-mail**: quando a extracao retornar `NR_KANBAN`, o HTML da notificacao passa a exibir a placa por OB nas tabelas resumida e detalhada para acelerar a triagem operacional.

---

## Operacao e Diagnostico

### Logs e Auditoria
- **Localizacao**: `Logs/Montagem_Terceirizados_...log`.
- **Rastreabilidade**: Todas as fases sao correlacionadas pelo `ExecId` unico.
- **PT-BR Blindado**: Mensagens de log em codigo-fonte sao ASCII-Safe, convertidas em tempo de execucao via Base64.

### Performance
A migracao para o modo nativo reduziu o tempo de execucao de minutos (via Excel COM) para **segundos** (via Python/cx_Oracle), eliminando falhas de interface e deadlocks de processos do Office.

---

## Regras de Negocio Criticas
1. **Idempotencia**: O sistema utiliza cache de estado para enviar alertas apenas quando surgem novos erros ou mudancas significativas.
2. **Filtros de Producao**: A automacao foca exclusivamente em OBs Montadas (Setor 5), com Destino Receita 1 e Programacao do tipo `%T`.
3. **Quantidade para Expedicao**: Os e-mails de divergencia informam quantas pecas estao ligadas a NF incorreta na montagem, permitindo retirada fisica precisa por OB.

---

## 🧠 Gestão de Contexto (AI-Native)
Este arquivo é o mapa cognitivo local do robô de Montagem de Terceirizados.
- **Obrigação**: Deve ser atualizado após mudanças nas regras fiscais de validação NF vs OB, na query SQL otimizada, no `Secure File-Payload Protocol` ou na lógica de idempotência.
- **Sincronismo**: Garante que a IA compreenda a transição Legacy -> Pure-Native e a lógica de cache de erros em JSON.
- **Objetivo**: Manter a IA ciente da arquitetura "Pure-Native" e da ausência de dependências de interface COM.
- **Atualização 17/05/2026**: A notificacao agora destaca, por OB e no resumo do e-mail, a quantidade de pecas vinculadas a NF incorreta na montagem a partir de `QT_PC_NF`.
- **Atualização 17/05/2026**: A extracao Python direta passou a usar `load_dotenv(..., override=True)` para garantir que o `.env` do repositorio prevaleca sobre variaveis stale da sessao local, alinhando a execucao manual ao contrato do Orchestrator.
- **Atualização 07/06/2026**: O e-mail de divergencias passou a expor a placa kanban (`NR_KANBAN`) por OB quando disponivel, com fallback visual `N/A` quando o Oracle nao retornar placa.
