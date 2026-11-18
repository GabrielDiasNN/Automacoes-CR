// Testes do daemon persistente do WhatsApp (lib/whatsapp-daemon.js).
// Sem Chromium real: o motor (core) e' um dublê injetado em criarDaemon. Cada teste sobe
// o servidor em 127.0.0.1 com porta efemera (port: 0) e o encerra ao final.
'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');
const { EventEmitter } = require('events');

const daemonModule = require('../whatsapp-daemon.js');
const { criarDaemon, validarCorpoBatch, normalizarChatId, tokenConfere, backoffPadrao, lerMaxNotReadyMs, BACKOFF_MS, MAX_NOT_READY_MS_PADRAO } = daemonModule;

const valorFicticio = (n, caractere = 'w') => caractere.repeat(n);
const TOKEN = valorFicticio(40, 'x');
const LOTE_VALIDO = {
    exec_id: 'exec-1',
    client_id: 'teste-cliente',
    chat_id: '5511999999999',
    items: [{ phase_key: 'page_01', image_path: 'card.png', caption: 'Pagina 1' }]
};

class FakeClient extends EventEmitter {
    constructor(comportamento, indice, estadoFn) {
        super();
        this.comportamento = comportamento;
        this.destruido = false;
        this.indice = indice;
        this.estadoFn = estadoFn;
        this.getStateChamadas = 0;
    }
    async initialize() {
        if (this.comportamento.initializeErro) { throw new Error(this.comportamento.initializeErro); }
        if (this.comportamento.autoReady !== false) {
            setImmediate(() => this.emit('ready'));
        }
    }
    getState() {
        this.getStateChamadas++;
        return this.estadoFn(this.indice);
    }
}

function criarCore(opcoes = {}) {
    const chamadas = { criarCliente: 0, destruir: [], executar: [], envios: [], sessaoChecada: [], conferencias: [] };
    const clientes = [];
    const estadoFn = opcoes.estadoCliente || (() => 'CONNECTED');
    const conectado = opcoes.conectado || (() => true);
    const core = {
        chamadas,
        clientes,
        writeLog() {},
        sessaoPersistidaAusente(clientId) {
            chamadas.sessaoChecada.push(clientId);
            return opcoes.sessaoAusente === true;
        },
        criarCliente() {
            chamadas.criarCliente++;
            const c = new FakeClient(opcoes.cliente || {}, clientes.length, estadoFn);
            clientes.push(c);
            return c;
        },
        async destruirClienteSilenciosamente(cliente) {
            chamadas.destruir.push(cliente);
            cliente.destruido = true;
        },
        async verificarEstadoConectado(client, contexto) {
            chamadas.conferencias.push({ client, contexto });
            return conectado(chamadas.conferencias.length);
        },
        async executarEnvioUnico(client, envio) {
            chamadas.envios.push({ client, envio });
            if (opcoes.envio) { return opcoes.envio(envio); }
            return undefined;
        },
        async executarFluxoBatch(client, items, chatId, tentativa, batchState) {
            chamadas.executar.push({ client, items, chatId, tentativa });
            if (opcoes.executar) { return opcoes.executar(items, batchState); }
            const resultados = items.map((i) => ({ phase_key: i.phase_key, success: true, error: null }));
            batchState.resultados.push(...resultados);
            return resultados;
        },
        completarResultadosAbortados(itens, parciais, motivo) {
            const mapa = new Map((parciais || []).map((r) => [r.phase_key, r]));
            return itens.map((i) => mapa.get(i.phase_key) || { phase_key: i.phase_key, success: false, error: motivo });
        }
    };
    return core;
}

function requisitar(base, { metodo = 'GET', caminho = '/health', token = TOKEN, corpo = null, cabecalhos = {} } = {}) {
    return new Promise((resolve, reject) => {
        const url = new URL(caminho, base);
        const dados = corpo === null ? null : (typeof corpo === 'string' ? corpo : JSON.stringify(corpo));
        const headers = { ...cabecalhos };
        if (token !== null) { headers['x-hub-daemon-token'] = token; }
        if (dados !== null) {
            headers['Content-Type'] = 'application/json';
            headers['Content-Length'] = Buffer.byteLength(dados, 'utf8');
        }
        const req = http.request(url, { method: metodo, headers }, (res) => {
            const pedacos = [];
            res.on('data', (p) => pedacos.push(p));
            res.on('end', () => {
                const texto = Buffer.concat(pedacos).toString('utf8');
                let json = null;
                try { json = JSON.parse(texto); } catch (_) { json = texto; }
                resolve({ status: res.statusCode, corpo: json });
            });
        });
        req.on('error', reject);
        if (dados !== null) { req.write(dados); }
        req.end();
    });
}

async function subir(opcoes = {}) {
    const core = opcoes.core || criarCore(opcoes.coreOpcoes);
    const daemon = criarDaemon({
        token: opcoes.token === undefined ? TOKEN : opcoes.token,
        port: 0,
        clientId: 'teste-cliente',
        core,
        backoffMs: opcoes.backoffMs || (() => 10),
        sair: opcoes.sair || (() => {}),
        settleMs: opcoes.settleMs === undefined ? 0 : opcoes.settleMs,
        watchdogMs: opcoes.watchdogMs,
        watchdogTimeoutMs: opcoes.watchdogTimeoutMs,
        maxNotReadyMs: opcoes.maxNotReadyMs,
        destruirPrazoMs: opcoes.destruirPrazoMs
    });
    // A porta e' lida no evento 'listening': um encerramento durante o start (ex.: sessao ausente)
    // fecha o servidor antes de start() resolver.
    let porta = null;
    daemon.server.once('listening', () => { porta = daemon.server.address().port; });
    await daemon.start();
    const base = `http://127.0.0.1:${porta}`;
    if (opcoes.esperarReady !== false) {
        await esperarEstado(daemon, 'ready');
    }
    return { daemon, core, base };
}

