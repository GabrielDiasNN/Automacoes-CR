/**
 * extract_oracle.js - Extrator Oracle em Node.js para Montagem de Terceirizados (MT-02).
 * Usado so com ORACLE_DRIVER_MODE=bridge. Mesmo contrato IPC FILE PAYLOAD
 * (.data_{exec_id}.json) do extract_oracle.py; nucleo em lib/node/oracle_common.js.
 */

const fs = require('fs');
const path = require('path');
const oc = require('../lib/node/oracle_common');

oc.loadEnvFile();

const execId = process.argv[2] || 'manual';
const log = oc.makeLogger('EXTRACT-JS', execId);

async function extract() {
  // Mesmo contrato do extract_oracle.py: alias TNS fixo "dbprd", independente do .env.
  const creds = oc.resolveCredentials({ forceDsn: 'dbprd', requireTnsAdmin: true });
  const sql = fs.readFileSync(path.join(__dirname, 'SQL-MontagemTerceirizados.sql'), 'utf8');

  log(`Conectando ao Oracle via TNS Alias '${creds.dsn}'...`);
  const { columns, rows } = await oc.fetchAll(creds, sql, {}, { arraySize: 5000 });
  const data = oc.serializeRows(columns, rows);

  fs.writeFileSync(path.join(__dirname, `.data_${execId}.json`), JSON.stringify(data), 'utf8');
  log(`Extracao nativa concluida: ${data.length} registros.`);
  return 0;
}

oc.runMain(extract, log);
