/**
 * extract_obs.js - Extrator Oracle em Node.js para OBs Paradas na Fase (OBP-04).
 * Usado so com ORACLE_DRIVER_MODE=bridge. Mesmo contrato (obs_result.json /
 * obs_state.json.tmp, exit 2 = idempotente) e mesmo hash do extract_obs.py;
 * nucleo em lib/node/oracle_common.js.
 */

const fs = require('fs');
const path = require('path');
const oc = require('../lib/node/oracle_common');

oc.loadEnvFile();

const execId = process.argv[2] || 'manual';
const log = oc.makeLogger('OBP-EXTRACT-JS', execId);
const RESULT_FILE = path.join(__dirname, 'obs_result.json');
const STATE_FILE = path.join(__dirname, 'obs_state.json');

function writeResult(payload) {
  fs.writeFileSync(RESULT_FILE, JSON.stringify(payload, null, 2), 'utf8');
}

async function extract() {
  const creds = oc.resolveCredentials();
  const sql = fs.readFileSync(path.join(__dirname, 'SQL-ObsParadasFase.sql'), 'utf8');

  const { columns, rows } = await oc.fetchAll(creds, sql, {}, { arraySize: 1000 });
  const data = oc.serializeRows(columns, rows, r => [r.NUMERO_OB || '', r.FASE_ATUAL || '']);
  const currentHash = oc.computeHash({ rows: data });

  if (oc.readLastHash(STATE_FILE) === currentHash) {
    writeResult({ rows: [], total: 0, record_counts: { read: data.length }, extracted_at: oc.localIso(new Date()) });
    log('Sem alteracoes (idempotencia).');
    return 2;
  }

  writeResult({
    rows: data,
    total: data.length,
    record_counts: { read: data.length },
    extracted_at: oc.localIso(new Date()),
    hash: currentHash
  });
  oc.writeStateTmp(STATE_FILE, currentHash);
  log(`Extracao concluida: ${data.length} OBs.`);
  return 0;
}

oc.runMain(extract, log);
