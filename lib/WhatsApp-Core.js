// {
//   "name": "whatsapp-core",
//   "version": "2.7.0",
//   "skill": "nodejs-communications",
//   "description": "Motor Global de Mensageria WhatsApp (Soberano) - 100% Parametrizado",
//   "reliability": "Retry-Handshake, Ack-Persistence, Path-Portability, Batch-Mode"
// }
const fs = require('fs');
const path = require('path');
const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');

// Parametros via CLI
const EXEC_ID = (process.argv[2] || 'manual');
const MODE = (process.argv[3] || 'AUTO').toUpperCase(); // AUTO, VISUAL, LIST_GROUPS, BATCH
const CLIENT_ID = (process.argv[4] || 'default-client');
// Aceita número puro (ex: DDI+DDD+numero) ou chatId completo (numero@c.us / GROUPID@g.us)
const CONTACT_ARG = (process.argv[5] || '');
// BATCH mode: argv[6] = caminho do arquivo de lote (JSON), argv[7] = arquivo de resultado
const ATTACHMENT_PATH = (MODE !== 'BATCH' && process.argv[6]) ? path.resolve(process.argv[6]) : null;
const CAPTION = (MODE !== 'BATCH') ? (process.argv[7] || '*Alerta de Automacao*') : '';
const LOG_FILE = process.argv[8] ? path.resolve(process.argv[8]) : null;
const BATCH_FILE = (MODE === 'BATCH' && process.argv[6]) ? path.resolve(process.argv[6]) : null;
const BATCH_RESULT_FILE = (MODE === 'BATCH' && process.argv[7]) ? path.resolve(process.argv[7]) : null;

const INITIALIZE_MAX_ATTEMPTS = 3;
const INITIALIZE_RETRY_DELAY_MS = 5000;
const INITIALIZE_PROTOCOL_TIMEOUT_MS = 120000; // Timeout apenas para o bootstrap do cliente
const ACK_WAIT_ATTEMPTS = 90;
const ACK_WAIT_DELAY_MS = 2000;
const ACK_SETTLE_DELAY_MS = 30000;     // 30s de dreno pós-lote antes de destruir o cliente
// Modo batch: settle e ACK — mídia (imagem) exige CDN upload antes do ACK, independente do bootstrap
const BATCH_SETTLE_MS_NORMAL = 40000;  // 40s settle pós-ready (igual ao retry — upload de mídia precisa de tempo)
const BATCH_SETTLE_MS_RETRY  = 40000;  // 40s após retry — conexão demonstrou instabilidade
const ACK_WAIT_ATTEMPTS_BATCH_NORMAL = 60; // 60 × 2s = 120s por mensagem (imagens precisam de tempo de CDN)
const ACK_WAIT_ATTEMPTS_BATCH_RETRY  = 75; // 75 × 2s = 150s por mensagem (após retry)

