/**
 * extract_oracle.js - Extrator Oracle em Node.js para Receitas Emitidas (RE-03).
 * Usado so com ORACLE_DRIVER_MODE=bridge. Mesmo contrato IPC STDIO e mesmo hash
 * do extract_oracle.py; nucleo em lib/node/oracle_common.js.
 */

const fs = require('fs');
const path = require('path');
const oc = require('../lib/node/oracle_common');

oc.loadEnvFile();

const execId = process.argv[2] || 'manual';
const log = oc.makeLogger('EXTRACT-JS', execId);
const STATE_PATH = path.join(__dirname, 'receitas_state.json');

async function extract() {
  const creds = oc.resolveCredentials();
  let sql = fs.readFileSync(path.join(__dirname, 'SQL-ReceitasEmitidas.sql'), 'utf8');
  sql = sql.replace('/*+ FIRST_ROWS(1000) */', `/*+ FIRST_ROWS(1000) ExecId:${execId} */`);

  log('Executando query SQL CTE de Receitas Emitidas...');
  const { columns, rows } = await oc.fetchAll(creds, sql, {});
  const data = oc.serializeRows(columns, rows, r => [
    oc.pyStr(r.NUMERO_OB), oc.pyStr(r.REDUZIDO), oc.pyStr(r.GRUPO), oc.pyStr(r.INICIO_TING)
  ]);

  // record_counts para o evento execution.end do run.ps1 (stdout e canal de dados).
  fs.writeFileSync(path.join(__dirname, 're_result.json'), JSON.stringify({ record_counts: { read: data.length } }), 'utf8');

  const currentHash = oc.computeHash(data);
  log(`Hash calculado para ${data.length} registros: ${currentHash}`, 'DEBUG');

  const lastHash = oc.readLastHash(STATE_PATH);
  if (lastHash && currentHash === lastHash) {
    if (fs.existsSync(`${STATE_PATH}.tmp`)) {
      log('Sem novas alteracoes, mas detectado estado temporario pendente de notificacao.');
    } else {
      log('Sem alteracoes relevantes detectadas (Idempotencia).');
      return 2;
    }
  }

  oc.writeStateTmp(STATE_PATH, currentHash);
  process.stdout.write(JSON.stringify(data));
  log(`Extracao concluida com sucesso: ${data.length} registros.`);
  return 0;
}

oc.runMain(extract, log);
