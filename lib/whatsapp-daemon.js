// Daemon persistente do WhatsApp (opt-in). Mantem um cliente whatsapp-web.js pronto em
// processo de vida longa e recebe lotes por HTTP local (127.0.0.1), evitando o bootstrap
// do Chromium (10-25 s) a cada envio. Desligado por padrao: so e' usado quando
// WHATSAPP_DAEMON_ENABLED=1 (decidido em Send-WhatsApp.ps1 / Lib-WhatsAppBatch.psm1).
//
// Nao altera o comportamento de WhatsApp-Core.js: reutiliza exatamente o mesmo motor
// (executarFluxoBatch, criarCliente, destruirClienteSilenciosamente, ...).
//
// Estados: starting -> warming (apos 'ready', espera o settle) -> ready; queda -> reconnecting.
// Antes de cada lote: verificarEstadoConectado (sem CONNECTED -> 503 not_connected e reconexao).
// Vigia periodico: getState() com prazo, fora de lotes; resultado diferente de CONNECTED reconecta.
// Rotas autenticadas: POST /batch (lote de cards) e POST /send (mensagem unica, texto ou anexo,
// usada pelo AUTO). Ambas exigem client_id igual ao do daemon (senao 409 client_mismatch) e
// dividem a mesma fila serial, com a mesma conferencia de CONNECTED antes de cada envio.
// Teto sem 'ready' (WHATSAPP_DAEMON_MAX_NOT_READY_MS, padrao 600 s): tempo continuo fora de 'ready'
// acima do teto encerra o daemon com exit 1 (depois de destruir o cliente), para os envios voltarem
// ao modo por processo em vez de adiar com exit 22 sem alarme.
'use strict';

const http = require('http');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const TOKEN_MIN_LENGTH = 32;
const PORT_PADRAO = 8765;
const CLIENT_ID_PADRAO = 'hub-global';
const MAX_BODY_BYTES = 1024 * 1024; // 1 MB
const CABECALHO_AUTENTICACAO = 'x-hub-daemon-token';
// Backoff de reconexao: 30 s, 60 s, 120 s, teto 300 s.
const BACKOFF_MS = [30000, 60000, 120000, 300000];
const EXIT_SESSAO_AUSENTE = 21;
// Vigia periodico: intervalo padrao e prazo de getState() (controlado aqui, sem Promise do core).
const WATCHDOG_MS_PADRAO = 60000;
const WATCHDOG_TIMEOUT_MS_PADRAO = 15000;
// Teto sem 'ready' (ms): tempo continuo fora de 'ready' que encerra o daemon com EXIT_TETO_SEM_READY.
const MAX_NOT_READY_MS_PADRAO = 600000;
const EXIT_TETO_SEM_READY = 1;
// Prazo para destruir o cliente antes de sair por codigo (o Chromium pode travar ao fechar).
const DESTRUIR_PRAZO_MS_PADRAO = 15000;

function backoffPadrao(tentativa) {
    const indice = Math.min(tentativa, BACKOFF_MS.length - 1);
    return BACKOFF_MS[indice];
}

// WHATSAPP_DAEMON_MAX_NOT_READY_MS: so vale como inteiro positivo; qualquer outro valor usa o padrao.
function lerMaxNotReadyMs(texto) {
    const valor = Number(texto);
    return Number.isInteger(valor) && valor > 0 ? valor : undefined;
}

// Executa fn() com prazo: rejeita quando estoura ms. O timer e' limpo ao fim da corrida.
function comPrazo(fn, ms) {
    let timer = null;
    const estouro = new Promise((_, rejeitar) => {
        timer = setTimeout(() => rejeitar(new Error(`prazo de ${ms} ms estourado`)), ms);
    });
    return Promise.race([Promise.resolve().then(fn), estouro]).finally(() => clearTimeout(timer));
}

function tokenValido(token) {
    return typeof token === 'string' && token.length >= TOKEN_MIN_LENGTH;
}