async function esperarEstado(daemon, estadoEsperado, limiteMs = 2000) {
    const inicio = Date.now();
    while (daemon.estado().state !== estadoEsperado) {
        if (Date.now() - inicio > limiteMs) {
            assert.fail(`estado nao chegou a '${estadoEsperado}' (atual: ${daemon.estado().state})`);
        }
        await new Promise((r) => setTimeout(r, 5));
    }
}

async function esperarCondicao(condicao, limiteMs = 2000) {
    const inicio = Date.now();
    while (!condicao()) {
        if (Date.now() - inicio > limiteMs) {
            assert.fail('condicao nao atingida no prazo');
        }
        await new Promise((r) => setTimeout(r, 5));
    }
}

async function encerrar(ctx) {
    await ctx.daemon.stop();
}

test('recusa subir sem token e com token curto (nao abre porta)', () => {
    const core = criarCore();
    assert.throws(() => criarDaemon({ token: undefined, core }), /WHATSAPP_DAEMON_TOKEN/);
    assert.throws(() => criarDaemon({ token: '', core }), /WHATSAPP_DAEMON_TOKEN/);
    assert.throws(() => criarDaemon({ token: valorFicticio(5), core }), /menos de 32/);
    assert.throws(() => criarDaemon({ token: valorFicticio(31, 'y'), core }), /menos de 32/);
    assert.equal(core.chamadas.criarCliente, 0);
});

test('aceita token com exatamente 32 caracteres', () => {
    const d = criarDaemon({ token: valorFicticio(32, 'z'), core: criarCore() });
    assert.equal(typeof d.start, 'function');
    assert.equal(d.server.listening, false);
});

test('escuta somente em 127.0.0.1 (nunca em todas as interfaces)', async () => {
    const ctx = await subir();
    try {
        const endereco = ctx.daemon.server.address();
        assert.equal(endereco.address, '127.0.0.1');
        assert.equal(endereco.family, 'IPv4');
    } finally { await encerrar(ctx); }
});

test('401 sem header de token', async () => {
    const ctx = await subir();
    try {
        const r = await requisitar(ctx.base, { token: null });
        assert.equal(r.status, 401);
        assert.deepEqual(r.corpo, { error: 'unauthorized' });
    } finally { await encerrar(ctx); }
});

test('401 com token errado (mesmo tamanho e tamanho diferente)', async () => {
    const ctx = await subir();
    try {
        const mesmoTamanho = await requisitar(ctx.base, { token: valorFicticio(40) });
        assert.equal(mesmoTamanho.status, 401);
        const outroTamanho = await requisitar(ctx.base, { token: valorFicticio(10) });
        assert.equal(outroTamanho.status, 401);
    } finally { await encerrar(ctx); }
});

test('tokenConfere recusa tipos e tamanhos diferentes sem lancar', () => {
    assert.equal(tokenConfere(undefined, TOKEN), false);
    assert.equal(tokenConfere(['x'], TOKEN), false);
    assert.equal(tokenConfere('curto', TOKEN), false);
    assert.equal(tokenConfere(TOKEN, TOKEN), true);
});

test('GET /health devolve estado, client_id, ready_since e fila', async () => {
    const ctx = await subir();
    try {
        const r = await requisitar(ctx.base, { caminho: '/health' });
        assert.equal(r.status, 200);
        assert.equal(r.corpo.state, 'ready');
        assert.equal(r.corpo.client_id, 'teste-cliente');
        assert.equal(typeof r.corpo.ready_since, 'string');
        assert.deepEqual(r.corpo.fila, { pendentes: 0 });
    } finally { await encerrar(ctx); }
});

test('rota desconhecida com token valido devolve 404', async () => {
    const ctx = await subir();
    try {
        const r = await requisitar(ctx.base, { caminho: '/nada' });
        assert.equal(r.status, 404);
    } finally { await encerrar(ctx); }
});

test('POST /batch responde 503 not_ready enquanto o cliente nao esta pronto', async () => {
    const ctx = await subir({ esperarReady: false, coreOpcoes: { cliente: { autoReady: false } } });
    try {
        const r = await requisitar(ctx.base, { metodo: 'POST', caminho: '/batch', corpo: LOTE_VALIDO });
        assert.equal(r.status, 503);
        assert.deepEqual(r.corpo, { error: 'not_ready' });
        assert.equal(ctx.core.chamadas.executar.length, 0);
    } finally { await encerrar(ctx); }
});

