/**
 * oracle_query.js - Bridge Node (node-oracledb, Thick Mode) chamado por
 * lib/python/oracle_extract.run_node_bridge quando ORACLE_DRIVER_MODE=bridge.
 *
 * Uso:
 *   node oracle_query.js <arquivo_sql> [params_json] [max_rows] [prazo_segundos]
 * Credenciais e DSN vem do ambiente montado pelo chamador (nao le o .env).
 * Datas trafegam como {"$date": "<ISO local>"} nos dois sentidos.
 * Retorno (stdout):
 *   {"columns": [...], "rows": [...]}
 */

const fs = require('fs');
const oc = require('./oracle_common');

function decodeParams(text) {
  const params = JSON.parse(text || '{}');
  for (const [k, v] of Object.entries(params)) {
    if (v && typeof v === 'object' && Object.keys(v).length === 1 && typeof v.$date === 'string') {
      params[k] = oc.parseLocalIso(v.$date);
    }
  }
  return params;
}

function encodeValue(v) {
  if (v instanceof Date) return { $date: oc.localIso(v) };
  return typeof v === 'string' ? v.trim() : v;
}

async function main() {
  const [sqlFile, paramsJson, maxRowsArg, deadlineArg] = process.argv.slice(2);
  if (!sqlFile || !fs.existsSync(sqlFile)) {
    throw new Error('Uso: node oracle_query.js <arquivo_sql> [params_json] [max_rows] [prazo_segundos]');
  }
  const sql = fs.readFileSync(sqlFile, 'utf8');
  const params = decodeParams(paramsJson);
  const deadlineSeconds = Number(deadlineArg) || 0;
  const creds = oc.resolveCredentials();

  const { columns, rows } = await oc.fetchAll(creds, sql, params, {
    arraySize: 5000,
    maxRows: Number(maxRowsArg) || 0,
    callTimeoutMs: deadlineSeconds * 1000
  });
  process.stdout.write(JSON.stringify({ columns, rows: rows.map(row => row.map(encodeValue)) }));
  return 0;
}

const log = (msg, level = 'ERROR') => process.stderr.write(`[ORACLE-BRIDGE] ${level}: ${msg}\n`);
oc.runMain(main, (msg, level) => log(msg, level), Number(process.argv[5]) || undefined);