// Comparacao em tempo constante. Tamanhos diferentes sao recusados antes do timingSafeEqual
// (que lanca quando os buffers tem tamanhos distintos).
function tokenConfere(recebido, esperado) {
    if (typeof recebido !== 'string') { return false; }
    const a = Buffer.from(recebido, 'utf8');
    const b = Buffer.from(esperado, 'utf8');
    if (a.length !== b.length) { return false; }
    return crypto.timingSafeEqual(a, b);
}

function normalizarChatId(valor) {
    // Mesma regra de executarModoBatch em WhatsApp-Core.js.
    return valor.includes('@') ? valor : `${valor.replace(/\D/g, '')}@c.us`;
}

function validarCorpoBatch(corpo) {
    if (!corpo || typeof corpo !== 'object' || Array.isArray(corpo)) {
        return 'corpo deve ser um objeto JSON';
    }
    if (typeof corpo.exec_id !== 'string' || corpo.exec_id.trim() === '') {
        return 'exec_id ausente ou invalido';
    }
    if (typeof corpo.chat_id !== 'string' || corpo.chat_id.trim() === '') {
        return 'chat_id ausente ou invalido';
    }
    if (!Array.isArray(corpo.items) || corpo.items.length === 0) {
        return 'items deve ser uma lista nao vazia';
    }
    for (const item of corpo.items) {
        if (!item || typeof item !== 'object') { return 'item invalido'; }
        if (typeof item.phase_key !== 'string' || item.phase_key.trim() === '') {
            return 'item sem phase_key';
        }
        if (typeof item.image_path !== 'string' || item.image_path.trim() === '') {
            return 'item sem image_path';
        }
        if (typeof item.caption !== 'string') {
            return 'item sem caption (string)';
        }
    }
    // Por ultimo: as mensagens de validacao anteriores permanecem as mesmas para corpos sem client_id.
    if (typeof corpo.client_id !== 'string' || corpo.client_id.trim() === '') {
        return 'client_id ausente ou invalido';
    }
    return null;
}

// Contrato de POST /send: mensagem unica (texto ou anexo) para um chat.
function validarCorpoEnvio(corpo) {
    if (!corpo || typeof corpo !== 'object' || Array.isArray(corpo)) {
        return 'corpo deve ser um objeto JSON';
    }
    if (typeof corpo.exec_id !== 'string' || corpo.exec_id.trim() === '') {
        return 'exec_id ausente ou invalido';
    }
    if (typeof corpo.chat_id !== 'string' || corpo.chat_id.trim() === '') {
        return 'chat_id ausente ou invalido';
    }
    if (typeof corpo.client_id !== 'string' || corpo.client_id.trim() === '') {
        return 'client_id ausente ou invalido';
    }
    if (typeof corpo.caption !== 'string' || corpo.caption.trim() === '') {
        return 'caption ausente ou vazia';
    }
    const anexo = corpo.attachment_path;
    if (anexo !== null && anexo !== undefined && (typeof anexo !== 'string' || anexo.trim() === '')) {
        return 'attachment_path deve ser string nao vazia ou null';
    }
    return null;
}

// Anexo informado precisa existir como arquivo. E' checado antes de enfileirar (400, sem tocar na fila).
function anexoInexistente(corpo) {
    if (!corpo.attachment_path) { return false; }
    try {
        return !fs.statSync(path.resolve(corpo.attachment_path)).isFile();
    } catch (_) {
        return true;
    }
}

function responderJson(res, status, corpo, cabecalhosExtras = {}) {
    const texto = JSON.stringify(corpo);
    res.writeHead(status, {
        'Content-Type': 'application/json; charset=utf-8',
        'Content-Length': Buffer.byteLength(texto, 'utf8'),
        ...cabecalhosExtras
    });
    res.end(texto);
}