test('POST /batch feliz devolve results do core e normaliza chat_id', async () => {
    const ctx = await subir();
    try {
        const r = await requisitar(ctx.base, { metodo: 'POST', caminho: '/batch', corpo: LOTE_VALIDO });
        assert.equal(r.status, 200);
        assert.deepEqual(r.corpo, { results: [{ phase_key: 'page_01', success: true, error: null }] });
        assert.equal(ctx.core.chamadas.executar.length, 1);
        const chamada = ctx.core.chamadas.executar[0];
        assert.equal(chamada.chatId, '5511999999999@c.us');
        assert.equal(chamada.tentativa, 1);
        assert.equal(chamada.client, ctx.core.clientes[0]);
    } finally { await encerrar(ctx); }
});

test('POST /batch com corpo invalido devolve 400', async () => {
    const ctx = await subir();
    try {
        const json = await requisitar(ctx.base, { metodo: 'POST', caminho: '/batch', corpo: '{nao-json' });
        assert.equal(json.status, 400);
        assert.equal(json.corpo.error, 'invalid_json');

        const semItems = await requisitar(ctx.base, {
            metodo: 'POST', caminho: '/batch', corpo: { exec_id: 'e', chat_id: '5511', items: [] }
        });
        assert.equal(semItems.status, 400);
        assert.equal(semItems.corpo.error, 'invalid_body');

        const semPhase = await requisitar(ctx.base, {
            metodo: 'POST', caminho: '/batch',
            corpo: { exec_id: 'e', chat_id: '5511', items: [{ image_path: 'a.png', caption: '' }] }
        });
        assert.equal(semPhase.status, 400);
    } finally { await encerrar(ctx); }
});

const ENVIO_VALIDO = {
    exec_id: 'exec-envio-1',
    client_id: 'teste-cliente',
    chat_id: '5511999999999',
    caption: 'Mensagem de teste',
    attachment_path: null
};

test('POST /send feliz responde 200 {ok:true} e chama executarEnvioUnico com contato, anexo e legenda', async () => {
    const ctx = await subir();
    try {
        const r = await requisitar(ctx.base, { metodo: 'POST', caminho: '/send', corpo: ENVIO_VALIDO });
        assert.equal(r.status, 200);
        assert.deepEqual(r.corpo, { ok: true });
        assert.equal(ctx.core.chamadas.envios.length, 1);
        assert.equal(ctx.core.chamadas.envios[0].client, ctx.core.clientes[0]);
        assert.deepEqual(ctx.core.chamadas.envios[0].envio, { contato: '5511999999999', anexo: null, legenda: 'Mensagem de teste' });
    } finally { await encerrar(ctx); }
});

test('POST /send com anexo existente encaminha o caminho resolvido', async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'daemon-send-'));
    const arquivo = path.join(dir, 'relatorio.xlsx');
    fs.writeFileSync(arquivo, 'conteudo');
    const ctx = await subir();
    try {
        const r = await requisitar(ctx.base, { metodo: 'POST', caminho: '/send', corpo: { ...ENVIO_VALIDO, attachment_path: arquivo } });
        assert.equal(r.status, 200);
        assert.equal(ctx.core.chamadas.envios[0].envio.anexo, path.resolve(arquivo));
    } finally {
        await encerrar(ctx);
        fs.rmSync(dir, { recursive: true, force: true });
    }
});

test('POST /send com anexo inexistente devolve 400 e nao toca na fila', async () => {
    const ctx = await subir();
    try {
        const caminho = path.join(os.tmpdir(), 'daemon-send-nao-existe', 'x.xlsx');
        const r = await requisitar(ctx.base, { metodo: 'POST', caminho: '/send', corpo: { ...ENVIO_VALIDO, attachment_path: caminho } });
        assert.equal(r.status, 400);
        assert.equal(r.corpo.error, 'invalid_body');
        assert.match(r.corpo.detail, /attachment_path inexistente/);
        assert.equal(ctx.core.chamadas.envios.length, 0);
    } finally { await encerrar(ctx); }
});

test('POST /send com corpo invalido devolve 400', async () => {
    const ctx = await subir();
    try {
        const json = await requisitar(ctx.base, { metodo: 'POST', caminho: '/send', corpo: '{nao-json' });
        assert.equal(json.status, 400);
        assert.equal(json.corpo.error, 'invalid_json');

        const semLegenda = await requisitar(ctx.base, { metodo: 'POST', caminho: '/send', corpo: { ...ENVIO_VALIDO, caption: '   ' } });
        assert.equal(semLegenda.status, 400);
        assert.match(semLegenda.corpo.detail, /caption/);

        const semPerfil = await requisitar(ctx.base, { metodo: 'POST', caminho: '/send', corpo: { ...ENVIO_VALIDO, client_id: undefined } });
        assert.equal(semPerfil.status, 400);
        assert.match(semPerfil.corpo.detail, /client_id/);

        const anexoInvalido = await requisitar(ctx.base, { metodo: 'POST', caminho: '/send', corpo: { ...ENVIO_VALIDO, attachment_path: 42 } });
        assert.equal(anexoInvalido.status, 400);
        assert.match(anexoInvalido.corpo.detail, /attachment_path/);
        assert.equal(ctx.core.chamadas.envios.length, 0);
    } finally { await encerrar(ctx); }
});

