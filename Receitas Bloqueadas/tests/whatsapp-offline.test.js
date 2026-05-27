const assert = require('assert');
const fs = require('fs');
const path = require('path');

const automationRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(automationRoot, '..');
const localSenderPath = path.join(automationRoot, 'sendWhatsApp.js');
const sharedCorePath = path.join(repoRoot, 'lib', 'WhatsApp-Core.js');
const packageJsonPath = path.join(automationRoot, 'package.json');

function read(filePath) {
  return fs.readFileSync(filePath, 'utf8');
}

assert.ok(fs.existsSync(localSenderPath), 'sendWhatsApp.js deve existir');
assert.ok(fs.existsSync(sharedCorePath), 'lib/WhatsApp-Core.js deve existir');

const localSender = read(localSenderPath);
const sharedCore = read(sharedCorePath);
const packageJson = JSON.parse(read(packageJsonPath));

assert.strictEqual(packageJson.type, 'commonjs');
assert.ok(packageJson.scripts.test.includes('whatsapp-offline.test.js'));

assert.match(sharedCore, /const PHONE = \(process\.argv\[5\] \|\| ''\)\.replace\(\/\\D\/g, ''\);/);
assert.match(sharedCore, /INITIALIZE_MAX_ATTEMPTS = 2/);
assert.match(sharedCore, /ACK_WAIT_ATTEMPTS = 30/);
assert.match(sharedCore, /process\.exit\(21\)/);
assert.match(sharedCore, /process\.exit\(24\)/);
assert.match(sharedCore, /function describeError\(error\)/);
assert.doesNotMatch(sharedCore, /\b\d{10,13}@c\.us\b/);

assert.match(localSender, /LocalAuth/);
assert.match(localSender, /process\.exit\(21\)/);
assert.match(localSender, /process\.exit\(24\)/);
assert.doesNotMatch(localSender, /\b\d{10,13}@c\.us\b/);

console.log('[OK] Contrato offline de WhatsApp validado.');