function agoraBR() {
    const d = new Date();
    const p = n => String(n).padStart(2, '0');
    return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function writeLog(nivel, mensagem) {
    const linha = `[${agoraBR()}] [NODE-WA] [${nivel}] [ExecId:${EXEC_ID}] ${mensagem}`;
    console.log(linha);
    if (!LOG_FILE) return;
    const logDir = path.dirname(LOG_FILE);
    if (!fs.existsSync(logDir)) { fs.mkdirSync(logDir, { recursive: true }); }
    try { fs.appendFileSync(LOG_FILE, linha + '\r\n', 'utf8'); } catch (_) { }
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

function cleanProfileForRetry(clientId) {
    // Remove apenas LOCK files — .log são dados de sessão válidos e NÃO devem ser apagados
    const sessionDir = path.join(__dirname, '.wwebjs_auth', `session-${clientId}`, 'Default');
    const dirs = [
        'Local Storage/leveldb', 'Session Storage', 'Service Worker/Database',
        'GCM Store', 'shared_proto_db', 'Sync Data/LevelDB',
    ];
    for (const rel of dirs) {
        const dir = path.join(sessionDir, rel.replace(/\//g, path.sep));
        if (!fs.existsSync(dir)) continue;
        try {
            for (const f of fs.readdirSync(dir)) {
                if (f === 'LOCK') {
                    try { fs.unlinkSync(path.join(dir, f)); } catch (_) {}
                }
            }
        } catch (_) {}
    }
    // LOCK raiz do perfil
    const rootLock = path.join(sessionDir, 'LOCK');
    try { if (fs.existsSync(rootLock)) fs.unlinkSync(rootLock); } catch (_) {}
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

async function verificarEstadoConectado(client, contexto) {
    // Apos o evento 'ready', o canal WebSocket pode ainda nao estar estavel para transmitir.
    // getState() CONNECTED confirma que a conexao com os servidores do WhatsApp esta ativa.
    const MAX_ESPERA_MS = 30000;
    const INTERVALO_MS  = 3000;
    let esperado = 0;
    while (esperado < MAX_ESPERA_MS) {
        try {
            const state = await client.getState();
            if (state === 'CONNECTED') {
                writeLog('INFO', `[${contexto}] Estado confirmado: CONNECTED.`);
                return true;
            }
            writeLog('WARN', `[${contexto}] Estado atual: ${state} — aguardando CONNECTED (${esperado / 1000}s / ${MAX_ESPERA_MS / 1000}s)...`);
        } catch (_) {
            writeLog('WARN', `[${contexto}] getState() falhou — aguardando...`);
        }
        await sleep(INTERVALO_MS);
        esperado += INTERVALO_MS;
    }
    writeLog('WARN', `[${contexto}] Estado nao confirmado como CONNECTED em ${MAX_ESPERA_MS / 1000}s — prosseguindo com cautela.`);
    return false;
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
                await verificarEstadoConectado(client, 'AUTO');
                const chatId = CONTACT_ARG.includes('@')
                    ? CONTACT_ARG
                    : `${CONTACT_ARG.replace(/\D/g, '')}@c.us`;

                // Warmup apenas para contatos individuais (grupos recebem apenas a mensagem principal)
                if (!chatId.endsWith('@g.us')) {
                    writeLog('INFO', `Aquecendo canal para ${chatId}...`);
                    await client.sendMessage(chatId, '\u231b _Iniciando transmissao do relatorio..._');
                    await sleep(2000);
                }

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

    if (!CONTACT_ARG) {
        throw new Error('Telefone/chatId de destino ausente.');
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
                cleanProfileForRetry(CLIENT_ID);
                await sleep(INITIALIZE_RETRY_DELAY_MS);
                continue;
            }

            throw error;
        }
    }
}

async function aguardarAckBatch(client, state, phaseKey, maxAttempts) {
    const timeoutSec = maxAttempts * ACK_WAIT_DELAY_MS / 1000;
    writeLog('INFO', `[BATCH] ${phaseKey}: Aguardando ACK (até ${timeoutSec}s)...`);
    for (let i = 1; i <= maxAttempts; i++) {
        if (state.ackConfirmado) {
            writeLog('INFO', `[BATCH] ${phaseKey}: ACK confirmado.`);
            return true;
        }
        if (client.pupPage) {
            try { await client.pupPage.mouse.move(i, i); } catch (_) {}
        }
        await sleep(ACK_WAIT_DELAY_MS);
    }
    writeLog('WARN', `[BATCH] ${phaseKey}: ACK nao confirmado em ${timeoutSec}s — mensagem esta na fila local do WhatsApp.`);
    return false; // nao bloqueia — mensagem foi enviada para a fila
}

async function executarFluxoBatch(client, itens, chatId, bootstrapAttempt) {
    const ackAttempts = bootstrapAttempt > 1 ? ACK_WAIT_ATTEMPTS_BATCH_RETRY : ACK_WAIT_ATTEMPTS_BATCH_NORMAL;
    if (bootstrapAttempt > 1) {
        writeLog('INFO', `[BATCH] Bootstrap precisou de ${bootstrapAttempt} tentativas — usando ACK timeout estendido (${ackAttempts * ACK_WAIT_DELAY_MS / 1000}s/msg).`);
    }
    const resultados = [];
    const MAX_CONSECUTIVE_FAILURES = 2;
    let consecutiveFailures = 0;

    for (const item of itens) {
        const { phase_key, image_path, caption } = item;
        const imgPath = path.resolve(image_path);
        writeLog('INFO', `[BATCH] Enviando fase: ${phase_key}...`);

        let success = false;
        let error = null;

        try {
            if (!fs.existsSync(imgPath)) {
                throw new Error(`Imagem nao encontrada: ${imgPath}`);
            }
            const media = MessageMedia.fromFilePath(imgPath);

            // --- TENTATIVA 1 ---
            const ackState = { targetMsgId: null, ackConfirmado: false };
            const ackListener = (msg, ack) => {
                if (ackState.targetMsgId && msg.id._serialized === ackState.targetMsgId && ack >= 1) {
                    ackState.ackConfirmado = true;
                }
            };
            client.on('message_ack', ackListener);

            try {
                const sentMsg = await client.sendMessage(chatId, media, { caption });
                ackState.targetMsgId = sentMsg.id._serialized;
                writeLog('INFO', `[BATCH] ${phase_key}: Enviado para fila local (${ackState.targetMsgId}).`);
                let acked = await aguardarAckBatch(client, ackState, phase_key, ackAttempts);
                
                if (acked) {
                    success = true;
                    writeLog('INFO', `[BATCH] ${phase_key}: Entrega confirmada pelo servidor.`);
                } else {
                    writeLog('WARN', `[BATCH] ${phase_key}: ACK nao confirmado na Tentativa 1/2. Iniciar Retry 1/1...`);
                    
                    // --- RETRY (TENTATIVA 2) ---
                    client.removeListener('message_ack', ackListener);
                    const retryState = { targetMsgId: null, ackConfirmado: false };
                    const retryListener = (msg, ack) => {
                        if (retryState.targetMsgId && msg.id._serialized === retryState.targetMsgId && ack >= 1) {
                            retryState.ackConfirmado = true;
                        }
                    };
                    client.on('message_ack', retryListener);

                    try {
                        const retryMsg = await client.sendMessage(chatId, media, { caption });
                        retryState.targetMsgId = retryMsg.id._serialized;
                        writeLog('INFO', `[BATCH] ${phase_key}: (Retry) Enviado para fila local (${retryState.targetMsgId}).`);
                        let retryAcked = await aguardarAckBatch(client, retryState, phase_key + ' (Retry)', ackAttempts);
                        
                        if (retryAcked) {
                            success = true;
                            writeLog('INFO', `[BATCH] ${phase_key}: Entrega confirmada pelo servidor na tentativa de Retry.`);
                        } else {
                            writeLog('WARN', `[BATCH] ${phase_key}: ACK nao confirmado no Retry.`);
                            success = false;
                        }
                    } finally {
                        client.removeListener('message_ack', retryListener);
                    }
                }
            } finally {
                client.removeListener('message_ack', ackListener);
            }
        } catch (err) {
            error = err.message || String(err);
            writeLog('ERROR', `[BATCH] ${phase_key}: Falha — ${error}`);
            success = false;
        }

        resultados.push({ phase_key, success, error });

        if (success) {
            consecutiveFailures = 0;
        } else {
            consecutiveFailures++;
            if (consecutiveFailures >= MAX_CONSECUTIVE_FAILURES) {
                writeLog('ERROR', `[CIRCUIT-BREAKER] ${consecutiveFailures} falhas consecutivas detectadas. Abortando lote.`);
                const remainingStartIndex = itens.indexOf(item) + 1;
                for (let i = remainingStartIndex; i < itens.length; i++) {
                    resultados.push({
                        phase_key: itens[i].phase_key,
                        success: false,
                        error: 'CIRCUIT_BREAKER_ABORT'
                    });
                }
                break;
            }
        }

        if (itens.indexOf(item) < itens.length - 1 && consecutiveFailures < MAX_CONSECUTIVE_FAILURES) {
            await sleep(3000); // pausa entre mensagens na mesma sessão
        }
    }

    return resultados;
}

// Modo de listagem de grupos: lista todos os grupos disponíveis na sessão e sai
if (MODE === 'LIST_GROUPS') {
    (async () => {
        const client = criarCliente();
        client.on('qr', () => {
            writeLog('WARN', 'QR necessario — use um clientId ja autenticado ou rode em modo VISUAL.');
            process.exit(21);
        });
        client.on('ready', async () => {
            try {
                const chats = await client.getChats();
                const groups = chats
                    .filter(c => c.isGroup)
                    .map(c => ({ id: c.id._serialized, name: c.name }));
                console.log(JSON.stringify(groups, null, 2));
                await destruirClienteSilenciosamente(client);
                process.exit(0);
            } catch (err) {
                writeLog('ERROR', `Erro ao listar grupos: ${describeError(err)}`);
                await destruirClienteSilenciosamente(client);
                process.exit(24);
            }
        });
        client.initialize().catch(err => {
            writeLog('ERROR', `Erro ao inicializar cliente: ${describeError(err)}`);
            process.exit(24);
        });
    })();
} else if (MODE === 'BATCH') {
(async () => {
    writeLog('INFO', '=== MOTOR SOBERANO V2.1 (MODO BATCH) ===');
    if (!BATCH_FILE || !fs.existsSync(BATCH_FILE)) {
        writeLog('ERROR', `Arquivo de lote nao encontrado: ${BATCH_FILE}`);
        process.exit(24);
    }
    if (!CONTACT_ARG) {
        writeLog('ERROR', 'chatId de destino ausente.');
        process.exit(24);
    }

    let itens;
    try {
        let batchContent = fs.readFileSync(BATCH_FILE, 'utf8');
        if (batchContent.charCodeAt(0) === 0xFEFF) batchContent = batchContent.slice(1); // strip BOM
        itens = JSON.parse(batchContent);
    } catch (e) {
        writeLog('ERROR', `Falha ao ler arquivo de lote: ${e.message}`);
        process.exit(24);
    }

    if (!Array.isArray(itens) || itens.length === 0) {
        writeLog('WARN', 'Lote vazio — nada a enviar.');
        process.exit(0);
    }

    const chatId = CONTACT_ARG.includes('@') ? CONTACT_ARG : `${CONTACT_ARG.replace(/\D/g, '')}@c.us`;

    for (let attempt = 1; attempt <= INITIALIZE_MAX_ATTEMPTS; attempt++) {
        const client = criarCliente();
        try {
            writeLog('INFO', `Bootstrap do WhatsApp iniciado (tentativa ${attempt}/${INITIALIZE_MAX_ATTEMPTS}).`);
            writeLog('INFO', `Inicializando cliente WhatsApp (bootstrap) com protocolTimeout=${INITIALIZE_PROTOCOL_TIMEOUT_MS}ms...`);

            const resultados = await new Promise((resolve, reject) => {
                client.on('qr', async () => {
                    if (MODE !== 'VISUAL') {
                        writeLog('WARN', 'Sessao expirada. Reautenticacao necessaria.');
                        await destruirClienteSilenciosamente(client);
                        process.exit(21);
                    }
                });
                client.on('auth_failure', async (msg) => {
                    await destruirClienteSilenciosamente(client);
                    reject(new Error(`Falha de autenticacao: ${msg}`));
                });
                client.on('disconnected', async (reason) => {
                    await destruirClienteSilenciosamente(client);
                    reject(new Error(`Desconectado: ${reason}`));
                });
                client.on('loading_screen', (pct, msg) => {
                    writeLog('INFO', `Bootstrap: ${pct}% - ${msg}`);
                });
                client.on('ready', async () => {
                    const settleMs = attempt > 1 ? BATCH_SETTLE_MS_RETRY : BATCH_SETTLE_MS_NORMAL;
                    writeLog('INFO', `Cliente pronto. Aguardando estabilizacao do WhatsApp Web (${settleMs / 1000}s)...`);
                    await sleep(settleMs);
                    await verificarEstadoConectado(client, 'BATCH');
                    try {
                        writeLog('INFO', `Processando ${itens.length} fases em lote...`);
                        const res = await executarFluxoBatch(client, itens, chatId, attempt);
                        writeLog('INFO', `Dreno pos-lote: mantendo cliente ativo por ${ACK_SETTLE_DELAY_MS / 1000}s para uploads pendentes...`);
                        for (let d = 0; d < ACK_SETTLE_DELAY_MS; d += 3000) {
                            await sleep(3000);
                            if (client.pupPage) {
                                try { await client.pupPage.mouse.move(d % 50, d % 50); } catch (_) {}
                            }
                        }
                        await destruirClienteSilenciosamente(client);
                        resolve(res);
                    } catch (err) {
                        await destruirClienteSilenciosamente(client);
                        reject(err);
                    }
                });
                client.initialize().catch(async (err) => {
                    writeLog('ERROR', `Erro na inicializacao: ${describeError(err)}`);
                    await destruirClienteSilenciosamente(client);
                    reject(err);
                });
            });

            if (BATCH_RESULT_FILE) {
                fs.writeFileSync(BATCH_RESULT_FILE, JSON.stringify(resultados, null, 2), 'utf8');
            }
            const falhas = resultados.filter(r => !r.success).length;
            writeLog('INFO', `Lote concluido: ${resultados.length - falhas}/${resultados.length} enviados.`);
            process.exit(falhas > 0 ? 4 : 0);

        } catch (error) {
            await destruirClienteSilenciosamente(client);
            if (shouldRetryInitialize(error) && attempt < INITIALIZE_MAX_ATTEMPTS) {
                writeLog('WARN', `Falha transiente: ${describeError(error)}. Retentando em ${INITIALIZE_RETRY_DELAY_MS}ms...`);
                cleanProfileForRetry(CLIENT_ID);
                await sleep(INITIALIZE_RETRY_DELAY_MS);
                continue;
            }
            writeLog('ERROR', `ENCERRAMENTO POR FALHA: ${describeError(error)}`);
            process.exit(24);
        }
    }
})();
} else if (MODE === 'VISUAL' && !CONTACT_ARG) {
// Auth-only: abre Chrome visivel, aguarda QR scan e sai apos ready
(async () => {
    writeLog('INFO', '=== AUTENTICACAO VISUAL (auth-only) ===');
    const client = criarCliente();
    client.on('qr', () => {
        writeLog('INFO', 'QR Code recebido. Escaneie com o celular para autenticar.');
    });
    client.on('loading_screen', (pct, msg) => {
        writeLog('INFO', `Carregando: ${pct}% - ${msg}`);
    });
    client.on('authenticated', () => {
        writeLog('INFO', 'Sessao autenticada com sucesso.');
    });
    client.on('ready', async () => {
        writeLog('INFO', 'Cliente pronto — sessao hub-global ativa. Encerrando autenticador.');
        try { await client.destroy(); } catch (_) {}
        process.exit(0);
    });
    client.on('auth_failure', async (msg) => {
        writeLog('ERROR', `Falha de autenticacao: ${msg}`);
        try { await client.destroy(); } catch (_) {}
        process.exit(24);
    });
    client.initialize().catch(async (err) => {
        writeLog('ERROR', `Erro ao inicializar: ${describeError(err)}`);
        try { await client.destroy(); } catch (_) {}
        process.exit(24);
    });
})();
} else {
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
} // fim else (não LIST_GROUPS/BATCH)
