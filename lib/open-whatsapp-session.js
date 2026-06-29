// Abre o Chrome com a sessao hub-global em modo visivel e mantem aberto ate Ctrl+C.
// Uso: node open-whatsapp-session.js [clientId]
const path = require('path');
const { Client, LocalAuth } = require('whatsapp-web.js');

const CLIENT_ID = process.argv[2] || 'hub-global';
const AUTH_PATH = path.join(__dirname, '.wwebjs_auth');

function log(nivel, msg) {
    const d = new Date();
    const p = n => String(n).padStart(2, '0');
    const ts = `${p(d.getDate())}/${p(d.getMonth()+1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
    console.log(`[${ts}] [${nivel}] ${msg}`);
}

const client = new Client({
    authStrategy: new LocalAuth({ dataPath: AUTH_PATH, clientId: CLIENT_ID }),
    takeoverOnConflict: true,
    puppeteer: {
        headless: false,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
    }
});

client.on('qr', () => {
    log('WARN', 'QR Code recebido — sessao expirada. Escaneie com o celular para reautenticar.');
});

client.on('loading_screen', (pct, msg) => {
    log('INFO', `Carregando: ${pct}% - ${msg}`);
});

client.on('authenticated', () => {
    log('INFO', 'Sessao autenticada.');
});

client.on('ready', () => {
    log('INFO', '=================================================');
    log('INFO', `Sessao "${CLIENT_ID}" pronta — navegador aberto.`);
    log('INFO', 'Envie as mensagens pendentes e feche quando terminar.');
    log('INFO', 'Para encerrar: Ctrl+C nesta janela.');
    log('INFO', '=================================================');
});

client.on('disconnected', (reason) => {
    log('WARN', `Desconectado: ${reason}`);
});

async function encerrar() {
    log('INFO', 'Encerrando sessao...');
    try { await client.destroy(); } catch (_) {}
    process.exit(0);
}

process.on('SIGINT',  encerrar);
process.on('SIGTERM', encerrar);

log('INFO', `Iniciando sessao "${CLIENT_ID}" em modo visivel...`);
client.initialize().catch(async (err) => {
    log('ERROR', `Falha ao inicializar: ${err.message}`);
    try { await client.destroy(); } catch (_) {}
    process.exit(1);
});