test('POST /send e POST /batch com client_id de outro perfil devolvem 409 client_mismatch', async () => {
    const ctx = await subir();
    try {
        const envio = await requisitar(ctx.base, { metodo: 'POST', caminho: '/send', corpo: { ...ENVIO_VALIDO, client_id: 'outro-perfil' } });
        assert.equal(envio.status, 409);
        assert.deepEqual(envio.corpo, { error: 'client_mismatch' });

        const lote = await requisitar(ctx.base, { metodo: 'POST', caminho: '/batch', corpo: { ...LOTE_VALIDO, client_id: 'outro-perfil' } });
        assert.equal(lote.status, 409);
        assert.deepEqual(lote.corpo, { error: 'client_mismatch' });

        assert.equal(ctx.core.chamadas.envios.length, 0);
        assert.equal(ctx.core.chamadas.executar.length, 0);
    } finally { await encerrar(ctx); }
});

test('POST /batch sem client_id devolve 400 (contrato exige o perfil)', async () => {
    const ctx = await subir();
    try {
        const { client_id: _ignorado, ...semPerfil } = LOTE_VALIDO;
        const r = await requisitar(ctx.base, { metodo: 'POST', caminho: '/batch', corpo: semPerfil });
        assert.equal(r.status, 400);
        assert.equal(r.corpo.error, 'invalid_body');
        assert.match(r.corpo.detail, /client_id/);
    } finally { await encerrar(ctx); }
});

test('POST /send antes de ready devolve 503 not_ready e nao envia', async () => {
    const ctx = await subir({ esperarReady: false, coreOpcoes: { cliente: { autoReady: false } } });
    try {
        const r = await requisitar(ctx.base, { metodo: 'POST', caminho: '/send', corpo: ENVIO_VALIDO });
        assert.equal(r.status, 503);
        assert.deepEqual(r.corpo, { error: 'not_ready' });
        assert.equal(ctx.core.chamadas.envios.length, 0);
    } finally { await encerrar(ctx); }
});

test('POST /send sem CONNECTED confirmado devolve 503 not_connected e nao envia', async () => {
    const ctx = await subir({ coreOpcoes: { conectado: () => false } });
    try {
        const r = await requisitar(ctx.base, { metodo: 'POST', caminho: '/send', corpo: ENVIO_VALIDO });
        assert.equal(r.status, 503);
        assert.deepEqual(r.corpo, { error: 'not_connected' });
        assert.equal(ctx.core.chamadas.envios.length, 0);
    } finally { await encerrar(ctx); }
});

test('POST /send com falha no core devolve 500 com a mensagem do erro', async () => {
    const ctx = await subir({ coreOpcoes: { envio: () => { throw new Error('falha simulada no envio'); } } });
    try {
        const r = await requisitar(ctx.base, { metodo: 'POST', caminho: '/send', corpo: ENVIO_VALIDO });
        assert.equal(r.status, 500);
        assert.deepEqual(r.corpo, { error: 'falha simulada no envio' });
    } finally { await encerrar(ctx); }
});

test('validarCorpoBatch e normalizarChatId cobrem as regras de contrato', () => {
    assert.equal(validarCorpoBatch(null), 'corpo deve ser um objeto JSON');
    assert.equal(validarCorpoBatch([]), 'corpo deve ser um objeto JSON');
    assert.match(validarCorpoBatch({ exec_id: '', chat_id: '1', items: [1] }), /exec_id/);
    assert.match(validarCorpoBatch({ exec_id: 'e', chat_id: ' ', items: [1] }), /chat_id/);
    assert.match(validarCorpoBatch({ exec_id: 'e', chat_id: '1', items: [null] }), /item invalido/);
    assert.match(validarCorpoBatch({ exec_id: 'e', chat_id: '1', items: [{ phase_key: 'p', image_path: 'a', caption: 3 }] }), /caption/);
    assert.equal(validarCorpoBatch(LOTE_VALIDO), null);
    assert.equal(normalizarChatId('5511 99999-9999'), '5511999999999@c.us');
    assert.equal(normalizarChatId('120363@g.us'), '120363@g.us');
});

test('dois POST /batch concorrentes executam em serie', async () => {
    let ativos = 0;
    let pico = 0;
    const core = criarCore({
        executar: async (items, batchState) => {
            ativos++;
            pico = Math.max(pico, ativos);
            await new Promise((r) => setTimeout(r, 40));
            ativos--;
            const resultados = items.map((i) => ({ phase_key: i.phase_key, success: true, error: null }));
            batchState.resultados.push(...resultados);
            return resultados;
        }
    });
    const ctx = await subir({ core });
    try {
        const [a, b] = await Promise.all([
            requisitar(ctx.base, { metodo: 'POST', caminho: '/batch', corpo: LOTE_VALIDO }),
            requisitar(ctx.base, { metodo: 'POST', caminho: '/batch', corpo: LOTE_VALIDO })
        ]);
        assert.equal(a.status, 200);
        assert.equal(b.status, 200);
        assert.equal(pico, 1, 'lotes nao podem se sobrepor');
        assert.equal(core.chamadas.executar.length, 2);
    } finally { await encerrar(ctx); }
});