/**
 * Fabrica testavel do daemon.
 * @param {object} opts
 * @param {string} opts.token      Token de acesso (>= 32 caracteres). Obrigatorio.
 * @param {number} [opts.port]     Porta em 127.0.0.1. Padrao 8765.
 * @param {string} [opts.clientId] Perfil do WhatsApp. Padrao 'hub-global'.
 * @param {object} opts.core       Motor (WhatsApp-Core.js ou dublê de teste).
 * @param {function} [opts.backoffMs] (tentativa) => ms. Padrao: 30/60/120/300 s.
 * @param {function} [opts.sair]   (codigo) => void. Padrao: process.exit.
 * @param {number} [opts.settleMs] Acomodacao apos 'ready' antes de aceitar lotes (state 'warming').
 *                                 Padrao: core.BATCH_SETTLE_MS_NORMAL.
 * @param {number} [opts.watchdogMs] Intervalo do vigia de conexao. Padrao 60000.
 * @param {number} [opts.watchdogTimeoutMs] Prazo de getState() no vigia. Padrao 15000.
 * @param {number} [opts.maxNotReadyMs] Teto de tempo continuo fora de 'ready' (ms); estourado: exit 1.
 *                                      Padrao 600000.
 * @param {number} [opts.destruirPrazoMs] Prazo de destruirClienteSilenciosamente no encerramento. Padrao 15000.
 */
