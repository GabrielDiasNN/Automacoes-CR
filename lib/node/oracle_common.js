/**
 * oracle_common.js - Nucleo compartilhado dos extratores Oracle em Node.js.
 *
 * Espelha o contrato de lib/python/oracle_extract.py para que o motor Node e o
 * Python produzam o mesmo dado e o mesmo hash de idempotencia:
 * - datas em ISO local sem fuso (datetime.isoformat do Python), nunca UTC;
 * - hash sobre JSON no formato de json.dumps(sort_keys=True, ensure_ascii=False);
 * - credenciais e DSN com as mesmas regras de resolve_oracle_credentials.
 */

const fs = require('fs');
const path = require('path');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const ROOT_MODULES = path.join(REPO_ROOT, 'node_modules');
if (!module.paths.includes(ROOT_MODULES)) {
  module.paths.push(ROOT_MODULES);
}
const oracledb = require('oracledb');

// Prazo total do processo: sem ele um connect/consulta travado na WAN segura a
// automacao (WaitForExit sem prazo) e a sessao Oracle indefinidamente.
const DEFAULT_DEADLINE_SECONDS = 300;

/** Le o .env da raiz com override, como o load_dotenv(override=True) do Python. */
function loadEnvFile(envPath = path.join(REPO_ROOT, '.env')) {
  if (!fs.existsSync(envPath)) return;
  const content = fs.readFileSync(envPath, 'utf8');
  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eqIdx = trimmed.indexOf('=');
    if (eqIdx <= 0) continue;
    const key = trimmed.slice(0, eqIdx).trim();
    let val = trimmed.slice(eqIdx + 1).trim();
    if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
      val = val.slice(1, -1);
    }
    process.env[key] = val;
  }
}

function makeLogger(tag, execId) {
  return (msg, level = 'INFO') => {
    const ts = new Date().toLocaleString('pt-BR');
    process.stderr.write(`[${ts}] [${tag}] [${level}] [ExecId:${execId}] ${msg}\n`);
  };
}

/**
 * Mesmas regras de resolve_oracle_credentials: DSN vazio e erro (nunca cai em
 * producao por omissao), alias TNS e respeitado, e o Oracle Client e obrigatorio
 * porque o motor Node roda em Thick Mode (verificador legado 0x939).
 */
function resolveCredentials({ forceDsn = null, requireTnsAdmin = false } = {}) {
  const user = process.env.ORACLE_READONLY_USER;
  const password = process.env.ORACLE_READONLY_PASSWORD;
  const rawDsn = forceDsn !== null ? forceDsn : (process.env.ORACLE_CONNECT_STRING ?? 'dbprd');
  const dsn = (rawDsn || '').trim();
  const clientLib = process.env.ORACLE_CLIENT_LIB_DIR || process.env.ORACLE_CLIENT_PATH || '';
  const tnsAdmin = process.env.TNS_ADMIN || null;

  if (!user || !password) throw new Error('Credenciais Oracle ausentes no ambiente.');
  if (!dsn) throw new Error('DSN Oracle vazio (ORACLE_CONNECT_STRING ou forceDsn).');
  if (!clientLib || !fs.existsSync(clientLib)) {
    throw new Error('ORACLE_CLIENT_LIB_DIR invalido (obrigatorio no motor Node, Thick Mode).');
  }
  if (requireTnsAdmin && !tnsAdmin) throw new Error('TNS_ADMIN ausente no ambiente.');
  return { user, password, dsn, clientLib, tnsAdmin };
}

/** Executa a consulta e devolve colunas e linhas (arrays), como fetch_all. */
async function fetchAll(creds, sql, binds = {}, { arraySize = 1000, maxRows = 0, callTimeoutMs = 0 } = {}) {
  oracledb.initOracleClient({ libDir: creds.clientLib, configDir: creds.tnsAdmin || undefined });
  const connection = await oracledb.getConnection({
    user: creds.user,
    password: creds.password,
    connectString: creds.dsn
  });
  try {
    if (callTimeoutMs > 0) connection.callTimeout = callTimeoutMs;
    const result = await connection.execute(sql, binds, {
      outFormat: oracledb.OUT_FORMAT_ARRAY,
      fetchArraySize: arraySize,
      maxRows
    });
    return { columns: (result.metaData || []).map(m => m.name), rows: result.rows || [] };
  } finally {
    await connection.close().catch(() => {});
  }
}

function pad(value, width = 2) {
  return String(value).padStart(width, '0');
}

/** datetime.isoformat() de um datetime ingenuo local (sem fuso, microssegundos so se != 0). */
function localIso(d) {
  let text = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  const ms = d.getMilliseconds();
  if (ms) text += `.${pad(ms * 1000, 6)}`;
  return text;
}

