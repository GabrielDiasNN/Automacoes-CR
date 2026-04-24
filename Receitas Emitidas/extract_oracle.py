import os
import sys
import json
import oracledb
from datetime import datetime

def log(message, level="INFO", exec_id="manual"):
    """Envia logs para o stderr para não poluir o stdout (reservado para dados JSON)."""
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
    sys.stderr.write(f"[{ts}] [PY-EXTRACT] [{level}] [ExecId:{exec_id}] {message}\n")
    sys.stderr.flush()

def extract():
    exec_id = sys.argv[1] if len(sys.argv) > 1 else "manual"
    
    # 1. Obter credenciais via variáveis de ambiente (Processo herdado)
    user = os.environ.get("ORACLE_READONLY_USER")
    password = os.environ.get("ORACLE_READONLY_PASSWORD")
    dsn = os.environ.get("ORACLE_CONNECT_STRING")
    client_lib = os.environ.get("ORACLE_CLIENT_LIB_DIR")

    if not all([user, password, dsn]):
        log("Credenciais (ORACLE_*) ausentes no ambiente.", "ERROR", exec_id)
        sys.exit(1)

    # Iniciar modo Thick se houver diretório de biblioteca
    if client_lib and os.path.exists(client_lib):
        try:
            oracledb.init_oracle_client(lib_dir=client_lib)
            log(f"Modo Thick ativado (lib_dir={client_lib})", "INFO", exec_id)
        except Exception as e:
            log(f"Falha ao iniciar modo Thick, tentando modo Thin: {e}", "WARN", exec_id)

    sql = """
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

SELECT /*+ FIRST_ROWS(1000) */
    *
FROM (
    SELECT
        BASE.CODIGO_GRUPO AS GRUPO, BASE.NUMERO_OB,
        CASE WHEN SGTPRD.FNC_ESP_REC_PES(BASE.NUMERO_OB) = 0 THEN 'NÃO' ELSE 'SIM' END AS PESADA,
        MT.MQ_TING, TT.INICIO_TING, TT.FINAL_TING,
        ART.CDARTIGOCRU AS ARTIGO, BASE.CODPRO_REDUZIDO AS REDUZIDO,
        TRIM(ITE.DESCRICAO) AS DESCRICAO, FAS.DESCR_FASE AS FASE_ATUAL,
        CASE FAS.STATUS 
            WHEN 0 THEN 'PROGRAMADA' WHEN 1 THEN 'EMITIDA' 
            WHEN 2 THEN 'PESADA' WHEN 3 THEN 'EM EXECUÇÃO' 
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
WHERE PESADA = 'NÃO'
ORDER BY INICIO_TING NULLS LAST
"""

    connection = None
    try:
        log("Conectando ao Oracle...", "INFO", exec_id)
        connection = oracledb.connect(user=user, password=password, dsn=dsn)
        cursor = connection.cursor()
        
        cursor.execute(sql)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        
        data = []
        for row in rows:
            record = dict(zip(columns, row))
            for key, value in record.items():
                if isinstance(value, datetime):
                    record[key] = value.isoformat()
            data.append(record)
            
        # Saída estruturada via STDOUT para IPC
        sys.stdout.write(json.dumps(data, ensure_ascii=False))
        sys.stdout.flush()
        
        log(f"Extração concluída. {len(data)} registros enviados para stdout.", "INFO", exec_id)
        
    except oracledb.DatabaseError as e:
        error_obj, = e.args
        log(f"Erro de Banco de Dados Oracle: {error_obj.message}", "ERROR", exec_id)
        sys.exit(1)
    except Exception as e:
        log(f"Erro inesperado na extração: {e}", "ERROR", exec_id)
        sys.exit(1)
    finally:
        if connection:
            connection.close()

if __name__ == "__main__":
    extract()
