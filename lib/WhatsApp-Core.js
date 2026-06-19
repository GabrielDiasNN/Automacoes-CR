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

const INITIALIZE_MAX_ATTEMPTS = 2;
const INITIALIZE_RETRY_DELAY_MS = 5000;
const INITIALIZE_PROTOCOL_TIMEOUT_MS = 120000; // Timeout apenas para o bootstrap do cliente
const ACK_WAIT_ATTEMPTS = 90;
const ACK_WAIT_DELAY_MS = 2000;
const ACK_SETTLE_DELAY_MS = 3000;

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

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function describeError(error) {
    if (error instanceof Error) {
        const parts = [];
        parts.push(error.name || 'Error');
        parts.push(error.message || '(sem message)');

        if (typeof error.stack === 'string' && error.stack.trim()) {
            const stackPreview = error.stack
                .split('\n')
                .map(line => line.trim())
                .filter(Boolean)
                .slice(1, 4)
                .join(' <- ');
            if (stackPreview) {
                parts.push(`stack=${stackPreview}`);
            }
        }

        const extra = {};
        for (const key of Object.getOwnPropertyNames(error)) {
            if (['name', 'message', 'stack'].includes(key)) {
                continue;
            }
            extra[key] = error[key];
        }

        if (Object.keys(extra).length > 0) {
            try {
                parts.push(`extra=${JSON.stringify(extra)}`);
            } catch (_) {
                parts.push('extra=[nao serializavel]');
            }
        }

        return parts.join(' | ');
    }

    if (error === undefined) {
        return 'erro indefinido/sem payload';
    }

    if (error === null) {
        return 'erro nulo';
    }

    if (typeof error === 'string') {
        return error;
    }

    if (typeof error === 'object') {
        try {
            const json = JSON.stringify(error);
            if (json && json !== '{}') {
                return json;
            }
        } catch (_) {
            // Ignora e cai para String(error)
        }
    }

    try {
        return String(error);
    } catch (_) {
        return 'erro nao serializavel';
    }
}

function criarCliente() {
    return new Client({
        authStrategy: new LocalAuth({ dataPath: path.join(__dirname, '.wwebjs_auth'), clientId: CLIENT_ID }),
        takeoverOnConflict: true,
        puppeteer: {
            headless: (MODE === 'VISUAL') ? false : true,
            protocolTimeout: INITIALIZE_PROTOCOL_TIMEOUT_MS,
            args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
        }
    });
}

function shouldRetryInitialize(error) {
    const message = describeError(error);
    return /Runtime\.callFunctionOn timed out|Execution context was destroyed|protocol timeout|timed out/i.test(message);
}

async function destruirClienteSilenciosamente(client) {
    if (!client) { return; }
    try {
        await client.destroy();
    } catch (_) {
        // Melhor esforço: o processo pode ja ter sido encerrado pelo proprio runtime.
    }
}

async function aguardarAck(client, state) {
    writeLog('INFO', `Mensagem enviada em fila local (${state.targetMsgId}). Aguardando ACK do servidor...`);

    for (let i = 1; i <= ACK_WAIT_ATTEMPTS; i++) {
        if (state.ackConfirmado) {
            writeLog('INFO', 'Confirmacao de recebimento detectada via ACK.');
            return;
        }

        if (client.pupPage) {
            try {
                await client.pupPage.mouse.move(i, i);
            } catch (error) {
                writeLog('WARN', `Keep-alive do browser nao respondeu nesta iteracao: ${describeError(error)}`);
            }
        }

        await sleep(ACK_WAIT_DELAY_MS);
    }

    throw new Error('Falha de transmissao: O servidor do WhatsApp nao confirmou o recebimento da mensagem em 180s.');
}

