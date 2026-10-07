# Acervo de Consultas SQL (ERP SGT)

Consultas analíticas e operacionais sobre o ERP SGT (schema `SGTPRD`, Oracle), organizadas por processo têxtil, com **1 consulta por arquivo** e encoding **UTF-8 sem BOM**.

O inventário completo (arquivo, objetivo, binds e último status de validação no Oracle) está em [`CATALOGO_QUERIES.md`](CATALOGO_QUERIES.md), **gerado** por `Tools/oracle/gerar_catalogo_sql.py` a partir dos próprios arquivos e da evidência do validador (`validacao_status.json`) — não edite à mão, e não repita contagens ou status em outros documentos.

> **Confiabilidade:** só as consultas marcadas ✅ no catálogo passaram por guard + parse + execução no Oracle e valem como referência canônica. As demais são **inventário não validado**: leia a regra antes de copiar o SQL, e valide (fluxo abaixo) antes de promovê-lo a referência.

## Dono, localização e promoção

- **Dono do acervo:** é material de **referência central** sobre o ERP, não código de uma automação. Por isso vive ao lado do catálogo do schema (`docs/oracle-schema/`), que é por onde os agentes começam (skill `oracle-schema-navigator`).
- **Dono do SQL de runtime:** a automação que o executa. O SQL que o runner do Beneficiamento lê é [`Produção Beneficimento/sql/templates/bnf_producao_beneficiamento_detalhado.sql`](../../../Produção%20Beneficimento/sql/templates/bnf_producao_beneficiamento_detalhado.sql); ele **não** está nesta pasta, para que consolidar, renomear ou arquivar o acervo nunca quebre produção.
- **Regra de promoção:** quando uma consulta do acervo vira runtime de uma automação, ela é **movida** (`git mv`) para a pasta da automação e este README ganha um ponteiro. Nunca se copia: duas cópias divergem.
- **Pastas `01_` a `13_`:** as chaves de `validacao_status.json` são relativas a esta pasta e o hash é do conteúdo normalizado, então a evidência de validação sobrevive a mudanças de local sem reconsultar o Oracle.

## Fonte canônica das regras de negócio

As regras de negócio verificadas no Oracle (status, épocas de data, chaves, definições, divergências conhecidas) têm **uma** fonte: [`REGRAS_NEGOCIO.md`](REGRAS_NEGOCIO.md). Os cabeçalhos dos `.sql` e as skills `oracle-sql-patterns`/`oracle-schema-navigator` **apontam** para ele em vez de repetir valores; se uma regra mudar, corrija lá e confira os cabeçalhos que a citam.

## Estrutura

| Pasta | Domínio | Conteúdo |
|:---|:---|:---|
| [`01_beneficiamento_tingimento/`](01_beneficiamento_tingimento/) | Tinturaria e Beneficiamento | Máquinas de tingimento, receitas, relação de banho, químicos, painel de tingimento e status de OBs. |
| [`02_acabamento_preparacao/`](02_acabamento_preparacao/) | Acabamento | Ramas (RM01/RM02), tubulares, felpadeiras, embaladeiras e ordens de manutenção. |
| [`03_malharia_teares/`](03_malharia_teares/) | Malharia | Eficiência de teares, finura, necessidades, estoque por agulha/tear e faltas/sobras. |
| [`04_fiacao_fios/`](04_fiacao_fios/) | Fiação | Lotes de fios, cones, fio Vórtex, resíduos e estoque de fibras/fios. |
| [`05_estoque_armazenagem/`](05_estoque_armazenagem/) | Estoque e Depósitos | Saldos por depósito, transferências, malha crua e pesagens. |
| [`06_qualidade_auditoria_obs/`](06_qualidade_auditoria_obs/) | Qualidade e Auditoria | Ciclo de NF de entrada, peças restritas, pesos fora de padrão, SKU e testes de qualidade. |
| [`07_expedicao_pedidos_comercial/`](07_expedicao_pedidos_comercial/) | Comercial e Expedição | Carteira, pedidos atrasados, romaneios, OB → Romaneio → NF-e, preços e lojas. |
| [`08_faccao_terceirizacao/`](08_faccao_terceirizacao/) | Facção e Terceiros | Remessa/retorno, saldo de NFs de terceiros e estamparia. |
| [`09_pcp_kpis_gestao/`](09_pcp_kpis_gestao/) | PCP e Indicadores | Sincronismo malha × ribana, TOP 5, produção por fase/turno e calendário. |
| [`10_engenharia_custos/`](10_engenharia_custos/) | Engenharia e Custos | Ficha técnica, composição, custo de matéria-prima e pesos padrão. |
| [`11_views_referencia_sgt/`](11_views_referencia_sgt/) | Referência | DDL de views do SGT, para consulta e conferência. **Não executadas** pelos validadores. |
| [`12_manutencao_dml_restrito/`](12_manutencao_dml_restrito/) | DML restrito | Roteiros manuais de `UPDATE`. Leia [`AVISO_SEGURANCA.md`](12_manutencao_dml_restrito/AVISO_SEGURANCA.md) antes de qualquer uso. |
| [`13_utilitarios_snippets/`](13_utilitarios_snippets/) | Utilitários | Padrões de sintaxe Oracle (`LISTAGG`, datas seriais do SGT), dicionário e permissões. |