test('erro no fluxo devolve 500 com results completados como DAEMON_ERROR', async () => {
    const itensDoLote = [
        { phase_key: 'page_01', image_path: 'a.png', caption: '' },
        { phase_key: 'page_02', image_path: 'b.png', caption: '' }
    ];
    const core = criarCore({
        executar: async (items, batchState) => {
            batchState.resultados.push({ phase_key: 'page_01', success: true, error: null });
            throw new Error('boom controlado');
        }
    });
    const ctx = await subir({ core });
    try {
        const r = await requisitar(ctx.base, {
            metodo: 'POST', caminho: '/batch', corpo: { exec_id: 'e', client_id: 'teste-cliente', chat_id: '5511999999999', items: itensDoLote }
        });
        assert.equal(r.status, 500);
        assert.equal(r.corpo.error, 'boom controlado');
        assert.deepEqual(r.corpo.results, [
            { phase_key: 'page_01', success: true, error: null },
            { phase_key: 'page_02', success: false, error: 'DAEMON_ERROR' }
        ]);
    } finally { await encerrar(ctx); }
});

test('corpo acima de 1 MB devolve 413', async () => {
    const ctx = await subir();
    try {
        const grande = JSON.stringify({ exec_id: 'e', chat_id: '5511', items: [{ phase_key: 'p', image_path: 'a', caption: 'x'.repeat(1024 * 1024 + 10) }] });
        const r = await requisitar(ctx.base, { metodo: 'POST', caminho: '/batch', corpo: grande }).catch((e) => ({ status: 'erro-de-socket', detalhe: e.code }));
        assert.ok(r.status === 413 || r.status === 'erro-de-socket', `status inesperado: ${r.status}`);
        if (r.status === 413) {
            assert.deepEqual(r.corpo, { error: 'payload_too_large' });
        }
        assert.equal(ctx.core.chamadas.executar.length, 0);
    } finally { await encerrar(ctx); }
});

test('sessao ausente no perfil encerra com exit 21 antes de criar cliente', async () => {
    const codigos = [];
    const ctx = await subir({
        coreOpcoes: { sessaoAusente: true },
        esperarReady: false,
        sair: (codigo) => codigos.push(codigo)
    });
    try {
        await new Promise((r) => setTimeout(r, 20));
        assert.deepEqual(codigos, [21]);
        assert.equal(ctx.core.chamadas.criarCliente, 0);
        assert.deepEqual(ctx.core.chamadas.sessaoChecada, ['teste-cliente']);
    } finally { await encerrar(ctx); }
});

test('evento qr encerra com exit 21 (reautenticacao necessaria) depois de destruir o cliente', async () => {
    const core = criarCore({ cliente: { autoReady: false } });
    const saidas = [];
    const ctx = await subir({ core, esperarReady: false, sair: (c) => saidas.push({ c, destruidos: core.chamadas.destruir.length }) });
    try {
        await new Promise((r) => setTimeout(r, 5));
        core.clientes[0].emit('qr', 'codigo');
        await esperarCondicao(() => saidas.length === 1);
        assert.deepEqual(saidas.map((s) => s.c), [21]);
        assert.equal(saidas[0].destruidos, 1, 'cliente deve ser destruido antes de sair');
        assert.equal(core.chamadas.destruir[0], core.clientes[0]);
        assert.equal(ctx.daemon.server.listening, false);
    } finally { await encerrar(ctx); }
});

test('disconnected destroi o cliente, aguarda backoff e recria', async () => {
    const ctx = await subir({ backoffMs: () => 10 });
    try {
        ctx.core.clientes[0].emit('disconnected', 'NAVIGATION');
        await esperarEstado(ctx.daemon, 'ready');
        assert.equal(ctx.core.chamadas.destruir.length, 1);
        assert.equal(ctx.core.chamadas.destruir[0], ctx.core.clientes[0]);
        assert.equal(ctx.core.chamadas.criarCliente, 2);
        const r = await requisitar(ctx.base, { metodo: 'POST', caminho: '/batch', corpo: LOTE_VALIDO });
        assert.equal(r.status, 200);
        assert.equal(ctx.core.chamadas.executar[0].client, ctx.core.clientes[1]);
    } finally { await encerrar(ctx); }
});

test('falha de initialize entra em reconnecting e tenta de novo', async () => {
    let tentativas = 0;
    const core = criarCore();
    const criarOriginal = core.criarCliente;
    core.criarCliente = () => {
        tentativas++;
        const c = criarOriginal.call(core);
        if (tentativas === 1) { c.comportamento = { initializeErro: 'falha de rede' }; }
        return c;
    };
    const ctx = await subir({ core, esperarReady: false, backoffMs: () => 10 });
    try {
        await esperarEstado(ctx.daemon, 'ready');
        assert.equal(tentativas, 2);
        assert.equal(ctx.core.chamadas.destruir.length, 1);
    } finally { await encerrar(ctx); }
});

test('backoff padrao segue 30/60/120/300 s com teto', () => {
    assert.deepEqual(BACKOFF_MS, [30000, 60000, 120000, 300000]);
    assert.equal(backoffPadrao(0), 30000);
    assert.equal(backoffPadrao(1), 60000);
    assert.equal(backoffPadrao(2), 120000);
    assert.equal(backoffPadrao(3), 300000);
    assert.equal(backoffPadrao(9), 300000);
});

test('stop destroi o cliente e fecha o servidor', async () => {
    const ctx = await subir();
    const porta = ctx.daemon.server.address().port;
    await ctx.daemon.stop();
    assert.equal(ctx.core.chamadas.destruir.length, 1);
    assert.equal(ctx.daemon.server.listening, false);
    await assert.rejects(() => requisitar(`http://127.0.0.1:${porta}`, { caminho: '/health' }));
});