function criarDaemon(opts) {
    const { token, core } = opts || {};
    if (!tokenValido(token)) {
        throw new Error(`WHATSAPP_DAEMON_TOKEN ausente ou com menos de ${TOKEN_MIN_LENGTH} caracteres`);
    }
    if (!core) {
        throw new Error('motor (core) nao informado');
    }
    const port = (opts.port === undefined || opts.port === null) ? PORT_PADRAO : Number(opts.port);
    const clientId = opts.clientId || CLIENT_ID_PADRAO;
    const backoffMs = typeof opts.backoffMs === 'function' ? opts.backoffMs : backoffPadrao;
    const sair = typeof opts.sair === 'function' ? opts.sair : (codigo) => process.exit(codigo);
    const settleMs = Number.isFinite(opts.settleMs) ? opts.settleMs : (core.BATCH_SETTLE_MS_NORMAL || 0);
    const watchdogMs = Number.isFinite(opts.watchdogMs) ? opts.watchdogMs : WATCHDOG_MS_PADRAO;
    const watchdogTimeoutMs = Number.isFinite(opts.watchdogTimeoutMs) ? opts.watchdogTimeoutMs : WATCHDOG_TIMEOUT_MS_PADRAO;
    const maxNotReadyMs = Number.isFinite(opts.maxNotReadyMs) && opts.maxNotReadyMs > 0 ? opts.maxNotReadyMs : MAX_NOT_READY_MS_PADRAO;
    const destruirPrazoMs = Number.isFinite(opts.destruirPrazoMs) && opts.destruirPrazoMs > 0 ? opts.destruirPrazoMs : DESTRUIR_PRAZO_MS_PADRAO;

    let state = 'starting';
    let readySince = null;
    let client = null;
    let tentativaReconexao = 0;
    let retryTimer = null;
    let settleTimer = null;
    let watchdogTimer = null;
    let tetoTimer = null;
    let foraDeReadyDesde = null;
    let vigiaPendente = false;
    let parado = false;
    let encerrando = false;
    let pendentes = 0;
    let fila = Promise.resolve();

    function logar(nivel, mensagem) {
        if (typeof core.writeLog === 'function') {
            core.writeLog(nivel, mensagem);
        }
    }

    function limparSettle() {
        if (settleTimer) { clearTimeout(settleTimer); settleTimer = null; }
    }

    function limparTimers() {
        if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
        limparSettle();
        if (watchdogTimer) { clearInterval(watchdogTimer); watchdogTimer = null; }
        limparTeto();
    }

    // Teto sem 'ready': so arma se ainda nao esta armado, assim o tempo conta desde o ultimo momento fora de 'ready'.
    function armarTeto() {
        if (tetoTimer || parado) { return; }
        foraDeReadyDesde = Date.now();
        tetoTimer = setTimeout(() => {
            tetoTimer = null;
            const segundos = Math.round((Date.now() - foraDeReadyDesde) / 1000);
            encerrarPor(EXIT_TETO_SEM_READY, `[DAEMON] daemon sem ready ha ${segundos} s; encerrando para os envios voltarem ao modo por processo.`);
        }, maxNotReadyMs);
        tetoTimer.unref();
    }

    function limparTeto() {
        if (tetoTimer) { clearTimeout(tetoTimer); tetoTimer = null; }
        foraDeReadyDesde = null;
    }

    function fecharServidor() {
        return new Promise((resolve) => {
            if (!server.listening) { resolve(); return; }
            server.close(() => resolve());
            if (typeof server.closeAllConnections === 'function') { server.closeAllConnections(); }
        });
    }

    // Destroi o cliente com prazo: estourado o prazo ou com falha, segue para sair mesmo assim.
    async function destruirComPrazo(cliente) {
        try {
            await comPrazo(() => core.destruirClienteSilenciosamente(cliente), destruirPrazoMs);
        } catch (err) {
            logar('WARN', `[DAEMON] Cliente nao destruido com seguranca (${err && err.message ? err.message : err}); encerrando mesmo assim.`);
        }
    }

    // Encerramento por codigo (teto sem ready, QR, sessao ausente): destroi o cliente, fecha o servidor
    // e so entao sai, para nao deixar Chromium orfao segurando o perfil.
    async function encerrarPor(codigo, motivo) {
        if (encerrando) { return; }
        encerrando = true;
        logar('ERROR', motivo);
        parado = true;
        limparTimers();
        const cliente = client;
        client = null;
        state = 'stopped';
        if (cliente) { await destruirComPrazo(cliente); }
        await fecharServidor();
        sair(codigo);
    }

    function agendarReconexao() {
        if (parado) { return; }
        const atraso = backoffMs(tentativaReconexao);
        tentativaReconexao++;
        logar('WARN', `[DAEMON] Nova tentativa de inicializacao em ${atraso / 1000}s.`);
        retryTimer = setTimeout(() => {
            retryTimer = null;
            iniciarCliente();
        }, atraso);
    }

    function reconectar(cliente, motivo) {
        if (parado || cliente !== client) { return; }
        if (state === 'reconnecting') { return; }
        state = 'reconnecting';
        limparSettle();
        readySince = null;
        armarTeto();
        logar('WARN', `[DAEMON] Sessao interrompida (${motivo}). Reconectando.`);
        client = null;
        Promise.resolve(core.destruirClienteSilenciosamente(cliente))
            .catch(() => {})
            .then(() => agendarReconexao());
    }

    async function iniciarCliente() {
        if (parado) { return; }
        if (core.sessaoPersistidaAusente(clientId)) {
            await encerrarPor(EXIT_SESSAO_AUSENTE, `[DAEMON] Sessao do WhatsApp ausente no perfil '${clientId}'. Reautentique antes de iniciar o daemon.`);
            return;
        }
        state = 'starting';
        let cliente;
        try {
            cliente = core.criarCliente();
        } catch (err) {
            logar('ERROR', `[DAEMON] Falha ao criar cliente: ${err && err.message ? err.message : err}`);
            state = 'reconnecting';
            agendarReconexao();
            return;
        }
        client = cliente;

        cliente.on('ready', () => {
            if (cliente !== client || parado) { return; }
            // Acomodacao: o WhatsApp Web precisa de alguns segundos para aceitar envios de midia.
            // So vira 'ready' (aceita lotes) depois do settle; queda antes disso cancela o timer.
            state = 'warming';
            limparSettle();
            logar('INFO', `[DAEMON] Cliente pronto — estabilizando sessao '${clientId}' (${settleMs / 1000}s).`);
            settleTimer = setTimeout(() => {
                settleTimer = null;
                if (cliente !== client || parado || state !== 'warming') { return; }
                state = 'ready';
                readySince = new Date().toISOString();
                tentativaReconexao = 0;
                limparTeto();
                logar('INFO', `[DAEMON] Sessao '${clientId}' estabilizada e ativa.`);
            }, settleMs);
        });
        cliente.on('qr', () => {
            if (cliente !== client) { return; }
            encerrarPor(EXIT_SESSAO_AUSENTE, '[DAEMON] QR Code solicitado: reautenticacao necessaria. Encerrando com exit 21.');
        });
        cliente.on('disconnected', (motivo) => reconectar(cliente, `disconnected: ${motivo || 'sem motivo'}`));
        cliente.on('auth_failure', (msg) => reconectar(cliente, `auth_failure: ${msg || 'sem detalhe'}`));

        try {
            await cliente.initialize();
        } catch (err) {
            reconectar(cliente, `initialize: ${err && err.message ? err.message : err}`);
        }
    }

    function estado() {
        return {
            state,
            client_id: clientId,
            ready_since: readySince,
            fila: { pendentes }
        };
    }

    async function executarLote(corpo, cliente) {
        const items = corpo.items;
        const chatId = normalizarChatId(corpo.chat_id.trim());
        const batchState = { dispatchIniciado: false, resultados: [] };
        try {
            const results = await core.executarFluxoBatch(cliente, items, chatId, 1, batchState);
            const lista = Array.isArray(results) ? results : batchState.resultados;
            return { status: 200, corpo: { results: lista } };
        } catch (err) {
            const mensagem = err && err.message ? err.message : String(err);
            logar('ERROR', `[DAEMON] Falha no lote ${corpo.exec_id}: ${mensagem}`);
            const results = core.completarResultadosAbortados(items, batchState.resultados, 'DAEMON_ERROR');
            return { status: 500, corpo: { error: mensagem, results } };
        }
    }

    // Envio unico (POST /send): mesma assinatura de lote na fila; devolve { status, corpo }.
    async function executarEnvio(envio, cliente) {
        try {
            await core.executarEnvioUnico(cliente, { contato: envio.chat_id, anexo: envio.anexo, legenda: envio.caption });
            return { status: 200, corpo: { ok: true } };
        } catch (err) {
            const mensagem = err && err.message ? err.message : String(err);
            logar('ERROR', `[DAEMON] Falha no envio ${envio.exec_id}: ${mensagem}`);
            return { status: 500, corpo: { error: mensagem } };
        }
    }

    function enfileirarLote(corpo) {
        return enfileirarTarefa((cliente) => executarLote(corpo, cliente));
    }

    function enfileirarEnvio(envio) {
        return enfileirarTarefa((cliente) => executarEnvio(envio, cliente));
    }

    // Fila serial comum a lotes e envios unicos: uma tarefa por vez, sempre com a conferencia
    // de CONNECTED antes. tarefaFn(cliente) devolve { status, corpo }.
    function enfileirarTarefa(tarefaFn) {
        pendentes++;
        const tarefa = fila.then(async () => {
            if (state !== 'ready' || !client) {
                return { status: 503, corpo: { error: 'not_ready' } };
            }
            // Conferencia de conexao antes de cada tarefa: nada e' despachado se o WhatsApp
            // nao confirmar CONNECTED (pode levar ate 30 s no core).
            const cliente = client;
            let conectado = false;
            try {
                conectado = (await core.verificarEstadoConectado(cliente, 'DAEMON')) === true;
            } catch (_) {
                conectado = false;
            }
            if (!conectado) {
                reconectar(cliente, 'confirmacao de conexao antes da tarefa sem CONNECTED');
                return { status: 503, corpo: { error: 'not_connected' } };
            }
            // Durante a conferencia o cliente pode ter caido ou sido trocado.
            if (state !== 'ready' || cliente !== client) {
                return { status: 503, corpo: { error: 'not_ready' } };
            }
            return tarefaFn(cliente);
        });
        fila = tarefa.catch(() => {});
        return tarefa.finally(() => { pendentes--; });
    }

    // Vigia periodico: enfileirado na mesma fila dos lotes, portanto nunca roda durante um
    // lote. Nao agenda se ja ha lote pendente/em execucao (pendentes > 0) nem se nao esta 'ready'.
    function agendarVigia() {
        if (vigiaPendente || parado || pendentes > 0 || state !== 'ready' || !client) { return; }
        vigiaPendente = true;
        fila = fila.then(async () => {
            try {
                if (parado || state !== 'ready' || !client) { return; }
                const cliente = client;
                let estado = null;
                try {
                    estado = await comPrazo(() => cliente.getState(), watchdogTimeoutMs);
                } catch (_) {
                    estado = null;
                }
                if (estado === 'CONNECTED') { return; }
                reconectar(cliente, `vigia: getState=${estado || 'falha ou prazo estourado'}`);
            } finally {
                vigiaPendente = false;
            }
        }).catch(() => {});
    }

    function lerCorpo(req) {
        return new Promise((resolve) => {
            const pedacos = [];
            let tamanho = 0;
            let excedeu = false;
            req.on('data', (pedaco) => {
                if (excedeu) { return; }
                tamanho += pedaco.length;
                if (tamanho > MAX_BODY_BYTES) {
                    excedeu = true;
                    resolve({ erro: 413 });
                    return;
                }
                pedacos.push(pedaco);
            });
            req.on('end', () => {
                if (excedeu) { return; }
                resolve({ texto: Buffer.concat(pedacos).toString('utf8') });
            });
            req.on('error', () => {
                if (!excedeu) { resolve({ erro: 400 }); }
            });
        });
    }

    // Le e valida o corpo JSON de uma rota POST. Devolve { resposta } quando a requisicao ja
    // deve ser respondida com erro (413, 400) ou { corpo } quando o corpo e' valido.
    async function lerCorpoRequisicao(req, validar) {
        const lido = await lerCorpo(req);
        if (lido.erro === 413) {
            return { resposta: { status: 413, corpo: { error: 'payload_too_large' }, cabecalhos: { Connection: 'close' } } };
        }
        if (lido.erro) {
            return { resposta: { status: lido.erro, corpo: { error: 'bad_request' } } };
        }
        let corpo;
        try {
            corpo = JSON.parse(lido.texto);
        } catch (_) {
            return { resposta: { status: 400, corpo: { error: 'invalid_json' } } };
        }
        const invalido = validar(corpo);
        if (invalido) {
            return { resposta: { status: 400, corpo: { error: 'invalid_body', detail: invalido } } };
        }
        return { corpo };
    }

    // client_id do corpo tem de ser o perfil deste daemon; outro perfil nao e' atendido (409).
    // Comparacao sem diferenciar maiusculas e minusculas: no Windows a pasta do perfil nao diferencia caixa.
    function perfilDivergente(corpo) {
        return corpo.client_id.toLowerCase() !== String(clientId).toLowerCase();
    }

    async function tratarBatch(req, res) {
        const lido = await lerCorpoRequisicao(req, validarCorpoBatch);
        if (lido.resposta) {
            responderJson(res, lido.resposta.status, lido.resposta.corpo, lido.resposta.cabecalhos);
            return;
        }
        if (perfilDivergente(lido.corpo)) {
            responderJson(res, 409, { error: 'client_mismatch' });
            return;
        }
        const resposta = await enfileirarLote(lido.corpo);
        responderJson(res, resposta.status, resposta.corpo);
    }

    async function tratarEnvio(req, res) {
        const lido = await lerCorpoRequisicao(req, (corpo) => {
            const invalido = validarCorpoEnvio(corpo);
            if (invalido) { return invalido; }
            return anexoInexistente(corpo) ? 'attachment_path inexistente' : null;
        });
        if (lido.resposta) {
            responderJson(res, lido.resposta.status, lido.resposta.corpo, lido.resposta.cabecalhos);
            return;
        }
        if (perfilDivergente(lido.corpo)) {
            responderJson(res, 409, { error: 'client_mismatch' });
            return;
        }
        const envio = {
            exec_id: lido.corpo.exec_id,
            chat_id: lido.corpo.chat_id.trim(),
            caption: lido.corpo.caption,
            anexo: lido.corpo.attachment_path ? path.resolve(lido.corpo.attachment_path) : null
        };
        const resposta = await enfileirarEnvio(envio);
        responderJson(res, resposta.status, resposta.corpo);
    }

    const server = http.createServer((req, res) => {
        const recebido = req.headers[CABECALHO_AUTENTICACAO];
        if (!tokenConfere(recebido, token)) {
            responderJson(res, 401, { error: 'unauthorized' });
            req.resume();
            return;
        }
        const caminho = (req.url || '').split('?')[0];
        if (req.method === 'GET' && caminho === '/health') {
            responderJson(res, 200, estado());
            return;
        }
        if (req.method === 'POST' && caminho === '/batch') {
            tratarBatch(req, res).catch(() => {
                if (!res.headersSent) { responderJson(res, 500, { error: 'internal_error' }); }
            });
            return;
        }
        if (req.method === 'POST' && caminho === '/send') {
            tratarEnvio(req, res).catch(() => {
                if (!res.headersSent) { responderJson(res, 500, { error: 'internal_error' }); }
            });
            return;
        }
        responderJson(res, 404, { error: 'not_found' });
        req.resume();
    });

    async function start() {
        await new Promise((resolve, reject) => {
            server.once('error', reject);
            server.listen(port, '127.0.0.1', () => {
                server.removeListener('error', reject);
                resolve();
            });
        });
        logar('INFO', `[DAEMON] Escutando em 127.0.0.1:${port} (client_id '${clientId}').`);
        watchdogTimer = setInterval(agendarVigia, watchdogMs);
        watchdogTimer.unref();
        armarTeto();
        await iniciarCliente();
    }

    async function stop() {
        parado = true;
        limparTimers();
        const cliente = client;
        client = null;
        state = 'stopped';
        if (cliente) { await destruirComPrazo(cliente); }
        await fecharServidor();
    }

    return { server, start, stop, estado };
}

