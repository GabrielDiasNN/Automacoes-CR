import os
import sys
import json
import oracledb
from datetime import datetime

def extract():
    # 1. Obter credenciais de forma segura via variáveis de ambiente
    # Injetadas pelo run.ps1 a partir do arquivo .env
    user = os.environ.get("ORACLE_READONLY_USER")
    password = os.environ.get("ORACLE_READONLY_PASSWORD")
    dsn = os.environ.get("ORACLE_CONNECT_STRING")
    client_lib = os.environ.get("ORACLE_CLIENT_LIB_DIR")
    exec_id = sys.argv[1] if len(sys.argv) > 1 else "manual"

    if not all([user, password, dsn]):
        print(f"[{datetime.now()}] [PY] [ERRO] Credenciais (ORACLE_*) ausentes no ambiente.")
        sys.exit(1)

    # Opcional: Iniciar modo Thick se houver diretório de biblioteca
    if client_lib and os.path.exists(client_lib):
        try:
            oracledb.init_oracle_client(lib_dir=client_lib)
            print(f"[{datetime.now()}] [PY] [INFO] Modo Thick ativado (lib_dir={client_lib})")
        except Exception as e:
            print(f"[{datetime.now()}] [PY] [WARN] Falha ao iniciar modo Thick, tentando modo Thin: {e}")

    # 2. Query SQL (replicada do PowerQuery)
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
        # 3. Conectar via oracledb Thin Mode
        # Se DSN for no formato "host:port/service_name", o Thin mode funciona sem config local
        # Se for apenas um nome (TNS), ele procuraria arquivos de config (erro DPY-4027)
        
        connection = oracledb.connect(user=user, password=password, dsn=dsn)
        cursor = connection.cursor()
        
        print(f"[{datetime.now()}] [PY] [INFO] [ExecId:{exec_id}] Conectado ao Oracle. Iniciando extração...")
        cursor.execute(sql)
        
        # Obter colunas
        columns = [col[0] for col in cursor.description]
        
        # 4. Fetch e conversão para JSON
        rows = cursor.fetchall()
        data = []
        for row in rows:
            record = dict(zip(columns, row))
            # Serializar objetos datetime para string ISO
            for key, value in record.items():
                if isinstance(value, datetime):
                    record[key] = value.isoformat()
            data.append(record)
            
        # 5. Salvar arquivo de Shadow (ignorado no git)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_file = os.path.join(script_dir, f"ReceitasEmitidas_shadow_{exec_id}.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            
        print(f"[{datetime.now()}] [PY] [INFO] [ExecId:{exec_id}] Extração concluída. Total de linhas: {len(data)}")
        
    except Exception as e:
        print(f"[{datetime.now()}] [PY] [ERRO] [ExecId:{exec_id}] Erro na extração: {e}")
        sys.exit(1)
    finally:
        if connection:
            connection.close()

if __name__ == "__main__":
    extract()
