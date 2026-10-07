# AVISO DE SEGURANÇA OPERACIONAL — SCRIPTS DML RESTRITOS

> [!CAUTION]
> **ZONA DE SEGURANÇA MÁXIMA — OPERAÇÕES MUTÁVEIS EM BANCO DE DADOS ORACLE DE PRODUÇÃO**
> Os scripts contidos nesta pasta realizam operações de `UPDATE` ou modificação em tabelas centrais do ERP SGT/TOTVS (`SGTPRD.OB_FASES`, `SGTPRD.OB_QUALIDADE`, `SGTPRD.GRUPO_FLUXO_MAQUINAS`, `SGTPRD.GRUPO_FLUXO_FASES`).

---

## Regras Obrigatórias de Execução

Em conformidade com a skill canônica `oracle-sql` e o contrato compartilhado em `AGENTS.md`:

1. **Aprovação Humana Prévia e Explícita**:
   - Nenhum script desta pasta pode ser disparado por agentes de IA ou por automações sem que o operador humano autorize explicitamente a execução e confirme os parâmetros.
2. **SELECT de Conferência Prévia**:
   - Antes de qualquer comando `UPDATE`, execute o `SELECT` correspondente com o mesmo filtro `WHERE` para auditar a quantidade exata e o conteúdo atual das linhas afetadas.
3. **Transação Manual com ROLLBACK Preparado**:
   - **NUNCA execute em modo autocommit**.
   - Abra a transação explicitamente.
   - Após o comando, confira o `SQL%ROWCOUNT`. Se divergir da quantidade esperada, emita `ROLLBACK;` imediatamente.
   - Somente após conferência visual execute `COMMIT;`.
4. **Registro de Auditoria**:
   - Todo ajuste em dados de chão de fábrica deve estar associado a um chamado ou solicitação de engenharia/qualidade, registrando data, autor, OBs e valores alterados.

---

## Scripts Contidos nesta Pasta:

- `dml_alterar_grupo_de_programacao_pontos_de_controle.sql`: `SELECT` de conferência + `UPDATE` dos valores do ponto de controle em `BENEPTSCONTGRUFLUMAQ` (mesmo filtro nos dois).
- `dml_alterar_grupos_e_tipos_de_defeitos_ob_qualidade_ob_fases.sql`: série de `UPDATE`s de grupo/tipo de defeito em `OB_FASES` e `OB_QUALIDADE`.
- `dml_update_engenharia_grupos_de_programacao.sql`: ajusta a velocidade de máquinas em `GRUPO_FLUXO_MAQUINAS`.
- `dml_update_grupo_de_programacoes___observacoes_da_fase.sql`: ajusta observações de fases em `GRUPO_FLUXO_FASES`.

> **Exceção à atomicidade:** estes são roteiros de manutenção executados manualmente, passo a passo, e podem conter mais de uma instrução (conferência + `UPDATE`s). A regra "1 consulta por arquivo" vale para as pastas de consulta (`01`–`11`, `13`). Nenhum validador automatizado executa esta pasta.