O SQL de runtime do Beneficiamento (`bnf_producao_beneficiamento_detalhado.sql`) é **código de produção** e fica em `Produção Beneficimento/sql/templates/`: o runner (`src/beneficiamento/settings.py`) o executa a cada refresh do dashboard, e mudanças nele alteram os snapshots e o histórico SQLite. Não o mova nem renomeie sem ajustar `settings.SQL_TEMPLATE_DIR`/`_PERIOD_CONFIGS`: `Orchestrator/tests/test_beneficiamento_sql_template_unit.py` falha se o caminho configurado deixar de existir. Ele não consta do catálogo deste acervo.

## Fluxo de validação

Todos os comandos a partir da raiz do repositório, com o `.venv` do projeto.

```powershell
# 1. Guard + parse + execução limitada (FETCH FIRST 1) no Oracle real.
#    Exit 0 só se todos os arquivos saírem `validated`/`parse_ok`.
.venv\Scripts\python Tools\oracle\validar_sql_oracle.py --out <saida.json>
.venv\Scripts\python Tools\oracle\validar_sql_oracle.py --file "docs\oracle-schema\consultas\<pasta>\<arquivo>.sql" --out <saida.json>

# 2. Incorporar a evidência e regerar o catálogo.
.venv\Scripts\python Tools\oracle\gerar_catalogo_sql.py --evidencia <saida.json>

# 3. Antes do PR: falha se o catálogo não refletir o disco.
.venv\Scripts\python Tools\oracle\gerar_catalogo_sql.py --check
```

