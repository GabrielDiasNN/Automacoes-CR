const assert = require('assert');
const fs = require('fs');
const path = require('path');

const automationRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(automationRoot, '..');
const sharedCorePath = path.join(repoRoot, 'lib', 'WhatsApp-Core.js');
const packageJsonPath = path.join(automationRoot, 'package.json');

function read(filePath) {
  return fs.readFileSync(filePath, 'utf8');
}

assert.ok(fs.existsSync(sharedCorePath), 'lib/WhatsApp-Core.js deve existir');

const sharedCore = read(sharedCorePath);
const packageJson = JSON.parse(read(packageJsonPath));

assert.strictEqual(packageJson.type, 'commonjs');
assert.ok(packageJson.scripts.test.includes('whatsapp-offline.test.js'));

assert.match(sharedCore, /const CONTACT_ARG = \(process\.argv\[5\] \|\| ''\)/);
assert.match(sharedCore, /INITIALIZE_MAX_ATTEMPTS = [23]/);
assert.match(sharedCore, /ACK_WAIT_ATTEMPTS = 90/);
assert.match(sharedCore, /process\.exit\(21\)/);
assert.match(sharedCore, /process\.exit\(24\)/);
assert.match(sharedCore, /function describeError\(error\)/);
assert.doesNotMatch(sharedCore, /\b\d{10,13}@c\.us\b/);

// Regressao: mencoes via @<numero-discado>@c.us direto falham silenciosamente quando o ID
// real registrado no WhatsApp difere do numero discado (sem o 9o digito legado, ou LID).
// resolverMencoes() consulta client.getNumberId() para obter o wid real antes de montar
// o array de mentions — extrairOpcoesMensagem() (o helper sincrono anterior, que so
// concatenava "@c.us" no numero cru) nao deve mais existir.
assert.match(sharedCore, /async function resolverMencoes\(client, caption\)/);
assert.match(sharedCore, /client\.getNumberId\(numero\)/);
assert.doesNotMatch(sharedCore, /function extrairOpcoesMensagem/);

// Regressao [1.1.7]: whatsapp-web.js 1.34.6 pode resolver client.sendMessage() com
// `undefined` (getMessageModel nao serializa) apesar de a mensagem ter sido entregue.
// Dereferenciar sentMsg.id sem guarda lancava "Cannot read properties of undefined
// (reading 'id')", marcava fases entregues como falha e o circuit-breaker abortava o
// lote. A normalizacao deve aceitar retorno sem id e tambem o ID interno `$1` exposto
// pelo modelo instalado.
assert.doesNotMatch(sharedCore, /=\s*sentMsg\.id\._serialized/,
  'Retorno de sendMessage nao deve acessar _serialized diretamente (sentMsg pode ser undefined)');
assert.match(sharedCore, /function serializarIdMensagem\(id\)/,
  'Normalizador de ID do WhatsApp ausente');
assert.match(sharedCore, /serializarIdMensagem\(sentMsg && sentMsg\.id\)/,
  'Guarda defensiva do id de sendMessage ausente');

console.log('[OK] Contrato offline de WhatsApp validado.');
