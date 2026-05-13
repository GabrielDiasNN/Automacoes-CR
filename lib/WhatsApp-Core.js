// {
//   "name": "whatsapp-core",
//   "version": "2.0.0",
//   "skill": "nodejs-communications",
//   "description": "Motor Global de Mensageria WhatsApp (Soberano) - 100% Parametrizado",
//   "reliability": "Retry-Handshake, Ack-Persistence, Path-Portability"
// }
const fs = require('fs');
const path = require('path');
const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');

// Parametros via CLI
const EXEC_ID = (process.argv[2] || 'manual');
const MODE = (process.argv[3] || 'AUTO').toUpperCase(); // AUTO ou VISUAL
const CLIENT_ID = (process.argv[4] || 'default-client');
const PHONE = (process.argv[5] || '').replace(/\D/g, '');
const ATTACHMENT_PATH = process.argv[6] ? path.resolve(process.argv[6]) : null;
const CAPTION = (process.argv[7] || '*Alerta de Automacao*');
const LOG_FILE = process.argv[8] ? path.resolve(process.argv[8]) : null;

function agoraBR() {
    const d = new Date();
    const p = n => String(n).padStart(2, '0');
    return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function writeLog(nivel, mensagem) {
    if (!LOG_FILE) return;
    const logDir = path.dirname(LOG_FILE);
    if (!fs.existsSync(logDir)) { fs.mkdirSync(logDir, { recursive: true }); }
    const linha = `[${agoraBR()}] [NODE-WA] [${nivel}] [ExecId:${EXEC_ID}] ${mensagem}\r\n`;
    try { fs.appendFileSync(LOG_FILE, linha, 'utf8'); } catch (_) { }
    console.log(linha.trim());
}

async function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

async function start() {
    writeLog('INFO', `Iniciando Motor Global WA para ${PHONE} [ClientId: ${CLIENT_ID}]`);

    const client = new Client({
        authStrategy: new LocalAuth({ dataPath: path.join(__dirname, '.wwebjs_auth'), clientId: CLIENT_ID }),
        takeoverOnConflict: true,
        puppeteer: {
            headless: (MODE === 'VISUAL') ? false : true,
            args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
        }
    });

    return new Promise((resolve, reject) => {
        let ackConfirmado = false;
        let targetMsgId = null;

        client.on('qr', () => {
            if (MODE !== 'VISUAL') {
                writeLog('WARN', 'Sessao expirada. Reautenticacao necessaria via modo VISUAL.');
                client.destroy();
                process.exit(21);
            }
        });

        client.on('message_ack', (msg, ack) => {
            if (targetMsgId && msg.id._serialized === targetMsgId) {
                if (ack >= 1) ackConfirmado = true;
            }
        });

        client.on('ready', async () => {
            writeLog('INFO', 'Conexao pronta. Enviando...');
            try {
                const chatId = `${PHONE}@c.us`;

                if (ATTACHMENT_PATH && fs.existsSync(ATTACHMENT_PATH)) {
                    const media = MessageMedia.fromFilePath(ATTACHMENT_PATH);
                    const sentMsg = await client.sendMessage(chatId, media, { caption: CAPTION });
                    targetMsgId = sentMsg.id._serialized;
                } else {
                    const sentMsg = await client.sendMessage(chatId, CAPTION);
                    targetMsgId = sentMsg.id._serialized;
                }

                writeLog('INFO', `Mensagem enviada (${targetMsgId}). Aguardando confirmação...`);

                // Wait for ACK
                for (let i = 0; i < 30; i++) {
                    if (ackConfirmado) break;
                    await sleep(2000);
                }

                if (ackConfirmado) {
                    writeLog('INFO', 'Entrega confirmada pelo servidor.');
                    await sleep(2000);
                    await client.destroy();
                    resolve();
                } else {
                    throw new Error('Timeout: Servidor nao confirmou entrega em 60s.');
                }
            } catch (e) {
                writeLog('ERROR', `Erro no envio: ${e.message}`);
                await client.destroy();
                reject(e);
            }
        });

        client.initialize().catch(err => {
            writeLog('ERROR', `Erro na inicializacao: ${err.message}`);
            reject(err);
        });
    });
}

start().then(() => {
    writeLog('INFO', 'Processo finalizado com sucesso.');
    process.exit(0);
}).catch(err => {
    writeLog('ERROR', `Falha fatal: ${err.message}`);
    process.exit(1);
});
