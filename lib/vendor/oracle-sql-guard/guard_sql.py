#!/usr/bin/env python3
"""guard_sql.py — classifica SQL Oracle ANTES de enviar ao MCP (execute_sql).

A ferramenta `execute_sql` do MCP oracledb executa QUALQUER instrução. Este
script é a trava determinística: só leitura passa; o resto exige checkpoint.

Uso:
    python guard_sql.py --sql "SELECT ..." [--exigir-limite]
    python guard_sql.py --arquivo consulta.sql
    Get-Content consulta.sql | python guard_sql.py            (stdin)

No PowerShell use aspas SIMPLES em --sql (aspas duplas expandem $: v$version vira "v")
ou prefira --arquivo.
    python guard_sql.py --hook                                 (PreToolUse do Antigravity; ver references/hook-opcional.md)

Saída: JSON {"classe", "permitido", "motivos", "avisos", "instrucoes",
"verificar_objetos", "consulta_verificacao"}. Quando houver `consulta_verificacao`,
rode-a (é leitura) antes da primeira execução da consulta: se retornar linhas,
algum nome é FUNÇÃO/PACOTE/TIPO (função sem argumentos dispensa parênteses) →
trate como checkpoint humano.
Exit: 0 = leitura permitida | 3 = exige checkpoint humano (não executar) | 1 = entrada inválida.

Limitações conhecidas (mitigadas pelo protocolo da skill, não pelo script):
- função sem argumentos escrita sem parênteses → use `consulta_verificacao`;
- VIEW que chama função com efeito colateral não é detectável pelo texto da
  consulta → privilégios do usuário no banco são a barreira final. Somente biblioteca padrão.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

DML = {"INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT"}
DDL = {"CREATE", "ALTER", "DROP", "TRUNCATE", "RENAME", "COMMENT", "GRANT", "REVOKE",
       "PURGE", "FLASHBACK", "ANALYZE", "AUDIT", "NOAUDIT", "ASSOCIATE", "DISASSOCIATE"}
PLSQL = {"BEGIN", "DECLARE", "CALL", "EXEC", "EXECUTE"}
TRANSACAO = {"COMMIT", "ROLLBACK", "SAVEPOINT", "SET", "LOCK"}
LEITURA = {"SELECT", "WITH"}
# Chamadas que saem do banco, gravam ou executam código: bloqueiam (exigem checkpoint).
PACOTES_SENSIVEIS = re.compile(r"\b(DBMS_\w+|UTL_\w+|OWA_\w+|APEX_\w+|HTP|\w*URITYPE|XMLTYPE|XMLPARSE|BFILENAME|SYS)\b", re.I)
# Funções nativas de leitura aceitas sem qualificação. Qualquer outra "nome(" bloqueia:
# pode ser função do usuário com efeito colateral (PRAGMA AUTONOMOUS_TRANSACTION).
FUNCOES_NATIVAS = frozenset("""
ABS ACOS ADD_MONTHS APPROX_COUNT_DISTINCT ASCII ASCIISTR ASIN ATAN ATAN2 AVG BIN_TO_NUM BITAND CARDINALITY CAST CEIL
CHARTOROWID CHR COALESCE COLLECT CONCAT CONVERT CORR COS COSH COUNT COVAR_POP COVAR_SAMP CUME_DIST CURRENT_DATE
CURRENT_TIMESTAMP DBTIMEZONE DECODE DENSE_RANK DUMP EMPTY_BLOB EMPTY_CLOB EXP EXTRACT FIRST_VALUE FLOOR FROM_TZ
GREATEST GROUPING GROUPING_ID GROUP_ID HEXTORAW INITCAP INSTR INSTRB JSON_ARRAY JSON_ARRAYAGG JSON_OBJECT
JSON_OBJECTAGG JSON_QUERY JSON_TABLE JSON_VALUE LAG LAST_DAY LAST_VALUE LEAD LEAST LENGTH LENGTHB LISTAGG LN
LNNVL LOCALTIMESTAMP LOG LOWER LPAD LTRIM MAX MEDIAN MIN MOD MONTHS_BETWEEN NANVL NEW_TIME NEXT_DAY NLSSORT
NLS_INITCAP NLS_LOWER NLS_UPPER NTH_VALUE NTILE NULLIF NUMTODSINTERVAL NUMTOYMINTERVAL NVL NVL2 ORA_HASH
PERCENTILE_CONT PERCENTILE_DISC PERCENT_RANK POWER RANK RATIO_TO_REPORT RAWTOHEX REGEXP_COUNT REGEXP_INSTR
REGEXP_LIKE REGEXP_REPLACE REGEXP_SUBSTR REMAINDER REPLACE ROUND ROWIDTOCHAR ROW_NUMBER RPAD RTRIM SESSIONTIMEZONE
SIGN SIN SINH SOUNDEX SQRT STANDARD_HASH STDDEV STDDEV_POP STDDEV_SAMP SUBSTR SUBSTRB SUM SYSDATE SYSTIMESTAMP
SYS_CONTEXT SYS_EXTRACT_UTC SYS_GUID TAN TANH TO_BINARY_DOUBLE TO_BINARY_FLOAT TO_CHAR TO_CLOB TO_DATE
TO_DSINTERVAL TO_LOB TO_MULTI_BYTE TO_NCHAR TO_NCLOB TO_NUMBER TO_SINGLE_BYTE TO_TIMESTAMP TO_TIMESTAMP_TZ
TO_YMINTERVAL TRANSLATE TRIM TRUNC TZ_OFFSET UID UNISTR UPPER USER USERENV VARIANCE VAR_POP VAR_SAMP VSIZE
WIDTH_BUCKET XMLAGG XMLELEMENT XMLFOREST XMLSERIALIZE
""".split())
# Palavras reservadas/estruturais que nunca são objetos do usuário.
PALAVRAS_SQL = frozenset("""
SELECT FROM WHERE AND OR NOT IN IS NULL AS ON JOIN INNER LEFT RIGHT FULL OUTER CROSS NATURAL USING GROUP BY ORDER
HAVING UNION ALL INTERSECT MINUS DISTINCT UNIQUE CASE WHEN THEN ELSE END EXISTS BETWEEN LIKE ESCAPE WITH FETCH FIRST
NEXT ROWS ROW ONLY OFFSET ASC DESC NULLS LAST ROWNUM ROWID LEVEL PRIOR CONNECT START NOCYCLE OVER PARTITION RANGE
UNBOUNDED PRECEDING FOLLOWING CURRENT KEEP DENSE_RANK WITHIN SAMPLE SEED DUAL DATE TIMESTAMP INTERVAL YEAR MONTH
DAY HOUR MINUTE SECOND TO ZONE LOCAL AT PIVOT UNPIVOT FOR ANY SOME TRUE FALSE PERCENT TIES SIBLINGS LATERAL APPLY
TABLE QID LIKE2 LIKE4 LIKEC REGEXP MATCH_RECOGNIZE MEASURES PATTERN DEFINE ONE PER MATCH SKIP PAST AFTER
""".split())
# Palavras-chave que legitimamente precedem "(".
PALAVRAS_ANTES_DE_PARENTESE = frozenset("""
AS IN EXISTS NOT AND OR ON USING FROM JOIN SELECT WHERE BY OVER KEEP WITHIN GROUP PIVOT UNPIVOT VALUES SAMPLE SEED
ANY ALL SOME THEN ELSE WHEN CASE BETWEEN LIKE DISTINCT PRIOR LATERAL APPLY TABLE PARTITION SUBPARTITION FOR
HAVING UNION INTERSECT MINUS EXCEPT RETURNING MEASURES PATTERN DEFINE DIMENSION RULES MODEL NULLS IS OF
MATCH_RECOGNIZE CONNECT START WITH ORDER SET NUMBER VARCHAR2 VARCHAR CHAR NCHAR NVARCHAR2 RAW TIMESTAMP INTERVAL
FLOAT DECIMAL INTEGER DATE ESCAPE QID
""".split())
# Leituras de pacotes comprovadamente sem efeito colateral.
PERMITIDOS = re.compile(r"\bDBMS_XPLAN\s*\.\s*DISPLAY\w*\s*\(|\bDBMS_METADATA\s*\.\s*GET_\w+\s*\(", re.I)
CHAMADA_QUALIFICADA = re.compile(r"\b[A-Za-z_][\w$#]*\s*\.\s*[A-Za-z_][\w$#]*(\s*\.\s*[A-Za-z_][\w$#]*)?\s*\(")
# GROUPING SETS (Oracle 9i+) é cláusula do GROUP BY, não chamada: sem esta troca o laço de
# chamadas lê "SETS(" como função desconhecida. Só "GROUP BY GROUPING SETS (" vira
# "GROUP BY (": as duas palavras saem da análise e a lista de conjuntos segue normalmente.
# Roda sobre o texto já sem literais e comentários, então nunca casa dentro de string.
GROUPING_SETS = re.compile(r"(?<![\w$#.])(GROUP\s+BY\s+)GROUPING\s+SETS\s*\(", re.I)




def _fim_linha(sql: str, i: int) -> int:
    """Índice onde termina o comentário de linha iniciado em `i` (fim do texto se não houver quebra)."""
    fim = sql.find("\n", i)
    return len(sql) if fim == -1 else fim


def _fim_bloco(sql: str, i: int) -> int:
    """Índice logo após o `*/` que fecha o comentário de bloco iniciado em `i`."""
    fim = sql.find("*/", i + 2)
    if fim == -1:
        raise ValueError("comentário /* sem fechamento")
    return fim + 2


def _consumir_prefixo(sql: str, i: int) -> tuple[str, int] | None:
    """Trata os prefixos `nq'` (descarta o N) e `u&'` (descarta o &).

    Devolve o texto e a posição ajustados, ou None quando não há prefixo.
    """
    if i + 2 < len(sql) and sql[i] in "nN" and sql[i + 1] in "qQ" and sql[i + 2] == "'":
        return sql, i + 1
    if sql[i] in "uU" and sql.startswith("&'", i + 1):
        return sql[: i + 1] + sql[i + 2 :], i + 1
    return None


def _fim_literal_q(sql: str, i: int) -> int:
    """Índice da aspa final do literal q'...' iniciado em `i`, conforme o delimitador escolhido."""
    abre = sql[i + 2]
    fecha = {"[": "]", "{": "}", "(": ")", "<": ">"}.get(abre, abre)
    fim = sql.find(fecha + "'", i + 3)
    if fim == -1:
        raise ValueError("literal q'...' sem fechamento")
    return fim


def _fim_texto(sql: str, i: int) -> int:
    """Índice da aspa que fecha o literal de texto aberto em `i` (aspa dupla é escape)."""
    n = len(sql)
    j = i + 1
    while True:
        j = sql.find("'", j)
        if j == -1:
            raise ValueError("literal de texto sem fechamento")
        if j + 1 < n and sql[j + 1] == "'":
            j += 2
            continue
        return j


def _fim_identificador(sql: str, i: int) -> int:
    """Índice da aspa que fecha o identificador entre aspas duplas iniciado em `i`."""
    fim = sql.find('"', i + 1)
    if fim == -1:
        raise ValueError("identificador entre aspas sem fechamento")
    return fim


def remover_literais_e_comentarios(sql: str, citados: list[str] | None = None) -> str:
    """Troca literais por '' e identificadores entre aspas por QID (guardando o
    nome em `citados`), remove comentários e preserva a estrutura."""
    saida: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        if sql.startswith("--", i):
            i = _fim_linha(sql, i)
            continue
        if sql.startswith("/*", i):
            i = _fim_bloco(sql, i)
            saida.append(" ")
            continue
        inicio_token = i == 0 or not (sql[i - 1].isalnum() or sql[i - 1] in "_$#")
        if inicio_token and c in "nNuU":
            prefixo = _consumir_prefixo(sql, i)
            if prefixo is not None:
                sql, i = prefixo
                n = len(sql)
                c = sql[i]
        if c in "qQ" and i + 2 < n and sql[i + 1] == "'" and (inicio_token or sql[i - 1] in "nN"):
            i = _fim_literal_q(sql, i) + 2
            saida.append("''")
            continue
        if c == "'":
            i = _fim_texto(sql, i) + 1
            saida.append("''")
            continue
        if c == '"':
            fim = _fim_identificador(sql, i)
            if citados is not None:
                citados.append(sql[i + 1 : fim])
            saida.append("QID")
            i = fim + 1
            continue
        saida.append(c)
        i += 1
    return "".join(saida)


def _nivel_externo(texto: str) -> str:
    """Remove o conteúdo entre parênteses, deixando só a consulta de nível 0."""
    saida: list[str] = []
    profundidade = 0
    for caractere in texto:
        if caractere == "(":
            profundidade += 1
        elif caractere == ")":
            profundidade = max(0, profundidade - 1)
        elif profundidade == 0:
            saida.append(caractere)
    return "".join(saida)


def _bloquear(resultado: dict[str, Any], classe: str, permitido: bool = False) -> None:
    """Marca bloqueio preservando a primeira classe bloqueante encontrada."""
    if resultado["classe"] in ("leitura", "multiplas"):
        resultado["classe"] = classe
    resultado["permitido"] = permitido


def _contar_argumentos(texto: str, abre: int) -> int:
    """Conta os argumentos da chamada cujo '(' está em `abre`, ignorando vírgulas aninhadas."""
    profundidade, argumentos = 0, 1
    for caractere in texto[abre:]:
        if caractere == "(":
            profundidade += 1
        elif caractere == ")":
            profundidade -= 1
            if profundidade == 0:
                break
        elif caractere == "," and profundidade == 1:
            argumentos += 1
    return argumentos


def normalizar_grouping_sets(texto: str) -> str:
    """Troca 'GROUP BY GROUPING SETS (' por 'GROUP BY (' e mais nada (ver GROUPING_SETS)."""
    return GROUPING_SETS.sub(r"\1(", texto)


def _separar_instrucoes(limpo: str, corpo_plsql: bool) -> list[str]:
    """Divide o texto em instruções pelo `;`. Blocos PL/SQL e DDL com corpo ficam inteiros."""
    if corpo_plsql:
        return [limpo.strip().rstrip("/").strip()]
    return [parte.strip() for parte in re.split(r";|^\s*/\s*$", limpo, flags=re.M) if parte.strip()]


def _checar_bloqueios_de_leitura(
    primeira: str, upper: str, resultado: dict[str, Any]
) -> None:
    """Bloqueios de uma consulta SELECT/WITH: FOR UPDATE, WITH FUNCTION e DML disfarçado."""
    if re.search(r"\bFOR\s+UPDATE\b", upper):
        _bloquear(resultado, "bloqueio")
        resultado["motivos"].append("SELECT ... FOR UPDATE trava linhas")
    if primeira == "WITH" and re.match(r"WITH\s+(FUNCTION|PROCEDURE)\b", upper.strip()):
        _bloquear(resultado, "plsql")
        resultado["motivos"].append("WITH FUNCTION/PROCEDURE executa PL/SQL")
    if re.search(r"\b(INSERT|UPDATE|DELETE|MERGE)\b", upper) and not re.search(r"\bFOR\s+UPDATE\b", upper):
        _bloquear(resultado, "mutacao")
        resultado["motivos"].append("palavra-chave de DML dentro de consulta")


def _checar_chamadas(instrucao: str, citados: list[str], resultado: dict[str, Any]) -> None:
    """Chamadas de função, pacote ou tipo capazes de efeito colateral ou de rede."""
    for dis in re.finditer(r"\bDBMS_XPLAN\s*\.\s*DISPLAY\w*\s*\(", instrucao, re.I):
        if _contar_argumentos(instrucao, dis.end() - 1) >= 4:
            _bloquear(resultado, "chamada_sensivel")
            resultado["motivos"].append("DBMS_XPLAN.DISPLAY com 4º argumento (filter_preds) executa SQL dinâmico")
            break
    sem_permitidos = PERMITIDOS.sub(" ", instrucao)
    sensiveis = {m.group(1).upper() for m in PACOTES_SENSIVEIS.finditer(sem_permitidos)}
    sensiveis |= {c.upper() for c in citados if PACOTES_SENSIVEIS.fullmatch(c.strip())}
    if sensiveis:
        _bloquear(resultado, "chamada_sensivel")
        resultado["motivos"].append(f"pacote/tipo capaz de rede, escrita ou execução: {sorted(sensiveis)}")
    if CHAMADA_QUALIFICADA.search(sem_permitidos) or (
        citados and re.search(r"QID\s*\.\s*(QID|[A-Za-z_]\w*)\s*\(", sem_permitidos)
    ):
        _bloquear(resultado, "chamada_funcao")
        resultado["motivos"].append("chamada a função/procedimento de pacote ou schema (pode ter efeito colateral, ex.: autonomous transaction)")
    for chamada in re.finditer(r"(?<![\w$#.])([A-Za-z_][\w$#]*)\s*\(", sem_permitidos):
        nome_funcao = chamada.group(1).upper()
        if nome_funcao not in FUNCOES_NATIVAS and nome_funcao not in PALAVRAS_ANTES_DE_PARENTESE:
            _bloquear(resultado, "chamada_funcao")
            resultado["motivos"].append(
                f"função não reconhecida como nativa de leitura: {nome_funcao}( — pode ser função do usuário com efeito colateral"
            )
            break
    if re.search(r"\bTABLE\s*\(\s*(?!\()(?!SELECT\b)(?!CAST\b)[A-Za-z_\"]", sem_permitidos, re.I):
        _bloquear(resultado, "chamada_funcao")
        resultado["motivos"].append("TABLE(função) executa função de tabela (pipelined) do usuário")


def _checar_operacoes_especiais(instrucao: str, upper: str, resultado: dict[str, Any]) -> None:
    """CONNECT BY (aviso), NEXTVAL (bloqueio) e database link (bloqueio)."""
    if re.search(r"\bCONNECT\s+BY\b", upper) and not re.search(r"\bNOCYCLE\b", upper):
        resultado["avisos"].append("CONNECT BY: confirme condição de parada/volume com get_query_plan antes")
    if re.search(r"\bNEXTVAL\b", upper):
        _bloquear(resultado, "sequence")
        resultado["motivos"].append("NEXTVAL consome valor de sequence (efeito colateral)")
    if re.search(r"@\s*[A-Za-z_]", instrucao):
        _bloquear(resultado, "dblink")
        resultado["motivos"].append("database link (@): consulta outro banco; exige aprovação")


def _checar_limite(upper: str, resultado: dict[str, Any], exigir_limite: bool) -> None:
    """Consulta sem limite de linhas vira aviso, ou bloqueio quando `exigir_limite`."""
    externo = _nivel_externo(upper)
    tem_limite = None if re.search(r"\bOR\b", externo) and "ROWNUM" in externo and not re.search(r"\bFETCH\s+(FIRST|NEXT)\b", externo) else re.search(r"\bFETCH\s+(FIRST|NEXT)\s+\d{1,6}\s+ROWS?\b|\bROWNUM\s*<=?\s*\d{1,6}\b", externo)
    if not tem_limite:
        msg = "consulta sem limite de linhas (use FETCH FIRST n ROWS ONLY ou ROWNUM <= n)"
        if exigir_limite:
            resultado["permitido"] = False
            resultado["motivos"].append(msg)
        else:
            resultado["avisos"].append(msg)


def _checar_leitura(
    instrucao: str,
    primeira: str,
    citados: list[str],
    resultado: dict[str, Any],
    exigir_limite: bool,
) -> None:
    """Regras de uma instrução SELECT ou WITH, na ordem em que os motivos são reportados."""
    upper = instrucao.upper()
    _checar_bloqueios_de_leitura(primeira, upper, resultado)
    _checar_chamadas(instrucao, citados, resultado)
    _checar_operacoes_especiais(instrucao, upper, resultado)
    _checar_limite(upper, resultado, exigir_limite)


def _classificar_comando(primeira: str, resultado: dict[str, Any]) -> None:
    """Comandos que não são leitura: DML, DDL, PL/SQL, controle de transação ou desconhecido."""
    if primeira in DML:
        _bloquear(resultado, "mutacao")
        resultado["motivos"].append(f"DML ({primeira}) altera dados")
    elif primeira in DDL:
        _bloquear(resultado, "ddl")
        resultado["motivos"].append(f"DDL/DCL ({primeira}) altera estrutura/permissões e faz COMMIT implícito")
    elif primeira in PLSQL:
        _bloquear(resultado, "plsql")
        resultado["motivos"].append(f"bloco/chamada PL/SQL ({primeira}) pode fazer qualquer coisa")
    elif primeira in TRANSACAO:
        _bloquear(resultado, "transacao")
        resultado["motivos"].append(f"controle de transação/sessão ({primeira})")
    else:
        _bloquear(resultado, "desconhecido")
        resultado["motivos"].append(f"palavra-chave inicial não reconhecida: {primeira}")


def _classificar_instrucao(
    instrucao: str, citados: list[str], resultado: dict[str, Any], exigir_limite: bool
) -> None:
    """Classifica uma instrução isolada e acumula o resultado em `resultado`."""
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_$#]*", instrucao.lstrip("( \t\r\n"))
    if not tokens:
        _bloquear(resultado, "invalido")
        resultado["motivos"].append("instrução sem palavra-chave")
        return
    primeira = tokens[0].upper()
    if primeira == "EXPLAIN":
        _bloquear(resultado, "plano")
        resultado["motivos"].append("EXPLAIN PLAN grava em tabela (PLAN_TABLE ou INTO); use a ferramenta get_query_plan do MCP")
        return
    if primeira in LEITURA:
        _checar_leitura(instrucao, primeira, citados, resultado, exigir_limite)
        return
    _classificar_comando(primeira, resultado)


def _anexar_verificacao(limpo: str, citados: list[str], resultado: dict[str, Any]) -> None:
    """Função sem argumentos pode ser chamada sem parênteses (SELECT fn FROM dual): o texto não
    distingue coluna de função. Devolve a consulta que tira a dúvida."""
    nomes: set[str] = set()
    for token in re.findall(r"(?<![\w$#'])[A-Za-z_][\w$#]*", PERMITIDOS.sub(" ", limpo)):
        nome = token.upper()
        if nome not in PALAVRAS_SQL and nome not in FUNCOES_NATIVAS and nome not in PALAVRAS_ANTES_DE_PARENTESE and not nome.startswith(("V$", "GV$")):
            nomes.add(nome)
    nomes |= {c.upper() for c in citados if re.fullmatch(r"[A-Za-z_][\w$#]*", c)}
    if nomes:
        lista = ", ".join(f"'{n}'" for n in sorted(nomes)[:500])
        resultado["verificar_objetos"] = sorted(nomes)
        resultado["consulta_verificacao"] = (
            "SELECT o.owner, o.object_name, o.object_type FROM all_objects o "
            f"WHERE o.object_type IN ('FUNCTION','PACKAGE','PROCEDURE','TYPE') AND o.object_name IN ({lista}) "
            "UNION ALL SELECT s.owner, s.synonym_name, o.object_type FROM all_synonyms s "
            "JOIN all_objects o ON o.owner = s.table_owner AND o.object_name = s.table_name "
            f"WHERE o.object_type IN ('FUNCTION','PACKAGE','PROCEDURE','TYPE') AND s.synonym_name IN ({lista}) "
            "FETCH FIRST 50 ROWS ONLY"
        )


def classificar(sql: str, exigir_limite: bool = False) -> dict[str, Any]:
    resultado: dict[str, Any] = {"classe": "leitura", "permitido": True, "motivos": [], "avisos": [], "instrucoes": 0}
    if not sql or not sql.strip():
        return {**resultado, "classe": "invalido", "permitido": False, "motivos": ["SQL vazio"]}
    if re.search(r"/\*\+[^*]*\bPARALLEL\b", sql, re.I):
        resultado["avisos"].append("hint PARALLEL: pode consumir muitos recursos do servidor; confirme com o usuário")
    citados: list[str] = []
    try:
        limpo = normalizar_grouping_sets(remover_literais_e_comentarios(sql, citados))
    except ValueError as exc:
        return {**resultado, "classe": "invalido", "permitido": False, "motivos": [str(exc)]}

    inicio = re.findall(r"[A-Za-z_]+", limpo)
    if not inicio:
        return {**resultado, "classe": "invalido", "permitido": False, "motivos": ["só comentários"]}
    primeira_global = inicio[0].upper()
    # Blocos PL/SQL e DDL contêm ';' internos: classificar o texto inteiro.
    corpo_plsql = (
        primeira_global in PLSQL
        or primeira_global in DDL
        or re.match(r"\s*WITH\s+(FUNCTION|PROCEDURE)\b", limpo, re.I) is not None
    )
    instrucoes = _separar_instrucoes(limpo, corpo_plsql)
    resultado["instrucoes"] = len(instrucoes)
    if len(instrucoes) > 1:
        resultado["permitido"] = False
        resultado["motivos"].append(f"{len(instrucoes)} instruções em um envio; envie uma por vez")

    for instrucao in instrucoes:
        _classificar_instrucao(instrucao, citados, resultado, exigir_limite)
    if len(instrucoes) > 1 and resultado["classe"] == "leitura":
        resultado["classe"] = "multiplas"
    if resultado["permitido"]:
        _anexar_verificacao(limpo, citados, resultado)
    return resultado


def _achar_sql(obj: Any) -> str | None:
    """Procura recursivamente argumentos 'sql'/'query' no payload do hook."""
    if isinstance(obj, dict):
        for chave, valor in obj.items():
            if str(chave).lower() in ("sql", "query", "statement", "sql_statement", "sqlquery") and isinstance(valor, str):
                return valor
        for valor in obj.values():
            achado = _achar_sql(valor)
            if achado is not None:
                return achado
    elif isinstance(obj, list):
        for valor in obj:
            achado = _achar_sql(valor)
            if achado is not None:
                return achado
    return None


def _ler_stdin() -> str:
    bruto = sys.stdin.buffer.read() if hasattr(sys.stdin, "buffer") else sys.stdin.read().encode("utf-8")
    for codificacao in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return bruto.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return bruto.decode("utf-8", errors="replace")


def _expandir_strings_json(obj: Any) -> Any:
    """args pode chegar serializado como string JSON; expande quando possível."""
    if isinstance(obj, str) and obj.strip()[:1] in ("{", "["):
        try:
            return _expandir_strings_json(json.loads(obj))
        except json.JSONDecodeError:
            return obj
    if isinstance(obj, dict):
        return {k: _expandir_strings_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expandir_strings_json(v) for v in obj]
    return obj


def modo_hook() -> int:
    """PreToolUse: nunca devolve 'allow'. Qualquer dúvida vira 'force_ask'."""

    def responder(decisao: str, motivo: str) -> int:
        print(json.dumps({"decision": decisao, "reason": motivo}, ensure_ascii=False))
        return 0

    try:
        payload = _expandir_strings_json(json.loads(_ler_stdin() or "{}"))
        alvo = payload.get("toolCall", payload) if isinstance(payload, dict) else payload
        sql = _achar_sql(alvo)
        if sql is None:
            return responder("force_ask", "guard_sql: não encontrei a SQL no payload; confirme manualmente")
        analise = classificar(sql)
        if analise["permitido"]:
            return responder("ask", "guard_sql: leitura")
        return responder("force_ask", "guard_sql: CHECKPOINT HUMANO — " + "; ".join(analise["motivos"]))
    except Exception as exc:  # pylint: disable=broad-exception-caught  # hook nunca pode falhar aberto
        return responder("force_ask", f"guard_sql: erro ao analisar ({type(exc).__name__}); confirme manualmente")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classifica SQL Oracle antes de executar via MCP.")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--sql")
    grupo.add_argument("--arquivo")
    grupo.add_argument("--hook", action="store_true")
    parser.add_argument("--exigir-limite", action="store_true", help="Bloqueia SELECT sem FETCH FIRST/ROWNUM.")
    args = parser.parse_args(argv)
    if args.hook:
        return modo_hook()
    if args.arquivo:
        try:
            with open(args.arquivo, "rb") as handle:
                bruto = handle.read()
            for codificacao in ("utf-8-sig", "cp1252", "latin-1"):
                try:
                    sql = bruto.decode(codificacao)
                    break
                except UnicodeDecodeError:
                    continue
        except OSError as exc:
            print(json.dumps({"classe": "invalido", "permitido": False, "motivos": [str(exc)]}, ensure_ascii=False))
            return 1
    elif args.sql is not None:
        sql = args.sql
    else:
        sql = sys.stdin.read()
    analise = classificar(sql, args.exigir_limite)
    print(json.dumps(analise, ensure_ascii=False, indent=2))
    if analise["classe"] == "invalido":
        return 1
    return 0 if analise["permitido"] else 3


if __name__ == "__main__":
    sys.exit(main())