async function executarFluxoComCliente(client) {
    return new Promise((resolve, reject) => {
        const state = {
            targetMsgId: null,
            ackConfirmado: false,
            finalized: false
        };

        const finalizeAndResolve = async () => {
            if (state.finalized) { return; }
            state.finalized = true;
            await destruirClienteSilenciosamente(client);
            resolve();
        };

        const finalizeAndReject = async (error) => {
            if (state.finalized) { return; }
            state.finalized = true;
            await destruirClienteSilenciosamente(client);
            reject(error);
        };

        client.on('qr', async () => {
            if (MODE !== 'VISUAL') {
                const error = new Error('Sessao expirada. Reautenticacao necessaria.');
                writeLog('WARN', error.message);
                await destruirClienteSilenciosamente(client);
                process.exit(21);
                return;
            }

            writeLog('INFO', 'QR Code recebido em modo VISUAL. Aguardando autenticacao manual.');
        });

        client.on('loading_screen', (percent, message) => {
            writeLog('INFO', `Bootstrap do browser em andamento: ${percent}% - ${message}`);
        });

        client.on('auth_failure', async (message) => {
            const error = new Error(`Falha de autenticacao/sessao do WhatsApp: ${message}`);
            writeLog('ERROR', error.message);
            await finalizeAndReject(error);
        });

        client.on('disconnected', async (reason) => {
            const error = new Error(`Cliente WhatsApp desconectado: ${reason}`);
            writeLog('WARN', error.message);
            await finalizeAndReject(error);
        });

        client.on('message_ack', (msg, ack) => {
            if (state.targetMsgId && msg.id._serialized === state.targetMsgId) {
                writeLog('INFO', `Evento ACK recebido: ID=${msg.id._serialized} | Nivel=${ack}`);
                if (ack >= 1) {
                    state.ackConfirmado = true;
                }
            }
        });

        client.on('ready', async () => {
            try {
                writeLog('INFO', 'Cliente WhatsApp pronto. Iniciando protocolo de envio...');
                const phone = PHONE;
                const chatId = `${phone}@c.us`;

                writeLog('INFO', `Aquecendo canal para ${chatId}...`);
                await client.sendMessage(chatId, '\u231b _Iniciando transmissao do relatorio..._');
                await sleep(2000);

                let sentMsg;
                if (ATTACHMENT_PATH && fs.existsSync(ATTACHMENT_PATH)) {
                    writeLog('INFO', 'Enviando anexo Excel...');
                    const media = MessageMedia.fromFilePath(ATTACHMENT_PATH);
                    sentMsg = await client.sendMessage(chatId, media, { caption: CAPTION });
                } else {
                    writeLog('WARN', 'Anexo ausente ou nao encontrado. Enviando apenas a mensagem de texto.');
                    sentMsg = await client.sendMessage(chatId, CAPTION);
                }
                state.targetMsgId = sentMsg.id._serialized;

                await aguardarAck(client, state);

                writeLog('INFO', 'Entrega fisica garantida. Finalizando sessao com seguranca.');
                await sleep(ACK_SETTLE_DELAY_MS);
                await finalizeAndResolve();
            } catch (error) {
                writeLog('ERROR', `Erro no protocolo Soberano: ${describeError(error)}`);
                await finalizeAndReject(error);
            }
        });

        writeLog('INFO', `Inicializando cliente WhatsApp (bootstrap) com protocolTimeout=${INITIALIZE_PROTOCOL_TIMEOUT_MS}ms...`);
        client.initialize().catch(async (error) => {
            writeLog('ERROR', `Erro na inicializacao do WhatsApp: ${describeError(error)}`);
            await finalizeAndReject(error);
        });
    });
}

async function processar() {
    writeLog('INFO', '=== MOTOR SOBERANO V1.3 (PERSISTENCIA DE ACK) ===');

    if (!PHONE) {
        throw new Error('Telefone de destino ausente.');
    }

    if (!CAPTION) {
        throw new Error('Mensagem vazia.');
    }

    for (let attempt = 1; attempt <= INITIALIZE_MAX_ATTEMPTS; attempt++) {
        const client = criarCliente();

        try {
            writeLog('INFO', `Bootstrap do WhatsApp iniciado (tentativa ${attempt}/${INITIALIZE_MAX_ATTEMPTS}).`);
            await executarFluxoComCliente(client);
            return;
        } catch (error) {
            await destruirClienteSilenciosamente(client);

            if (shouldRetryInitialize(error) && attempt < INITIALIZE_MAX_ATTEMPTS) {
                writeLog('WARN', `Falha transiente na inicializacao do WhatsApp: ${describeError(error)}. Retentando em ${INITIALIZE_RETRY_DELAY_MS}ms...`);
                await sleep(INITIALIZE_RETRY_DELAY_MS);
                continue;
            }

            throw error;
        }
    }
}

(async () => {
    try {
        await processar();
        writeLog('INFO', 'Fluxo concluido com sucesso real.');
        process.exit(0);
    } catch (e) {
        const errorDetails = describeError(e);
        if (errorDetails.includes('No LID for user')) {
            writeLog('WARN', `Contato invalido / No LID: ${errorDetails}. Encerrando graciosamente sem falhar a automacao.`);
            process.exit(0);
        } else {
            writeLog('ERROR', `ENCERRAMENTO POR FALHA: ${errorDetails}`);
            process.exit(24);
        }
    }
})();