test('porta ocupada faz start rejeitar', async () => {
    const ctx = await subir();
    try {
        const outro = criarDaemon({ token: TOKEN, port: ctx.daemon.server.address().port, core: criarCore() });
        await assert.rejects(() => outro.start(), /EADDRINUSE/);
    } finally { await encerrar(ctx); }
});

test('ready passa por warming e so vira ready depois do settle', async () => {
    const SETTLE = 150;
    const ctx = await subir({ esperarReady: false, settleMs: SETTLE });
    try {
        await esperarEstado(ctx.daemon, 'warming');
        assert.equal(ctx.daemon.estado().state, 'warming');
        const inicio = Date.now();

        const saude = await requisitar(ctx.base, { caminho: '/health' });
        assert.equal(saude.corpo.state, 'warming');
        assert.equal(saude.corpo.ready_since, null);

        const lote = await requisitar(ctx.base, { metodo: 'POST', caminho: '/batch', corpo: LOTE_VALIDO });
        assert.equal(lote.status, 503);
        assert.deepEqual(lote.corpo, { error: 'not_ready' });
        assert.equal(ctx.core.chamadas.executar.length, 0);

        await esperarEstado(ctx.daemon, 'ready', 2000);
        assert.ok(Date.now() - inicio >= SETTLE - 50, `ready chegou cedo demais (${Date.now() - inicio} ms)`);
        assert.equal(typeof ctx.daemon.estado().ready_since, 'string');
    } finally { await encerrar(ctx); }
});

test('cliente que cai durante o warming nao vira ready', async () => {
    const ctx = await subir({ esperarReady: false, settleMs: 150, backoffMs: () => 10000 });
    try {
        await esperarEstado(ctx.daemon, 'warming');
        ctx.core.clientes[0].emit('disconnected', 'NAVIGATION');
        assert.equal(ctx.daemon.estado().state, 'reconnecting');
        await new Promise((r) => setTimeout(r, 250));
        assert.equal(ctx.daemon.estado().state, 'reconnecting');
        assert.equal(ctx.core.chamadas.criarCliente, 1);
    } finally { await encerrar(ctx); }
});

test('conferencia de conexao falha: 503 not_connected sem executar lote e dispara reconexao', async () => {
    const ctx = await subir({ coreOpcoes: { conectado: () => false }, backoffMs: () => 10 });
    try {
        const r = await requisitar(ctx.base, { metodo: 'POST', caminho: '/batch', corpo: LOTE_VALIDO });
        assert.equal(r.status, 503);
        assert.deepEqual(r.corpo, { error: 'not_connected' });
        assert.equal(ctx.core.chamadas.conferencias.length, 1);
        assert.equal(ctx.core.chamadas.conferencias[0].contexto, 'DAEMON');
        assert.equal(ctx.core.chamadas.executar.length, 0);
        assert.equal(ctx.core.chamadas.destruir.length, 1);
        assert.equal(ctx.core.chamadas.destruir[0], ctx.core.clientes[0]);
        await esperarEstado(ctx.daemon, 'ready');
        assert.equal(ctx.core.chamadas.criarCliente, 2);
    } finally { await encerrar(ctx); }
});

test('conferencia de conexao com CONNECTED segue para o lote', async () => {
    const ctx = await subir({ coreOpcoes: { conectado: () => true } });
    try {
        const r = await requisitar(ctx.base, { metodo: 'POST', caminho: '/batch', corpo: LOTE_VALIDO });
        assert.equal(r.status, 200);
        assert.equal(ctx.core.chamadas.conferencias.length, 1);
        assert.equal(ctx.core.chamadas.executar[0].client, ctx.core.clientes[0]);
    } finally { await encerrar(ctx); }
});

test('vigia reconecta quando getState devolve estado diferente de CONNECTED', async () => {
    const ctx = await subir({
        coreOpcoes: { estadoCliente: (i) => (i === 0 ? 'UNPAIRED' : 'CONNECTED') },
        watchdogMs: 5,
        backoffMs: () => 10
    });
    try {
        await esperarCondicao(() => ctx.core.chamadas.criarCliente === 2);
        await esperarEstado(ctx.daemon, 'ready');
        assert.equal(ctx.core.chamadas.destruir.length, 1);
        assert.equal(ctx.core.chamadas.destruir[0], ctx.core.clientes[0]);
    } finally { await encerrar(ctx); }
});

test('vigia reconecta quando getState estoura o prazo', async () => {
    const ctx = await subir({
        coreOpcoes: { estadoCliente: (i) => (i === 0 ? new Promise(() => {}) : 'CONNECTED') },
        watchdogMs: 5,
        watchdogTimeoutMs: 20,
        backoffMs: () => 10
    });
    try {
        await esperarCondicao(() => ctx.core.chamadas.criarCliente === 2);
        await esperarEstado(ctx.daemon, 'ready');
        assert.equal(ctx.core.chamadas.destruir[0], ctx.core.clientes[0]);
    } finally { await encerrar(ctx); }
});

test('vigia com CONNECTED consulta o estado mas nao reconecta', async () => {
    const ctx = await subir({ watchdogMs: 5 });
    try {
        await esperarCondicao(() => ctx.core.clientes[0].getStateChamadas >= 2);
        assert.equal(ctx.daemon.estado().state, 'ready');
        assert.equal(ctx.core.chamadas.destruir.length, 0);
        assert.equal(ctx.core.chamadas.criarCliente, 1);
    } finally { await encerrar(ctx); }
});