function main() {
    const token = process.env.WHATSAPP_DAEMON_TOKEN || '';
    const port = Number(process.env.WHATSAPP_DAEMON_PORT || PORT_PADRAO);
    const clientId = process.env.WHATSAPP_DAEMON_CLIENT_ID || CLIENT_ID_PADRAO;
    const logFile = process.env.WHATSAPP_DAEMON_LOG
        || path.join(__dirname, '..', 'Logs', 'WhatsApp_Daemon.log');

    if (!tokenValido(token)) {
        console.error(`[DAEMON] WHATSAPP_DAEMON_TOKEN ausente ou com menos de ${TOKEN_MIN_LENGTH} caracteres. Daemon nao iniciado.`);
        process.exit(1);
    }

    // WhatsApp-Core.js le EXEC_ID/MODE/CLIENT_ID/LOG_FILE de process.argv na carga do modulo.
    process.argv = [process.argv[0], __filename, 'daemon', 'BATCH', clientId, '', '', '', logFile];
    const core = require('./WhatsApp-Core.js');

    let daemon;
    try {
        const maxNotReadyMs = lerMaxNotReadyMs(process.env.WHATSAPP_DAEMON_MAX_NOT_READY_MS);
        daemon = criarDaemon({ token, port, clientId, core, maxNotReadyMs });
    } catch (err) {
        core.writeLog('ERROR', `[DAEMON] ${err.message}`);
        process.exit(1);
    }

    const encerrar = () => {
        daemon.stop().then(() => process.exit(0), () => process.exit(1));
    };
    process.on('SIGINT', encerrar);
    process.on('SIGTERM', encerrar);

    daemon.start().catch((err) => {
        core.writeLog('ERROR', `[DAEMON] Falha ao iniciar: ${err && err.message ? err.message : err}`);
        process.exit(1);
    });
}

if (require.main === module) {
    main();
}

module.exports = {
    criarDaemon,
    validarCorpoBatch,
    validarCorpoEnvio,
    normalizarChatId,
    tokenConfere,
    backoffPadrao,
    lerMaxNotReadyMs,
    BACKOFF_MS,
    TOKEN_MIN_LENGTH,
    MAX_BODY_BYTES,
    MAX_NOT_READY_MS_PADRAO
};