/** Inverso de localIso para "YYYY-MM-DD[THH:MM:SS[.ffffff]]", sempre em hora local. */
function parseLocalIso(text) {
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?)?$/.exec(text);
  if (!m) throw new Error(`Data invalida no parametro: ${text}`);
  const ms = m[7] ? Math.floor(Number(m[7].padEnd(6, '0')) / 1000) : 0;
  return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0), ms);
}

/** serialize_rows: dict por linha, datas em ISO local, strings sem espacos nas pontas. */
function serializeRows(columns, rows, sortKey = null) {
  const repetidas = [...new Set(columns.filter((c, i) => columns.indexOf(c) !== i))].sort();
  if (repetidas.length) {
    throw new Error(`Colunas com nome repetido na consulta: ${repetidas.join(', ')}. Use alias unico para cada coluna.`);
  }
  const data = rows.map(row => {
    const record = {};
    columns.forEach((col, i) => {
      const v = row[i];
      record[col] = v instanceof Date ? localIso(v) : (typeof v === 'string' ? v.trim() : v);
    });
    return record;
  });
  if (sortKey) data.sort((a, b) => pyCompare(sortKey(a), sortKey(b)));
  return data;
}

/** Comparacao de tuplas do Python (numeros pelo valor, texto por ponto de codigo). */
function pyCompare(a, b) {
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    const x = a[i];
    const y = b[i];
    if (typeof x === 'number' && typeof y === 'number') {
      if (x !== y) return x < y ? -1 : 1;
      continue;
    }
    const sx = String(x);
    const sy = String(y);
    if (sx !== sy) return sx < sy ? -1 : 1;
  }
  return a.length - b.length;
}

function pyNumber(v) {
  if (Number.isInteger(v)) return String(v);
  // repr do float no Python: expoente com dois digitos (1e-07).
  return String(v).replace(/e([+-])(\d)$/, 'e$10$2');
}

/** str() do Python para os valores que chegam do Oracle. */
function pyStr(v) {
  if (v === null || v === undefined) return 'None';
  if (typeof v === 'number') return pyNumber(v);
  return String(v);
}

/** json.dumps(v, ensure_ascii=False, sort_keys=True) com os separadores padrao. */
function pyJson(v) {
  if (v === null || v === undefined) return 'null';
  if (typeof v === 'boolean') return v ? 'true' : 'false';
  if (typeof v === 'number') return pyNumber(v);
  if (typeof v === 'string') return JSON.stringify(v);
  if (Array.isArray(v)) return `[${v.map(pyJson).join(', ')}]`;
  const keys = Object.keys(v).sort();
  return `{${keys.map(k => `${JSON.stringify(k)}: ${pyJson(v[k])}`).join(', ')}}`;
}

/** compute_hash do Python: sha256 do JSON deterministico. */
function computeHash(data) {
  return require('crypto').createHash('sha256').update(pyJson(data), 'utf8').digest('hex');
}

function readLastHash(statePath) {
  if (!fs.existsSync(statePath)) return '';
  let parsed;
  try {
    parsed = JSON.parse(fs.readFileSync(statePath, 'utf8'));
  } catch (e) {
    return '';
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`state.json em ${statePath} deve ser um objeto JSON.`);
  }
  return String(parsed.last_hash ?? '');
}

function writeStateTmp(statePath, currentHash) {
  fs.writeFileSync(`${statePath}.tmp`, pyJson({ last_hash: currentHash, updated_at: localIso(new Date()) }), 'utf8');
}

/**
 * Roda o extrator com prazo total. O valor resolvido vira o exit code (0 ou 2);
 * erro vira exit 1. O prazo encerra o processo (e a sessao) se travar.
 */
function runMain(fn, log, deadlineSeconds = Number(process.env.ORACLE_JS_DEADLINE_SECONDS) || DEFAULT_DEADLINE_SECONDS) {
  const timer = setTimeout(() => {
    log(`Prazo total de ${deadlineSeconds}s excedido; encerrando.`, 'ERROR');
    process.exit(1);
  }, deadlineSeconds * 1000);
  Promise.resolve()
    .then(fn)
    .then(code => { process.exitCode = code || 0; })
    .catch(err => {
      log(`Falha na extracao Oracle: ${err.message}`, 'ERROR');
      process.exitCode = 1;
    })
    .finally(() => clearTimeout(timer));
}

module.exports = {
  oracledb,
  loadEnvFile,
  makeLogger,
  resolveCredentials,
  fetchAll,
  localIso,
  parseLocalIso,
  serializeRows,
  pyStr,
  pyJson,
  computeHash,
  readLastHash,
  writeStateTmp,
  runMain
};