test('vigia nao chama getState enquanto um lote esta em andamento', async () => {
    let liberar;
    const segurar = new Promise((r) => { liberar = r; });
    const core = criarCore({
        executar: async (items, batchState) => {
            await segurar;
            const resultados = items.map((i) => ({ phase_key: i.phase_key, success: true, error: null }));
            batchState.resultados.push(...resultados);
            return resultados;
        }
    });
    const ctx = await subir({ core, watchdogMs: 2, watchdogTimeoutMs: 1000 });
    try {
        const pedido = requisitar(ctx.base, { metodo: 'POST', caminho: '/batch', corpo: LOTE_VALIDO });
        await esperarCondicao(() => ctx.core.chamadas.executar.length === 1);
        const durante = ctx.core.clientes[0].getStateChamadas;
        await new Promise((r) => setTimeout(r, 60));
        assert.equal(ctx.core.clientes[0].getStateChamadas, durante, 'getState chamado durante o lote');

        liberar();
        const r = await pedido;
        assert.equal(r.status, 200);
        await esperarCondicao(() => ctx.core.clientes[0].getStateChamadas > durante);
    } finally { await encerrar(ctx); }
});

test('stop desliga o vigia (nenhum getState depois de parar)', async () => {
    const ctx = await subir({ watchdogMs: 5 });
    await esperarCondicao(() => ctx.core.clientes[0].getStateChamadas >= 1);
    await ctx.daemon.stop();
    const depois = ctx.core.clientes[0].getStateChamadas;
    await new Promise((r) => setTimeout(r, 40));
    assert.equal(ctx.core.clientes[0].getStateChamadas, depois);
});

test('teto sem ready: cliente que nunca fica pronto encerra com exit 1 depois de destruir o cliente', async () => {
    const core = criarCore({ cliente: { autoReady: false } });
    const logs = [];
    core.writeLog = (nivel, mensagem) => logs.push({ nivel, mensagem });
    const saidas = [];
    const ctx = await subir({
        core,
        esperarReady: false,
        maxNotReadyMs: 60,
        sair: (c) => saidas.push({ c, destruidos: core.chamadas.destruir.length })
    });
    try {
        await esperarCondicao(() => saidas.length === 1);
        assert.deepEqual(saidas.map((s) => s.c), [1]);
        assert.equal(saidas[0].destruidos, 1, 'cliente deve ser destruido antes de sair');
        assert.equal(core.chamadas.destruir[0], core.clientes[0]);
        const erro = logs.find((l) => l.nivel === 'ERROR');
        assert.ok(erro, 'deve registrar ERROR');
        assert.match(erro.mensagem, /daemon sem ready ha \d+ s; encerrando para os envios voltarem ao modo por processo/);
        assert.equal(ctx.daemon.server.listening, false);
        assert.equal(ctx.daemon.estado().state, 'stopped');
    } finally { await encerrar(ctx); }
});

test('teto sem ready: queda sem volta (reconnecting continuo) encerra com exit 1 e nao recria o cliente', async () => {
    const core = criarCore();
    const saidas = [];
    const ctx = await subir({
        core,
        maxNotReadyMs: 60,
        backoffMs: () => 60000,
        sair: (c) => saidas.push({ c, destruidos: core.chamadas.destruir.length })
    });
    try {
        core.clientes[0].emit('disconnected', 'NAVIGATION');
        await esperarCondicao(() => saidas.length === 1);
        assert.deepEqual(saidas.map((s) => s.c), [1]);
        assert.equal(saidas[0].destruidos, 1, 'cliente da queda deve estar destruido antes de sair');
        assert.equal(core.chamadas.criarCliente, 1, 'backoff longo: nenhuma nova tentativa antes do teto');
        assert.equal(ctx.daemon.server.listening, false);
    } finally { await encerrar(ctx); }
});

test('teto sem ready nao estoura quando o cliente fica ready antes do prazo', async () => {
    const saidas = [];
    const ctx = await subir({ maxNotReadyMs: 80, sair: (c) => saidas.push(c) });
    try {
        await new Promise((r) => setTimeout(r, 200));
        assert.equal(ctx.daemon.estado().state, 'ready');
        assert.deepEqual(saidas, []);
    } finally { await encerrar(ctx); }
});

test('o teto reinicia ao sair de ready: conta desde o ultimo momento fora de ready', async () => {
    const saidas = [];
    const ctx = await subir({ maxNotReadyMs: 150, backoffMs: () => 60000, sair: (c) => saidas.push(c) });
    try {
        await new Promise((r) => setTimeout(r, 100));
        assert.deepEqual(saidas, [], 'ready por 100 ms nao deve estourar o teto de 150 ms');
        const inicio = Date.now();
        ctx.core.clientes[0].emit('disconnected', 'NAVIGATION');
        await esperarCondicao(() => saidas.length === 1);
        assert.deepEqual(saidas, [1]);
        assert.ok(Date.now() - inicio >= 120, `teto contou desde o start, nao desde a saida de ready (${Date.now() - inicio} ms)`);
    } finally { await encerrar(ctx); }
});