- Cadeia do guard: **validador → `Tools/oracle/guard_sql.py` (wrapper versionado, aceita CTE com lista de colunas `WITH x (a) AS (...)`) → `guard_sql.py` canônico da skill `oracle-sql`** (instalada em `%USERPROFILE%\.gemini\antigravity\skills\oracle-sql\scripts\`, fora do repositório). `ORACLE_SQL_GUARD` troca o guard inteiro. Se o wrapper ou o canônico estiver ausente, o validador falha (`SystemExit`) em vez de marcar as consultas como `blocked_guard`.
- `Tools/oracle/validar_sql_oracle.py` grava o JSON de evidência com o comando relativo à raiz (sem caminho da máquina). Saídas soltas vão em `Tools/evidencias/` (ignorada pelo git).
- Regressão do PCP mensal: `Orchestrator/tests/test_consultas_pcp_producao_mensal_regression.py`. A parte offline (invariantes sobre a baseline, janela fixa, comparação) roda no CI; a parte que consulta o Oracle de produção só roda com `BENEFICIAMENTO_LIVE_ORACLE=1`.
- `est_posicao_acumulada_estoque_total.sql` não passa no smoke de 1 linha: a sessão é derrubada (`DPY-1001`) antes do primeiro resultado, **igual antes e depois** de trocar o `SELECT *` por colunas (conferido nas duas versões em 06/10/2026). É limite da consulta pesada sob o perfil de recursos do Oracle, não regressão; segue ⬜ no catálogo.
- O wrapper `Tools/oracle/guard_sql.py` libera `WITH x (a) AS (SELECT 1 FROM DUAL) SELECT a FROM x` com o guard canônico real (`test_wrapper_libera_cte_com_lista_de_colunas_no_canonico_real`; é pulado nas máquinas sem a skill `oracle-sql`).
- `ORA-00028`/`DPY-4011` (sessão cancelada pelo perfil de recurso do Oracle) é falha de execução, não sucesso — rode de novo a consulta isolada.
- Consultas pesadas podem ter os trechos críticos conferidos por `Tools/oracle/validar_partes_oracle.py`.
- Reescrita que precisa provar equivalência com a versão anterior: `Tools/oracle/comparar_equivalencia.py` (exige `--chaves` ou `--metricas`).

### Custo real, equivalência e auditoria

O validador só lê 1 linha. Para medir o custo do resultado inteiro e provar que uma mudança não alterou a saída:

```powershell
# 1. Baseline: fetch completo, mediana de 5 execuções (conexão nova em cada), resultado gravado
.venv\Scripts\python Tools\oracle\medir_sql_oracle.py "docs\oracle-schema\consultas\<pasta>\<arquivo>.sql" --runs 5 --dump base.json --out base.report.json

# 2. Depois da alteração: mesma medição; --baseline decide MELHORA / NEUTRO / PIOR (ganho acima do ruído e de 2%)
.venv\Scripts\python Tools\oracle\medir_sql_oracle.py "docs\oracle-schema\consultas\<pasta>\<arquivo>.sql" --runs 5 --dump nova.json --baseline base.report.json

# 3. Mesma saída? (a chave é a do GRÃO do cabeçalho)
.venv\Scripts\python Tools\oracle\comparar_equivalencia.py --controle base.json --candidata nova.json --chaves NUMERO_OB

# 4. Varredura do acervo inteiro: FALHA, INSTAVEL, LENTA (> 3 s), VAZIA, TETO_ATINGIDO, LINHAS_INSTAVEIS
.venv\Scripts\python Tools\oracle\auditar_acervo_sql.py --out varredura.json
```

- O usuário de leitura **não enxerga** `V$SQL`, `V$MYSTAT` nem `DBMS_XPLAN.DISPLAY_CURSOR` (ORA-00942): não há `buffer_gets`. A métrica é o tempo de parede do fetch completo e `--explain` (plano estimado) é só hipótese.
- A rede derruba sessões em ~4 a 6 s (`ORA-00028`, `DPY-1001`). Meta prática por consulta: fetch completo abaixo de 3 s. O medidor repete em queda de rede, com conexão nova.
- **`VAZIA` não é aprovação.** Uma consulta de anomalia que devolve 0 linhas pode estar saudável ou com o filtro quebrado (`qld_ob_s_com_peso_menor_que_8kg` "estava vazia" por época de data errada e escondia 58 OBs). Só a leitura da regra e uma variante relaxada que retorne linhas decidem.
- Regras de negócio verificadas no Oracle (status, épocas de data, chaves, definições) e as divergências conhecidas: [`REGRAS_NEGOCIO.md`](REGRAS_NEGOCIO.md).

## Regras para novas consultas

1. **Atomicidade:** exatamente uma consulta por arquivo nas pastas de consulta. Exceção: roteiros de `12_manutencao_dml_restrito/`.
2. **Nome:** `snake_case`, sem acentos, com o prefixo da pasta (`bnf_`, `acb_`, `mal_`, `fia_`, `est_`, `qld_`, `com_`, `fac_`, `pcp_`, `eng_`, `vw_`, `dml_`, `util_`).
3. **Cabeçalho:** `OBJETIVO:` (vira a descrição no catálogo), `DOMÍNIO:`, `TIPO:` (vira a categoria), `PARÂMETROS / BINDS:` e `TABELAS PRINCIPAIS:`. Em consulta nova, acrescente `GRÃO:` (a chave que torna cada linha única; é a que vai em `--chaves` do comparador) e use um destes `TIPO:`: `Monitoramento operacional`, `Painel/KPI`, `Auditoria/Sentinela`, `Conferência pontual`, `Cadastro/Referência` ou `Snippet/Utilitário`. Os arquivos antigos ainda têm ~30 valores de `TIPO:` misturando assunto e tipo de instrução; a normalização deles depende de decisão da área.
4. **Sem `SELECT *`** (bloqueado pelo pre-commit, `Tools/Test-SqlPerformance.ps1`) e sem `/` sozinho numa linha (o SQL*Plus executa o buffer).
5. **Somente leitura fora da pasta 12:** `UPDATE`/`DELETE`/`INSERT`/`MERGE` só em `12_manutencao_dml_restrito/`, com o protocolo de `AVISO_SEGURANCA.md`.
6. **Encoding:** UTF-8 sem BOM.
7. **Datas seriais e status:** siga [`REGRAS_NEGOCIO.md`](REGRAS_NEGOCIO.md). `OB.TEMPO_*` = minutos desde 01/01/1996; `UNIDADE_PROGRAMACAO.TEMPO*` = dias desde 30/12/1899. Não converta a coluna no `WHERE` (`TRUNC`, `TO_CHAR`, `TRIM`): compare com um limite no mesmo formato.
8. **Divisão:** sempre `x / NULLIF(y, 0)`.
9. **Teto de linhas:** `FETCH FIRST N ROWS ONLY` em consulta de auditoria trunca anomalias em silêncio; se usar, declare no cabeçalho (o auditor marca `TETO_ATINGIDO`).

O histórico das rodadas de revisão e otimização está no [`CHANGELOG.md`](../../CHANGELOG.md) (entradas 1.3.99 em diante).
