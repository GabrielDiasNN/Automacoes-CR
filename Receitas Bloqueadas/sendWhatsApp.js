// {
//   "version": "1.3.0",
//   "skill": "ai-native-development-standard",
//   "contract": "whatsapp-bridge-protocol",
//   "description": "Notificador via WhatsApp Web (Soberano) - Protocolo de Persistencia de Ack",
//   "reliability": "Event-State-Tracking, Keep-Alive-Flush"
// }
const fs = require('fs');
const path = require('path');
const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');

const EXEC_ID = (process.argv[2] || '').trim();
const RUNTIME_MODE = String(process.argv[3] || '').trim().toUpperCase();
const CONFIG_FILE = path.join(__dirname, 'whatsapp-config.json');

function agoraBR() {
    const d = new Date();
    const p = n => String(n).padStart(2, '0');
    return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function log(nivel, mensagem) {
    const logDir = path.join(__dirname, 'Logs');
    if (!fs.existsSync(logDir)) { fs.mkdirSync(logDir, { recursive: true }); }
    const logFile = path.join(logDir, 'WhatsApp.log');
    const linha = `[${agoraBR()}] [NODE] [${nivel}] [ExecId:${EXEC_ID || 'sem-id'}] ${mensagem}\r\n`;
    try { fs.appendFileSync(logFile, linha, 'utf8'); } catch (_) { }
}

async function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

async function processar() {
    const config = JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf8'));
    log('INFO', '=== MOTOR SOBERANO V1.3 (PERSISTENCIA DE ACK) ===');

    const client = new Client({
        authStrategy: new LocalAuth({ dataPath: path.join(__dirname, '.wwebjs_auth'), clientId: 'receitas-bloqueadas' }),
        takeoverOnConflict: true,
        puppeteer: {
            headless: (RUNTIME_MODE === 'VISUAL') ? false : true,
            args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
        }
    });

    return new Promise((resolve, reject) => {
        let finalizado = false;
        let targetMsgId = null;
        let ackConfirmado = false;

        client.on('qr', () => {
            if (RUNTIME_MODE !== 'VISUAL') {
                log('WARN', 'Sessao expirada. Reautenticacao necessaria.');
                client.destroy();
                process.exit(21);
            }
        });

        client.on('message_ack', (msg, ack) => {
            if (targetMsgId && msg.id._serialized === targetMsgId) {
                log('INFO', `Evento ACK recebido: ID=${msg.id._serialized} | Nivel=${ack}`);
                if (ack >= 1) {
                    ackConfirmado = true;
                }
            }
        });

        client.on('ready', async () => {
            log('INFO', 'Conexao estabelecida. Iniciando protocolo de envio...');
            try {
                const phone = config.target.contactPhone.replace(/\D/g, '');
                const chatId = `${phone}@c.us`;
                
                // 1. Warming
                log('INFO', `Aquecendo canal para ${chatId}...`);
                await client.sendMessage(chatId, '\u231b _Iniciando transmissao do relatorio..._');
                await sleep(2000);

                // 2. Disparo do Anexo
                log('INFO', 'Enviando anexo Excel...');
                const media = MessageMedia.fromFilePath(config.paths.attachmentPath);
                const sentMsg = await client.sendMessage(chatId, media, { caption: '*Relatorio: Receitas Bloqueadas*' });
                targetMsgId = sentMsg.id._serialized;
                log('INFO', `Mensagem em fila local: ${targetMsgId}. Aguardando Ack do servidor...`);

                // 3. Keep-Alive Loop (Ate 60 segundos)
                // Mantemos o navegador ativo e monitoramos o estado ackConfirmado via evento
                for (let i = 1; i <= 30; i++) {
                    if (ackConfirmado) {
                        log('INFO', 'Confirmacao de recebimento pelo servidor detectada via evento.');
                        break;
                    }
                    // Simula atividade leve para nao deixar a aba "dormir"
                    if (client.pupPage) {
                        await client.pupPage.mouse.move(i, i);
                    }
                    await sleep(2000);
                }

                if (ackConfirmado) {
                    log('INFO', 'Entrega fisica garantida. Finalizando sessao com seguranca.');
                    await sleep(3000);
                    finalizado = true;
                    await client.destroy();
                    resolve();
                } else {
                    throw new Error('Falha de transmissao: O servidor do WhatsApp nao confirmou o recebimento da mensagem em 60s.');
                }
            } catch (e) {
                log('ERROR', `Erro no protocolo Soberano: ${e.message}`);
                finalizado = true;
                await client.destroy();
                reject(e);
            }
        });

        client.initialize().catch(err => {
            log('ERROR', `Erro na inicializacao: ${err.message}`);
            reject(err);
        });
    });
}

(async () => {
    try {
        await processar();
        log('INFO', 'Fluxo concluido com sucesso real.');
        process.exit(0);
    } catch (e) {
        if (e && e.message && e.message.includes('No LID for user')) {
            log('WARN', `Contato invalido / No LID: ${e.message}. Encerrando graciosamente sem falhar a automacao.`);
            process.exit(0);
        } else {
            log('ERROR', `ENCERRAMENTO POR FALHA: ${e.message}`);
            process.exit(24);
        }
    }
})();