test('stop cancela o teto: nenhum encerramento depois de parar', async () => {
    const saidas = [];
    const ctx = await subir({
        coreOpcoes: { cliente: { autoReady: false } },
        esperarReady: false,
        maxNotReadyMs: 50,
        sair: (c) => saidas.push(c)
    });
    await encerrar(ctx);
    await new Promise((r) => setTimeout(r, 120));
    assert.deepEqual(saidas, []);
});

test('destruicao que trava no encerramento: estourado o prazo, sai mesmo assim', async () => {
    const core = criarCore({ cliente: { autoReady: false } });
    core.destruirClienteSilenciosamente = (cliente) => {
        core.chamadas.destruir.push(cliente);
        return new Promise(() => {});
    };
    const saidas = [];
    const ctx = await subir({ core, esperarReady: false, destruirPrazoMs: 30, sair: (c) => saidas.push(c) });
    try {
        await new Promise((r) => setTimeout(r, 5));
        core.clientes[0].emit('qr', 'codigo');
        await esperarCondicao(() => saidas.length === 1);
        assert.deepEqual(saidas, [21]);
        assert.equal(ctx.daemon.server.listening, false);
    } finally { await encerrar(ctx); }
});

test('client_id e comparado sem diferenciar maiusculas e minusculas em /batch e /send', async () => {
    const ctx = await subir();
    try {
        const envio = await requisitar(ctx.base, { metodo: 'POST', caminho: '/send', corpo: { ...ENVIO_VALIDO, client_id: 'TESTE-Cliente' } });
        assert.equal(envio.status, 200);
        const lote = await requisitar(ctx.base, { metodo: 'POST', caminho: '/batch', corpo: { ...LOTE_VALIDO, client_id: 'Teste-CLIENTE' } });
        assert.equal(lote.status, 200);
        const outroPerfil = await requisitar(ctx.base, { metodo: 'POST', caminho: '/send', corpo: { ...ENVIO_VALIDO, client_id: 'teste-cliente-2' } });
        assert.equal(outroPerfil.status, 409);
        assert.deepEqual(outroPerfil.corpo, { error: 'client_mismatch' });
    } finally { await encerrar(ctx); }
});

test('WHATSAPP_DAEMON_MAX_NOT_READY_MS so vale como inteiro positivo; padrao 600000', () => {
    assert.equal(MAX_NOT_READY_MS_PADRAO, 600000);
    assert.equal(lerMaxNotReadyMs('600000'), 600000);
    assert.equal(lerMaxNotReadyMs(undefined), undefined);
    assert.equal(lerMaxNotReadyMs(''), undefined);
    assert.equal(lerMaxNotReadyMs('0'), undefined);
    assert.equal(lerMaxNotReadyMs('-5'), undefined);
    assert.equal(lerMaxNotReadyMs('1.5'), undefined);
    assert.equal(lerMaxNotReadyMs('abc'), undefined);
});

test('reconectar com destroy() travado respeita destruirPrazoMs, limpa LOCK residual e reagenda', async () => {
    const core = criarCore();
    const cleanCalls = [];
    core.destruirClienteSilenciosamente = (cliente) => {
        core.chamadas.destruir.push(cliente);
        return new Promise(() => {}); // nunca resolve
    };
    core.cleanProfileForRetry = (cid) => { cleanCalls.push(cid); };

    const ctx = await subir({ core, destruirPrazoMs: 30, backoffMs: () => 10 });
    try {
        ctx.core.clientes[0].emit('disconnected', 'NAVIGATION');
        await esperarEstado(ctx.daemon, 'ready');
        assert.equal(core.chamadas.criarCliente, 2);
        assert.deepEqual(cleanCalls, ['teste-cliente']);
    } finally { await encerrar(ctx); }
});

test('POST /send com "No LID for user" responde 200 (paridade com exit 0 no spawn)', async () => {
    const logs = [];
    const core = criarCore({
        envio: () => { throw new Error('No LID for user 5511999999999'); }
    });
    core.writeLog = (nivel, mensagem) => logs.push({ nivel, mensagem });
    const ctx = await subir({ core });
    try {
        const r = await requisitar(ctx.base, { metodo: 'POST', caminho: '/send', corpo: ENVIO_VALIDO });
        assert.equal(r.status, 200);
        assert.equal(r.corpo.ok, true);
        assert.equal(r.corpo.skipped_reason, 'no_lid');
        assert.ok(logs.some((l) => l.nivel === 'WARN' && l.mensagem.includes('No LID')));
    } finally { await encerrar(ctx); }
});

test('daemon propaga exec_id da tarefa durante a execucao e restaura "daemon" ao finalizar', async () => {
    const execIdsVistos = [];
    let execIdAtual = 'daemon';
    const core = criarCore({
        envio: () => { execIdsVistos.push(execIdAtual); }
    });
    core.setExecIdAtual = (id) => { execIdAtual = id; };
    const ctx = await subir({ core });
    try {
        const r = await requisitar(ctx.base, { metodo: 'POST', caminho: '/send', corpo: { ...ENVIO_VALIDO, exec_id: 'exec-tarefa-99' } });
        assert.equal(r.status, 200);
        assert.deepEqual(execIdsVistos, ['exec-tarefa-99']);
        assert.equal(execIdAtual, 'daemon');
    } finally { await encerrar(ctx); }
});
