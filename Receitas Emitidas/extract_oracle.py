# -*- coding: utf-8 -*-
# {
#   "version": "2.6.0",
#   "skill": "python-oracle-migration, protocolo-valeg",
#   "contract": "ipc-stdio, thick-mode-padronizado",
#   "description": "Extrai receitas emitidas via Direct Oracle (Query CTE Nativa) com Thick Mode garantido",
#   "reliability": "Base64-Bridge-Logs, SQL-Correlation-DNA, Retry-On-Failure"
# }
import os
import sys
import json
import oracledb
from datetime import datetime
import base64

# Forca UTF-8 para garantir interoperabilidade
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

def log(message, level="INFO", exec_id="manual"):
    """Envia logs em Base64 para o stderr (Isolamento total)."""
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
    # Usando ASCII no prefixo para evitar problemas de encoding no terminal antes do decode
    raw_msg = f"[{ts}] [PY-EXTRACT] [{level}] [ExecId:{exec_id}] {message}"
    b64_msg = base64.b64encode(raw_msg.encode('utf-8')).decode('ascii')
    sys.stderr.write(f"B64:{b64_msg}\n")
    sys.stderr.flush()

def extract():
    exec_id = sys.argv[1] if len(sys.argv) > 1 else "manual"

    user = os.environ.get("ORACLE_READONLY_USER")
    password = os.environ.get("ORACLE_READONLY_PASSWORD")
    dsn = os.environ.get("ORACLE_CONNECT_STRING", "dbprd")
    client_lib = os.environ.get("ORACLE_CLIENT_LIB_DIR")
    tns_admin = os.environ.get("TNS_ADMIN")

    # Validacao de pre-requisitos obrigatorios
    if not all([user, password, dsn]):
        log("Credenciais Oracle ausentes no ambiente (ORACLE_READONLY_USER, ORACLE_READONLY_PASSWORD, ORACLE_CONNECT_STRING).", "ERROR", exec_id)
        sys.exit(1)

    if not client_lib or not os.path.exists(client_lib):
        log(f"ORACLE_CLIENT_LIB_DIR invalido ou ausente: '{client_lib}'. Thick Mode impossivel. Abortando para evitar falha DPY-3015.", "ERROR", exec_id)
        sys.exit(1)

    if not tns_admin or not os.path.exists(tns_admin):
        log(f"TNS_ADMIN invalido ou ausente: '{tns_admin}'. Thick Mode impossivel sem tnsnames.ora. Abortando.", "ERROR", exec_id)
        sys.exit(1)

    # Garantir Thick Mode - falha explicita se nao conseguir (nao ha fallback para Thin Mode)
    try:
        oracledb.init_oracle_client(lib_dir=client_lib, config_dir=tns_admin)
        log(f"Thick Mode ativado. client_lib='{client_lib}' tns_admin='{tns_admin}'", "INFO", exec_id)
    except Exception as e:
        log(f"ERRO CRITICO: Nao foi possivel ativar Thick Mode: {e}", "ERROR", exec_id)
        sys.exit(1)

    # Query Original Estavel com CTE (Velocidade maxima sem timeout)
    sql = f"""
    WITH
        TINGIMENTO_TEMPOS AS (
            SELECT
                UPO.NUMEROORDEMREAL AS NUMERO_OB,
                MAX(UNP.DTTEMPOINICIAL) AS INICIO_TING,
                MAX(UNP.DTTEMPOFINAL) AS FINAL_TING
            FROM SGTPRD.UP_ORDEM_MVTO UPO
            JOIN SGTPRD.UNIDADE_PROGRAMACAO UNP ON UPO.NUMEROUP = UNP.NUMEROUP
            WHERE UNP.TIPO_MAQUINA = 19 
            AND UNP.EXCLUIDA = 0 
            GROUP BY UPO.NUMEROORDEMREAL
        ),
        MAQUINAS_TINGIMENTO AS (
            SELECT 
                NUMERO_OB,
                MAX(LTRIM(NUMERO_MAQUINA, '0')) AS MQ_TING
            FROM SGTPRD.OB_FASES 
            WHERE CODIGO_FASE = 40
            GROUP BY NUMERO_OB
        ),
        DADOS_AGREGADOS AS (
            SELECT
                OBF.NUMERO_OB, M.NUMEROORDEM, OBF.CODIGO_GRUPO, OBP.CODPRO_REDUZIDO,
                MAX(TRIM(OPE.NOME)) AS USUARIO,
                MAX(M.DT_PESAGEM) AS HORARIO_PESADO,
                SUM(M.QUANTIDADEPESADA) AS QUANT_PESADA
            FROM SGTPRD.OB_FASES OBF
            JOIN SGTPRD.VW_BNF_FASEATUALOB OB ON OB.NUMERO_OB = OBF.NUMERO_OB       
            JOIN SGTPRD.OB_PRODUTO OBP ON OBP.NUMERO_OB = OBF.NUMERO_OB
            JOIN SGTPRD.MOVTO_RECEITA M ON M.NUMEROORDEM = OBF.NUMEROORDEMMOVIMENTO 
                AND M.SEQUENCIAFASEOB = OBF.SEQUENCIAORDEMMOVIME
            LEFT JOIN SGTPRD.OPERADOR OPE ON OPE.IDOPERADOR = M.IDOPE_PESAGEM
            WHERE OBF.CODIGO_FASE = 40 AND OBF.STATUS IN (1, 2, 3)
            GROUP BY OBF.NUMERO_OB, M.NUMEROORDEM, OBF.CODIGO_GRUPO, OBP.CODPRO_REDUZIDO
        )
    
    SELECT /*+ FIRST_ROWS(1000) ExecId:{exec_id} */
        *
    FROM (
        SELECT
            SYSDATE AS Valida_Atualizacao,
            BASE.CODIGO_GRUPO AS GRUPO, BASE.NUMERO_OB,
            CASE WHEN SGTPRD.FNC_ESP_REC_PES(BASE.NUMERO_OB) = 0 THEN 'NAO' ELSE 'SIM' END AS PESADA,
            MT.MQ_TING, TT.INICIO_TING, TT.FINAL_TING,
            ART.CDARTIGOCRU AS ARTIGO, BASE.CODPRO_REDUZIDO AS REDUZIDO,
            TRIM(ITE.DESCRICAO) AS DESCRICAO, FAS.DESCR_FASE AS FASE_ATUAL,
            CASE FAS.STATUS
                WHEN 0 THEN 'PROGRAMADA' WHEN 1 THEN 'EMITIDA'
                WHEN 2 THEN 'PESADA' WHEN 3 THEN 'EM EXECUCAO'
            END AS STATUS_FASE,
            BASE.USUARIO, BASE.HORARIO_PESADO,
            ROUND((SYSDATE) - BASE.HORARIO_PESADO, 2) AS DIAS_PESADO,
            BASE.QUANT_PESADA
        FROM DADOS_AGREGADOS BASE
        LEFT JOIN TINGIMENTO_TEMPOS TT ON TT.NUMERO_OB = BASE.NUMERO_OB
        LEFT JOIN MAQUINAS_TINGIMENTO MT ON MT.NUMERO_OB = BASE.NUMERO_OB
        LEFT JOIN SGTPRD.ENGEITEMESTOARTCRU ART ON ART.CDREDUZIDO = BASE.CODPRO_REDUZIDO
        LEFT JOIN SGTPRD.ITENS_ESTOQUE ITE ON ITE.CODIGO_REDUZIDO = BASE.CODPRO_REDUZIDO
        LEFT JOIN SGTPRD.VW_BNF_FASEATUALOB FAS ON FAS.NUMERO_OB = BASE.NUMERO_OB
    )
    WHERE PESADA = 'NAO'
    ORDER BY INICIO_TING NULLS LAST
    """

    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        connection = None
        try:
            if retry_count > 0:
                log(f"Tentativa {retry_count + 1} de {max_retries}...", "WARN", exec_id)
            
            log("Conectando ao Oracle para extracao Nativa (Pure-Python)...", "INFO", exec_id)
            connection = oracledb.connect(user=user, password=password, dsn=dsn)
            cursor = connection.cursor()
            
            log("Executando extracao oficial otimizada...", "INFO", exec_id)
            cursor.execute(sql)
            
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
            
            data = []
            for row in rows:
                record = dict(zip(columns, row))
                for key, value in record.items():
                    if isinstance(value, datetime): record[key] = value.isoformat()
                    elif isinstance(value, str) and value: record[key] = value.strip()
                data.append(record)
                
            # O Payload sai pelo Stdout limpo para o Orquestrador ler
            sys.stdout.write(json.dumps(data, ensure_ascii=False))
            sys.stdout.flush()
            log(f"Extracao concluida: {len(data)} registros.", "INFO", exec_id)
            return # Sucesso total
            
        except Exception as e:
            retry_count += 1
            log(f"Erro na extracao (Tentativa {retry_count}/{max_retries}): {e}", "ERROR", exec_id)
            if retry_count >= max_retries:
                sys.exit(1)
            import time
            time.sleep(5)
        finally:
            if connection:
                try: connection.close()
                except: pass

if __name__ == "__main__":
    extract()
