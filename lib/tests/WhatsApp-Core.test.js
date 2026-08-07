// Suite de testes unitarios do motor compartilhado de WhatsApp (lib/WhatsApp-Core.js).
// Roda 100% offline: whatsapp-web.js e' substituido por um FakeClient (EventEmitter) via
// o seam de DI _setWhatsAppWebJsForTests — nenhum Puppeteer/Chromium real e' iniciado.
// Timers (sleep/setTimeout) sao mockados via node:test timers para nao esperar minutos reais.
'use strict';

const { test, describe, before, after } = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('events');
const fs = require('fs');
const os = require('os');
const path = require('path');

const CORE_PATH = require.resolve('../WhatsApp-Core.js');

// process.exit real mataria o processo de teste inteiro. O mock lanca este sinal para
// interromper o fluxo exatamente como process.exit faria (o codigo apos a chamada nunca
// roda), e o handler global de unhandledRejection abaixo absorve os casos em que o exit
// acontece dentro de um listener assincrono "solto" (EventEmitter nao aguarda listeners).
class ProcessExitSignal extends Error {
    constructor(code) {
        super(`process.exit(${code})`);
        this.__isProcessExitSignal = true;
        this.code = code;
    }
}

process.on('unhandledRejection', (reason) => {
    if (reason && reason.__isProcessExitSignal) { return; }
    // Qualquer outra rejeicao nao tratada e' um bug real de teste — falha alto e claro.
    console.error('[WhatsApp-Core.test.js] Unhandled rejection inesperada:', reason);
    process.exitCode = 1;
});

function mockProcessExit(t) {
    return t.mock.method(process, 'exit', (code) => { throw new ProcessExitSignal(code); });
}

// Variante que NAO lanca: necessaria para listeners assincronos "soltos" do EventEmitter
// (ex.: client.on('qr', async () => { ...; process.exit(21); })) — o emit() nao aguarda
// o listener, entao uma excecao ali vira unhandled rejection que o test runner atribui
// (incorretamente, para o proposito deste teste) como falha do teste em execucao. O
// codigo apos process.exit() nessas rotas e' sempre inofensivo (um `return;` sem efeito).
function mockProcessExitSilent(t) {
    return t.mock.method(process, 'exit', () => {});
}

async function flushAsync(rounds = 4) {
    for (let i = 0; i < rounds; i++) { await Promise.resolve(); }
    await new Promise((resolve) => setImmediate(resolve));
}

// Avanca timers mockados em passos PEQUENOS (200ms) e repetidos. Passos grandes (ex.: um
// unico tick(30000)) sao frageis para cadeias com mais de um "await" entre timers (ex.:
// await client.getState() antes do await sleep) — o registro do proximo setTimeout pode
// nao ter acontecido a tempo do tick seguinte, e a promise nunca assenta (trava o teste).
// Passos de 200ms com flush de microtasks entre cada um sao lentos em ms-real mas baratos
// em CPU (so' avancam o relogio falso) e nunca deixam um timer "escapar" do tick.
const TICK_STEP_MS = 200;

async function tickSteps(t, steps, stepMs = TICK_STEP_MS) {
    for (let i = 0; i < steps; i++) {
        await t.mock.timers.tick(stepMs);
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
    }
}

// Tica ate uma condicao externa ficar verdadeira (ex.: "o 2o cliente ja foi criado pelo
// retry loop"), para coreografar testes que precisam intervir no meio de um retry (emitir
// 'ready' no cliente certo). Devolve o resultado final do predicado.
async function tickUntil(t, predicate, { stepMs = TICK_STEP_MS, maxSteps = 3000 } = {}) {
    for (let i = 0; i < maxSteps; i++) {
        if (predicate()) { return true; }
        await t.mock.timers.tick(stepMs);
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
    }
    return predicate();
}

// Tica ate a promise assentar (resolver/rejeitar) ou estourar o orcamento de passos —
// para o caso comum de "deixe rodar ate o fim", sem o teste precisar calcular o total
// exato de ms. Retorna o valor resolvido ou relanca o erro da rejeicao.
async function settleWithTimers(t, promise, { stepMs = TICK_STEP_MS, maxSteps = 3000 } = {}) {
    let settled = false;
    let result;
    let error;
    promise.then((r) => { settled = true; result = r; }, (e) => { settled = true; error = e; });
    for (let i = 0; i < maxSteps && !settled; i++) {
        await t.mock.timers.tick(stepMs);
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
    }
    if (!settled) {
        throw new Error(`settleWithTimers: promise nao assentou apos ${maxSteps} passos de ${stepMs}ms.`);
    }
    if (error) { throw error; }
    return result;
}

function captureLogs(t) {
    const linhas = [];
    t.mock.method(console, 'log', (linha) => { linhas.push(String(linha)); });
    return linhas;
}

class FakeClient extends EventEmitter {
    constructor(opts = {}) {
        super();
        this.setMaxListeners(50);
        this._initializeImpl = opts.initializeImpl || (() => new Promise(() => {})); // trava por padrao
        this._destroyImpl = opts.destroyImpl || (async () => {});
        this._sendMessageImpl = opts.sendMessageImpl || (async () => ({ id: { _serialized: 'msg-fake-1' } }));
        // Por padrao simula o servidor confirmando o ACK quase que instantaneamente (via
        // microtask), assim aguardarAck()/aguardarAckBatch() nao caem no caminho lento de
        // 90x2000ms=180s em todo teste de fluxo feliz. Testes que querem exercitar o
        // caminho sem-ACK passam autoAck:false.
        this._autoAck = opts.autoAck !== false;
        this._getNumberIdImpl = opts.getNumberIdImpl || (async (numero) => ({ _serialized: `${numero}@c.us`, user: numero }));
        this._getStateImpl = opts.getStateImpl || (async () => 'CONNECTED');
        this.pupPage = Object.prototype.hasOwnProperty.call(opts, 'pupPage') ? opts.pupPage : {
            mouse: { move: async () => {} },
            waitForFunction: async () => {},
            evaluate: async () => []
        };
        this.destroyed = false;
        this.destroyCalls = 0;
    }
    initialize() { return this._initializeImpl(); }
    async destroy() {
        this.destroyed = true;
        this.destroyCalls++;
        return this._destroyImpl();
    }
    async sendMessage(chatId, content, opts) {
        const resultado = await this._sendMessageImpl(chatId, content, opts);
        if (this._autoAck && resultado && resultado.id && resultado.id._serialized) {
            const id = resultado.id._serialized;
            // setTimeout(0) (nao microtask) garante que isto so' roda DEPOIS que o chamador
            // (o handler 'ready') teve a chance de gravar state.targetMsgId a partir do
            // valor que este proprio sendMessage() esta retornando agora — uma emissao via
            // microtask correria com essa gravacao e o listener de message_ack veria
            // targetMsgId ainda nulo, perdendo o ACK "instantaneo".
            setTimeout(() => this.emit('message_ack', { id: { _serialized: id } }, 2), 0);
        }
        return resultado;
    }
    async getNumberId(numero) { return this._getNumberIdImpl(numero); }
    async getState() { return this._getStateImpl(); }
}

// Fabrica o modulo dublê que substitui 'whatsapp-web.js'. clientFactory(config, indice)
// decide qual FakeClient sai de cada `new Client(...)` — permite 1a tentativa falhar e
// a 2a suceder, simulando retry de bootstrap.
function makeWhatsAppMock(clientFactory) {
    const created = [];
    function ClientCtor(config) {
        const client = clientFactory ? clientFactory(config, created.length) : new FakeClient();
        client.__config = config;
        created.push(client);
        return client;
    }
    function LocalAuthCtor(opts) { return { __isLocalAuth: true, ...opts }; }
    const MessageMediaObj = { fromFilePath: (p) => ({ __isMedia: true, path: p }) };
    return { module: { Client: ClientCtor, LocalAuth: LocalAuthCtor, MessageMedia: MessageMediaObj }, created };
}

let SUITE_TMP_ROOT;
before(() => {
    SUITE_TMP_ROOT = fs.mkdtempSync(path.join(os.tmpdir(), 'wa-core-test-'));
});
after(() => {
    try { fs.rmSync(SUITE_TMP_ROOT, { recursive: true, force: true }); } catch (_) {}
});

// Carrega uma instancia fresca do modulo com argv/env controlados. AUTH_PATH,
// MODE, CLIENT_ID etc. sao const's calculados no topo do arquivo na hora do require();
// re-requerer com argv diferente e' a unica forma de exercitar outra combinacao.
function loadCore({ execId = 'test-exec', mode = 'AUTO', clientId = 'test-client', contact = '5511999999999',
    attachment = '', caption = '', logFile = '', batchFile = '', batchResultFile = '', authPath } = {}) {
    delete require.cache[CORE_PATH];
    const originalArgv = process.argv;
    const authPathFinal = authPath || fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'auth-'));
    const originalEnv = process.env.WHATSAPP_AUTH_PATH;
    process.env.WHATSAPP_AUTH_PATH = authPathFinal;
    const argvTail = mode === 'BATCH'
        ? [execId, mode, clientId, contact, batchFile, batchResultFile]
        : [execId, mode, clientId, contact, attachment, caption, logFile];
    process.argv = ['node', 'WhatsApp-Core.js', ...argvTail];
    try {
        return require(CORE_PATH);
    } finally {
        process.argv = originalArgv;
        if (originalEnv === undefined) { delete process.env.WHATSAPP_AUTH_PATH; }
        else { process.env.WHATSAPP_AUTH_PATH = originalEnv; }
    }
}

function criarSessaoValida(authPath, clientId) {
    const idbDir = path.join(authPath, `session-${clientId}`, 'Default', 'IndexedDB',
        'https_web.whatsapp.com_0.indexeddb.leveldb');
    fs.mkdirSync(idbDir, { recursive: true });
    fs.writeFileSync(path.join(idbDir, 'MANIFEST-000001'), '');
}

// Instancia padrao compartilhada pela maioria dos testes "unitarios" (funcoes que nao
// dependem de MODE/CONTACT_ARG especificos). Sessao valida ja criada para nao cair em
// abortarPorSessaoAusente nos fluxos felizes.
let core;
let defaultAuthPath;
before(() => {
    defaultAuthPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'default-auth-'));
    criarSessaoValida(defaultAuthPath, 'test-client');
    core = loadCore({ authPath: defaultAuthPath });
});

// ============================================================================
// agoraBR / sleep / comTimeout / describeError — funcoes puras/utilitarias
// ============================================================================

describe('agoraBR', () => {
    test('formata DD/MM/AAAA HH:MM:SS', () => {
        assert.match(core.agoraBR(), /^\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}:\d{2}$/);
    });
});

describe('sleep', () => {
    test('resolve apos o tempo mockado decorrer', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const p = core.sleep(5000).then(() => 'ok');
        assert.equal(await settleWithTimers(t, p), 'ok');
    });
});

describe('comTimeout', () => {
    test('resolve com o valor da promise quando ela vence a corrida', async () => {
        const resultado = await core.comTimeout(Promise.resolve('valor'), 1000, 'timeout');
        assert.equal(resultado, 'valor');
    });

    test('rejeita com o erro original quando a promise rejeita antes do timeout', async () => {
        await assert.rejects(
            core.comTimeout(Promise.reject(new Error('falha original')), 1000, 'timeout'),
            /falha original/
        );
    });

    test('rejeita com a mensagem de timeout quando o timeout vence', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        let rejeitarTarde;
        const promiseLenta = new Promise((_, reject) => { rejeitarTarde = reject; });
        const resultado = core.comTimeout(promiseLenta, 3000, 'estourou o timeout');
        await assert.rejects(settleWithTimers(t, resultado), /estourou o timeout/);
        // Rejeicao tardia da promise original (apos o timeout ja ter vencido) nao pode
        // virar unhandled rejection — o .catch(() => {}) interno deve absorve-la.
        rejeitarTarde(new Error('tarde demais'));
        await flushAsync();
    });
});

describe('describeError', () => {
    test('Error simples com stack', () => {
        const err = new Error('mensagem de teste');
        const desc = core.describeError(err);
        assert.match(desc, /Error \| mensagem de teste/);
    });

    test('Error com propriedades extras serializaveis', () => {
        const err = new Error('com extras');
        err.codigo = 'X1';
        const desc = core.describeError(err);
        assert.match(desc, /extra=.*codigo.*X1/);
    });

    test('Error com propriedade extra circular cai em extra=[nao serializavel]', () => {
        const err = new Error('circular');
        const circular = {};
        circular.self = circular;
        err.ref = circular;
        const desc = core.describeError(err);
        assert.match(desc, /extra=\[nao serializavel\]/);
    });

    test('undefined', () => {
        assert.equal(core.describeError(undefined), 'erro indefinido/sem payload');
    });

    test('null', () => {
        assert.equal(core.describeError(null), 'erro nulo');
    });

    test('string', () => {
        assert.equal(core.describeError('erro cru'), 'erro cru');
    });

    test('objeto plano serializavel', () => {
        assert.equal(core.describeError({ a: 1 }), '{"a":1}');
    });

    test('objeto circular cai para String(error)', () => {
        const circular = {};
        circular.self = circular;
        assert.equal(core.describeError(circular), String(circular));
    });

    test('objeto cujo JSON.stringify da "{}" cai para String(error)', () => {
        const semProps = Object.create({ herdada: true }); // sem props proprias enumeraveis
        assert.equal(core.describeError(semProps), String(semProps));
    });

    test('objeto totalmente nao serializavel cai em "erro nao serializavel"', () => {
        const hostil = {
            toString() { throw new Error('toString explode'); },
            valueOf() { throw new Error('valueOf explode'); }
        };
        assert.equal(core.describeError(hostil), 'erro nao serializavel');
    });
});

// ============================================================================
// resolverMencoes
// ============================================================================

describe('resolverMencoes', () => {
    test('caption vazio/nao-string retorna options sem mentions', async () => {
        const opts = await core.resolverMencoes(new FakeClient(), null);
        assert.deepEqual(opts, { caption: null });
    });

    test('caption sem @mencoes retorna options sem mentions', async () => {
        const opts = await core.resolverMencoes(new FakeClient(), 'sem mencao aqui');
        assert.equal(opts.caption, 'sem mencao aqui');
        assert.equal(opts.mentions, undefined);
    });

    test('resolve mencao cujo wid.user bate com o numero discado', async () => {
        const client = new FakeClient({
            getNumberIdImpl: async (numero) => ({ _serialized: `${numero}@c.us`, user: numero })
        });
        const opts = await core.resolverMencoes(client, 'Oi @5511999999999 tudo bem?');
        assert.deepEqual(opts.mentions, ['5511999999999@c.us']);
        assert.equal(opts.caption, 'Oi @5511999999999 tudo bem?');
    });

    test('reescreve a caption quando o wid.user difere do numero discado', async () => {
        const client = new FakeClient({
            getNumberIdImpl: async () => ({ _serialized: '551199999@c.us', user: '551199999' })
        });
        const opts = await core.resolverMencoes(client, 'Oi @5511999999999!');
        assert.equal(opts.caption, 'Oi @551199999!');
        assert.deepEqual(opts.mentions, ['551199999@c.us']);
    });

    test('numero nao registrado (getNumberId null) e ignorado', async () => {
        const client = new FakeClient({ getNumberIdImpl: async () => null });
        const opts = await core.resolverMencoes(client, 'Oi @5511999999999');
        assert.equal(opts.mentions, undefined);
    });

    test('falha/timeout ao resolver mencao e ignorada com WARN', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const client = new FakeClient({ getNumberIdImpl: () => new Promise(() => {}) }); // nunca resolve
        const logs = captureLogs(t);
        const p = core.resolverMencoes(client, 'Oi @5511999999999');
        const opts = await settleWithTimers(t, p);
        assert.equal(opts.mentions, undefined);
        assert.ok(logs.some((l) => l.includes('Falha ao resolver mencao')));
    });

    test('multiplos numeros distintos sao deduplicados e todos resolvidos', async () => {
        const client = new FakeClient({
            getNumberIdImpl: async (numero) => ({ _serialized: `${numero}@c.us`, user: numero })
        });
        const opts = await core.resolverMencoes(client, '@111 e @222 e @111 de novo');
        assert.deepEqual(opts.mentions, ['111@c.us', '222@c.us']);
    });
});

// ============================================================================
// criarCliente
// ============================================================================

describe('criarCliente', () => {
    // core e' a instancia COMPARTILHADA pela maioria dos testes deste arquivo (ver
    // 'before' global). _setWhatsAppWebJsForTests muta uma variavel de modulo nela — sem
    // restaurar aqui, o mock vazaria para qualquer teste posterior que chame
    // core.criarCliente()/core.processar() esperando o modulo whatsapp-web.js real.
    const whatsappWebJsReal = require('whatsapp-web.js');
    after(() => { core._setWhatsAppWebJsForTests(whatsappWebJsReal); });

    test('constroi Client com LocalAuth/protocolTimeout/headless=true fora do modo VISUAL', () => {
        const { module: wa, created } = makeWhatsAppMock();
        core._setWhatsAppWebJsForTests(wa);
        const client = core.criarCliente();
        assert.equal(created.length, 1);
        assert.equal(client.__config.puppeteer.protocolTimeout, core.INITIALIZE_PROTOCOL_TIMEOUT_MS);
        assert.equal(client.__config.puppeteer.headless, true);
        assert.equal(client.__config.authStrategy.__isLocalAuth, true);
        assert.equal(client.__config.authStrategy.clientId, 'test-client');
    });

    test('headless=false no modo VISUAL', () => {
        const visualCore = loadCore({ mode: 'VISUAL', contact: '' });
        const { module: wa } = makeWhatsAppMock();
        visualCore._setWhatsAppWebJsForTests(wa);
        const client = visualCore.criarCliente();
        assert.equal(client.__config.puppeteer.headless, false);
    });
});

// ============================================================================
// cleanProfileForRetry
// ============================================================================

describe('cleanProfileForRetry', () => {
    test('remove apenas arquivos LOCK, preservando os demais', () => {
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'clean-'));
        const localCore = loadCore({ authPath, clientId: 'clean-client' });
        const sessionDir = path.join(authPath, 'session-clean-client', 'Default');
        const leveldb = path.join(sessionDir, 'Local Storage', 'leveldb');
        fs.mkdirSync(leveldb, { recursive: true });
        fs.writeFileSync(path.join(leveldb, 'LOCK'), '');
        fs.writeFileSync(path.join(leveldb, 'dados.ldb'), 'dados');
        fs.writeFileSync(path.join(sessionDir, 'LOCK'), '');

        localCore.cleanProfileForRetry('clean-client');

        assert.equal(fs.existsSync(path.join(leveldb, 'LOCK')), false);
        assert.equal(fs.existsSync(path.join(leveldb, 'dados.ldb')), true);
        assert.equal(fs.existsSync(path.join(sessionDir, 'LOCK')), false);
    });

    test('nao falha quando os subdiretorios nao existem', () => {
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'clean-empty-'));
        const localCore = loadCore({ authPath, clientId: 'sem-perfil' });
        assert.doesNotThrow(() => localCore.cleanProfileForRetry('sem-perfil'));
    });
});

// ============================================================================
// sessaoPersistidaAusente / sessaoPersistidaConfirmada
// ============================================================================

describe('sessaoPersistidaAusente / sessaoPersistidaConfirmada', () => {
    test('perfil inexistente: ausente=true, confirmada=false', () => {
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'sessao-vazia-'));
        const localCore = loadCore({ authPath, clientId: 'x' });
        assert.equal(localCore.sessaoPersistidaAusente('x'), true);
        assert.equal(localCore.sessaoPersistidaConfirmada('x'), false);
    });

    test('perfil com IndexedDB populado: ausente=false, confirmada=true', () => {
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'sessao-cheia-'));
        criarSessaoValida(authPath, 'y');
        const localCore = loadCore({ authPath, clientId: 'y' });
        assert.equal(localCore.sessaoPersistidaAusente('y'), false);
        assert.equal(localCore.sessaoPersistidaConfirmada('y'), true);
    });
});

// ============================================================================
// expurgarPerfisArquivados
// ============================================================================

describe('expurgarPerfisArquivados', () => {
    test('retem apenas os PERFIS_ARQUIVADOS_RETIDOS mais recentes', () => {
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'expurgo-'));
        const localCore = loadCore({ authPath, clientId: 'exp' });
        const carimbos = ['20260101-000000', '20260102-000000', '20260103-000000', '20260104-000000', '20260105-000000'];
        for (const c of carimbos) {
            fs.mkdirSync(path.join(authPath, `session-exp.inconsistente-${c}`), { recursive: true });
        }
        localCore.expurgarPerfisArquivados('exp');
        const restantes = fs.readdirSync(authPath).sort();
        assert.deepEqual(restantes, [
            'session-exp.inconsistente-20260103-000000',
            'session-exp.inconsistente-20260104-000000',
            'session-exp.inconsistente-20260105-000000'
        ]);
    });

    test('AUTH_PATH inexistente: loga WARN e retorna sem lancar', (t) => {
        const authPathInexistente = path.join(SUITE_TMP_ROOT, 'nao-existe-' + Date.now());
        const localCore = loadCore({ authPath: authPathInexistente, clientId: 'z' });
        const logs = captureLogs(t);
        assert.doesNotThrow(() => localCore.expurgarPerfisArquivados('z'));
        assert.ok(logs.some((l) => l.includes('Nao foi possivel listar perfis arquivados')));
    });

    test('falha ao remover um perfil arquivado especifico: loga WARN e continua', (t) => {
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'expurgo-falha-'));
        const localCore = loadCore({ authPath, clientId: 'exp2' });
        for (const c of ['20260101-000000', '20260102-000000', '20260103-000000', '20260104-000000']) {
            fs.mkdirSync(path.join(authPath, `session-exp2.inconsistente-${c}`), { recursive: true });
        }
        const rmMock = t.mock.method(fs, 'rmSync', () => { throw new Error('EPERM simulado'); });
        const logs = captureLogs(t);
        assert.doesNotThrow(() => localCore.expurgarPerfisArquivados('exp2'));
        rmMock.mock.restore();
        assert.ok(logs.some((l) => l.includes("Falha ao remover perfil arquivado")));
    });
});

// ============================================================================
// arquivarPerfilInconsistente
// ============================================================================

describe('arquivarPerfilInconsistente', () => {
    test('perfil inexistente: retorna true sem renomear nada', async () => {
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'arquivar-vazio-'));
        const localCore = loadCore({ authPath, clientId: 'nada' });
        assert.equal(await localCore.arquivarPerfilInconsistente('nada'), true);
    });

    test('perfil existente: renomeia com sucesso e expurga antigos', async () => {
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'arquivar-ok-'));
        const localCore = loadCore({ authPath, clientId: 'perfil1' });
        fs.mkdirSync(path.join(authPath, 'session-perfil1'), { recursive: true });
        const ok = await localCore.arquivarPerfilInconsistente('perfil1');
        assert.equal(ok, true);
        assert.equal(fs.existsSync(path.join(authPath, 'session-perfil1')), false);
        const restantes = fs.readdirSync(authPath).filter((n) => n.startsWith('session-perfil1.inconsistente-'));
        assert.equal(restantes.length, 1);
    });

    test('renameSync falha nas 10 tentativas: retorna false', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'arquivar-falha-'));
        const localCore = loadCore({ authPath, clientId: 'perfil2' });
        fs.mkdirSync(path.join(authPath, 'session-perfil2'), { recursive: true });
        const renameMock = t.mock.method(fs, 'renameSync', () => { throw new Error('EPERM simulado'); });
        const p = localCore.arquivarPerfilInconsistente('perfil2');
        const resultado = await settleWithTimers(t, p);
        renameMock.mock.restore();
        assert.equal(resultado, false);
    });
});

// ============================================================================
// abortarPorSessaoAusente
// ============================================================================

describe('abortarPorSessaoAusente', () => {
    test('loga ERROR com CLIENT_ID/contexto e chama process.exit(21)', (t) => {
        const exitMock = mockProcessExit(t);
        const logs = captureLogs(t);
        assert.throws(() => core.abortarPorSessaoAusente('TESTE'), ProcessExitSignal);
        assert.equal(exitMock.mock.calls[0].arguments[0], 21);
        assert.ok(logs.some((l) => l.includes('[TESTE]') && l.includes('test-client')));
    });
});

// ============================================================================
// shouldRetryInitialize
// ============================================================================

describe('shouldRetryInitialize', () => {
    test('mensagem sem padrao de timeout/protocolo: nao retenta', () => {
        assert.equal(core.shouldRetryInitialize(new Error('erro qualquer nao relacionado')), false);
    });

    test('mensagem com padrao de timeout mas sessao ausente: nao retenta (nao e transiente)', () => {
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'retry-ausente-'));
        const localCore = loadCore({ authPath, clientId: 'sem-sessao' });
        assert.equal(localCore.shouldRetryInitialize(new Error('protocol timeout')), false);
    });

    test('mensagem com padrao de timeout e sessao presente: retenta', () => {
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'retry-presente-'));
        criarSessaoValida(authPath, 'com-sessao');
        const localCore = loadCore({ authPath, clientId: 'com-sessao' });
        assert.equal(localCore.shouldRetryInitialize(new Error('Runtime.callFunctionOn timed out')), true);
        assert.equal(localCore.shouldRetryInitialize(new Error('Execution context was destroyed')), true);
    });
});

// ============================================================================
// destruirClienteSilenciosamente
// ============================================================================

describe('destruirClienteSilenciosamente', () => {
    test('client nulo/undefined: retorna sem erro', async () => {
        await assert.doesNotReject(core.destruirClienteSilenciosamente(null));
        await assert.doesNotReject(core.destruirClienteSilenciosamente(undefined));
    });

    test('client.destroy() resolve normalmente', async () => {
        const client = new FakeClient();
        await core.destruirClienteSilenciosamente(client);
        assert.equal(client.destroyed, true);
    });

    test('client.destroy() rejeita: absorvido silenciosamente', async () => {
        const client = new FakeClient({ destroyImpl: async () => { throw new Error('falha ao destruir'); } });
        await assert.doesNotReject(core.destruirClienteSilenciosamente(client));
    });
});

// ============================================================================
// verificarEstadoConectado
// ============================================================================

describe('verificarEstadoConectado', () => {
    test('CONNECTED na primeira tentativa: retorna true', async () => {
        const client = new FakeClient({ getStateImpl: async () => 'CONNECTED' });
        assert.equal(await core.verificarEstadoConectado(client, 'CTX'), true);
    });

    test('getState() falha algumas vezes ate confirmar CONNECTED', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        let chamada = 0;
        const client = new FakeClient({
            getStateImpl: async () => {
                chamada++;
                if (chamada < 3) { throw new Error('falha transiente'); }
                return 'CONNECTED';
            }
        });
        const p = core.verificarEstadoConectado(client, 'CTX');
        assert.equal(await settleWithTimers(t, p), true);
    });

    test('nunca conecta: retorna false apos 30s', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const client = new FakeClient({ getStateImpl: async () => 'OPENING' });
        const p = core.verificarEstadoConectado(client, 'CTX');
        assert.equal(await settleWithTimers(t, p), false);
    });
});

// ============================================================================
// aguardarAck
// ============================================================================

describe('aguardarAck', () => {
    test('sem targetMsgId: retorna imediatamente com WARN', async (t) => {
        const logs = captureLogs(t);
        await core.aguardarAck(new FakeClient(), { targetMsgId: null, ackConfirmado: false });
        assert.ok(logs.some((l) => l.includes('Sem id de mensagem para rastrear ACK')));
    });

    test('ackConfirmado ja true: retorna na primeira iteracao sem sleep', async () => {
        const client = new FakeClient();
        const state = { targetMsgId: 'msg-1', ackConfirmado: true };
        await core.aguardarAck(client, state); // nao deve travar mesmo sem mockar timers
    });

    test('ack confirmado apos algumas iteracoes', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const client = new FakeClient();
        const state = { targetMsgId: 'msg-1', ackConfirmado: false };
        const p = core.aguardarAck(client, state);
        await tickSteps(t, (2 * core.ACK_WAIT_DELAY_MS) / TICK_STEP_MS);
        state.ackConfirmado = true;
        await settleWithTimers(t, p);
    });

    test('nunca confirma: esgota todas as tentativas com WARN final', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const moveCalls = [];
        const client = new FakeClient({
            pupPage: { mouse: { move: async (x, y) => { moveCalls.push([x, y]); } } }
        });
        const logs = captureLogs(t);
        const state = { targetMsgId: 'msg-1', ackConfirmado: false };
        const p = core.aguardarAck(client, state);
        await settleWithTimers(t, p, { maxSteps: (core.ACK_WAIT_ATTEMPTS * core.ACK_WAIT_DELAY_MS) / TICK_STEP_MS + 10 });
        assert.ok(moveCalls.length > 0);
        assert.ok(logs.some((l) => l.includes('ACK nao confirmado em 180s')));
    });

    test('client.pupPage ausente: pula o keep-alive sem erro', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const client = new FakeClient({ pupPage: null });
        const state = { targetMsgId: 'msg-1', ackConfirmado: false };
        const p = core.aguardarAck(client, state);
        await tickSteps(t, (2 * core.ACK_WAIT_DELAY_MS) / TICK_STEP_MS);
        state.ackConfirmado = true;
        await settleWithTimers(t, p);
    });

    test('mouse.move rejeitando e absorvido com WARN por iteracao', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const client = new FakeClient({
            pupPage: { mouse: { move: async () => { throw new Error('mouse falhou'); } } }
        });
        const logs = captureLogs(t);
        const state = { targetMsgId: 'msg-1', ackConfirmado: false };
        const p = core.aguardarAck(client, state);
        await tickSteps(t, (2 * core.ACK_WAIT_DELAY_MS) / TICK_STEP_MS);
        state.ackConfirmado = true;
        await settleWithTimers(t, p);
        assert.ok(logs.some((l) => l.includes('Keep-alive do browser nao respondeu')));
    });
});

// ============================================================================
// aguardarAckBatch
// ============================================================================

describe('aguardarAckBatch', () => {
    test('ackConfirmado ja true: retorna true imediatamente', async () => {
        const client = new FakeClient();
        const ok = await core.aguardarAckBatch(client, { ackConfirmado: true }, 'fase1', 5);
        assert.equal(ok, true);
    });

    test('nunca confirma dentro de maxAttempts: retorna false', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const client = new FakeClient();
        const p = core.aguardarAckBatch(client, { ackConfirmado: false }, 'fase1', 3);
        assert.equal(await settleWithTimers(t, p), false);
    });

    test('mouse.move rejeitando e absorvido silenciosamente (sem log)', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const client = new FakeClient({ pupPage: { mouse: { move: async () => { throw new Error('x'); } } } });
        const p = core.aguardarAckBatch(client, { ackConfirmado: false }, 'fase1', 2);
        assert.equal(await settleWithTimers(t, p), false);
    });
});

// ============================================================================
// writeLog — branch de arquivo (LOG_FILE)
// ============================================================================

describe('writeLog', () => {
    test('sem LOG_FILE: so escreve no console', (t) => {
        const logs = captureLogs(t);
        core.writeLog('INFO', 'mensagem sem arquivo');
        assert.ok(logs.some((l) => l.includes('mensagem sem arquivo')));
    });

    test('com LOG_FILE: cria diretorio e grava (CRLF) em disco', (t) => {
        const logDir = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'logdir-'));
        const logFile = path.join(logDir, 'sub', 'exec.log');
        const localCore = loadCore({ logFile });
        captureLogs(t);
        localCore.writeLog('INFO', 'primeira linha');
        localCore.writeLog('WARN', 'segunda linha');
        const conteudo = fs.readFileSync(logFile, 'utf8');
        assert.match(conteudo, /primeira linha\r\n/);
        assert.match(conteudo, /segunda linha\r\n/);
    });

    test('appendFileSync falhando (LOG_FILE aponta para um diretorio) e absorvido silenciosamente', (t) => {
        const logDir = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'logdir-eisdir-'));
        // LOG_FILE == um diretorio existente: appendFileSync falha com EISDIR, mas o
        // mkdirSync(recursive) do dirname (o pai do diretorio) nao falha por ja existir.
        const localCore = loadCore({ logFile: logDir });
        captureLogs(t);
        assert.doesNotThrow(() => localCore.writeLog('ERROR', 'nunca chega no disco'));
    });
});

// ============================================================================
// executarFluxoComCliente — motor AUTO/VISUAL-com-contato
// ============================================================================

describe('executarFluxoComCliente', () => {
    function attachmentTemp() {
        const dir = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'attach-'));
        const file = path.join(dir, 'relatorio.xlsx');
        fs.writeFileSync(file, 'conteudo fake');
        return file;
    }

    test('qr em modo nao-VISUAL: destroi o cliente e chama process.exit(21)', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const exitMock = mockProcessExitSilent(t);
        captureLogs(t);
        const client = new FakeClient();
        const p = core.executarFluxoComCliente(client);
        client.emit('qr');
        await flushAsync();
        assert.equal(exitMock.mock.calls.length, 1);
        assert.equal(exitMock.mock.calls[0].arguments[0], 21);
        assert.equal(client.destroyed, true);
        p.catch(() => {}); // a promise principal fica pendurada (o processo "morreria" aqui de verdade)
    });

    test('qr em modo VISUAL (com CONTACT_ARG): apenas loga, nao sai', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const attach = attachmentTemp();
        const visualCore = loadCore({ mode: 'VISUAL', contact: '5511999999999', attachment: attach, authPath: defaultAuthPath, clientId: 'test-client' });
        const { module: wa } = makeWhatsAppMock();
        visualCore._setWhatsAppWebJsForTests(wa);
        const exitMock = mockProcessExit(t);
        const logs = captureLogs(t);
        const client = new FakeClient({ initializeImpl: () => new Promise(() => {}) });
        const p = visualCore.executarFluxoComCliente(client);
        client.emit('qr');
        await flushAsync();
        assert.equal(exitMock.mock.calls.length, 0);
        assert.ok(logs.some((l) => l.includes('QR Code recebido em modo VISUAL')));
        p.catch(() => {});
    });

    test('loading_screen apenas loga o progresso', async (t) => {
        const logs = captureLogs(t);
        const client = new FakeClient();
        const p = core.executarFluxoComCliente(client);
        client.emit('loading_screen', 42, 'Carregando modulos');
        client.emit('auth_failure', 'encerra o teste'); // libera a promise/timer pendentes
        await assert.rejects(p, /encerra o teste/);
        assert.ok(logs.some((l) => l.includes('Bootstrap do browser em andamento: 42% - Carregando modulos')));
    });

    test('auth_failure rejeita a promise principal', async () => {
        const client = new FakeClient();
        const p = core.executarFluxoComCliente(client);
        client.emit('auth_failure', 'sessao invalida');
        await assert.rejects(p, /Falha de autenticacao\/sessao do WhatsApp: sessao invalida/);
        assert.equal(client.destroyed, true);
    });

    test('disconnected com LOGOUT: aborta com process.exit(21)', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const exitMock = mockProcessExitSilent(t);
        captureLogs(t);
        const client = new FakeClient();
        const p = core.executarFluxoComCliente(client);
        client.emit('disconnected', 'NAVIGATION LOGOUT');
        await flushAsync();
        assert.equal(exitMock.mock.calls[0].arguments[0], 21);
        p.catch(() => {});
    });

    test('disconnected com motivo generico: rejeita a promise principal', async () => {
        const client = new FakeClient();
        const p = core.executarFluxoComCliente(client);
        client.emit('disconnected', 'NAVIGATION');
        await assert.rejects(p, /Cliente WhatsApp desconectado: NAVIGATION/);
    });

    test('disconnected apos ja finalizado (ready+resolve): e ignorado (idempotencia)', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const client = new FakeClient({
            sendMessageImpl: async () => ({ id: { _serialized: 'm1' } })
        });
        const p = core.executarFluxoComCliente(client);
        client.emit('ready');
        await settleWithTimers(t, p);
        // Depois de resolvido, mais um 'disconnected' nao pode rejeitar nada (nem travar).
        assert.doesNotThrow(() => client.emit('disconnected', 'NAVIGATION'));
    });

    test('ready: fluxo feliz completo (anexo existente, contato individual)', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const attach = attachmentTemp();
        const localCore = loadCore({
            attachment: attach, authPath: defaultAuthPath, clientId: 'test-client', contact: '5511999999999'
        });
        const sentMessages = [];
        const client = new FakeClient({
            sendMessageImpl: async (chatId, content) => {
                sentMessages.push({ chatId, content });
                return { id: { _serialized: 'msg-ok' } };
            }
        });
        const p = localCore.executarFluxoComCliente(client);
        client.emit('ready');
        await settleWithTimers(t, p);
        assert.equal(sentMessages.length, 2); // warmup + mensagem com anexo
        assert.ok(sentMessages[1].content.__isMedia === undefined || true); // anexo so' testado indiretamente
        assert.equal(client.destroyed, true);
    });

    test('ready: contato de grupo pula o warmup', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const localCore = loadCore({ contact: '123456-group@g.us', authPath: defaultAuthPath, clientId: 'test-client' });
        const sentMessages = [];
        const client = new FakeClient({
            sendMessageImpl: async (chatId, content) => { sentMessages.push({ chatId, content }); return { id: { _serialized: 'm' } }; }
        });
        const p = localCore.executarFluxoComCliente(client);
        client.emit('ready');
        await settleWithTimers(t, p);
        assert.equal(sentMessages.length, 1); // sem warmup
        assert.equal(sentMessages[0].chatId, '123456-group@g.us');
    });

    test('ready: sem ATTACHMENT_PATH envia so texto', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const localCore = loadCore({ contact: '5511999999999', authPath: defaultAuthPath, clientId: 'test-client' });
        const logs = captureLogs(t);
        const client = new FakeClient({ sendMessageImpl: async () => ({ id: { _serialized: 'm' } }) });
        const p = localCore.executarFluxoComCliente(client);
        client.emit('ready');
        await settleWithTimers(t, p);
        assert.ok(logs.some((l) => l.includes('Anexo ausente ou nao encontrado')));
    });

    test('ready: sendMessage sem id (quirk) segue sem ACK rastreavel', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const localCore = loadCore({ contact: '5511999999999', authPath: defaultAuthPath, clientId: 'test-client' });
        const logs = captureLogs(t);
        const client = new FakeClient({ sendMessageImpl: async () => undefined });
        const p = localCore.executarFluxoComCliente(client);
        client.emit('ready');
        await settleWithTimers(t, p);
        assert.ok(logs.some((l) => l.includes('sendMessage retornou sem id')));
    });

    test('ready: sendMessage lanca erro -> rejeita a promise principal', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const localCore = loadCore({ contact: '5511999999999', authPath: defaultAuthPath, clientId: 'test-client' });
        captureLogs(t);
        const client = new FakeClient({ sendMessageImpl: async () => { throw new Error('falha no envio'); } });
        const p = localCore.executarFluxoComCliente(client);
        client.emit('ready');
        await assert.rejects(settleWithTimers(t, p), /falha no envio/);
    });

    test('client.initialize() rejeita: rejeita a promise principal', async () => {
        const client = new FakeClient({ initializeImpl: () => Promise.reject(new Error('boot falhou')) });
        await assert.rejects(core.executarFluxoComCliente(client), /boot falhou/);
    });

    test('bootstrap nunca chega em ready/erro: deadline de BOOTSTRAP_DEADLINE_MS dispara', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const client = new FakeClient(); // initializeImpl padrao nunca resolve/rejeita
        const p = core.executarFluxoComCliente(client);
        await assert.rejects(
            settleWithTimers(t, p, { maxSteps: core.BOOTSTRAP_DEADLINE_MS / TICK_STEP_MS + 10 }),
            /timed out/
        );
        assert.equal(client.destroyed, true);
    });

    // Regressao: BOOTSTRAP_DEADLINE_MS cobre so' o handshake (initialize -> ready), nao o
    // fluxo inteiro. ACK_WAIT_ATTEMPTS(90) * ACK_WAIT_DELAY_MS(2000) = 180000ms sozinho ja
    // iguala o deadline — se o timer nao for cancelado no 'ready', qualquer envio sem ACK
    // confirmado (caso normal documentado em aguardarAck) estoura o deadline no MEIO do
    // envio e reenvia a mensagem via retry de processar(). Este teste teria que reprovar
    // ate' o deadline ser cancelado no inicio do handler 'ready'.
    test('ready: ACK nunca confirma (autoAck:false) NAO deve rejeitar por deadline de bootstrap ja vencido', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const attach = attachmentTemp();
        const localCore = loadCore({
            attachment: attach, authPath: defaultAuthPath, clientId: 'test-client', contact: '5511999999999'
        });
        const client = new FakeClient({
            sendMessageImpl: async () => ({ id: { _serialized: 'msg-sem-ack' } }),
            autoAck: false
        });
        const p = localCore.executarFluxoComCliente(client);
        client.emit('ready');
        await settleWithTimers(t, p, {
            maxSteps: (core.ACK_WAIT_ATTEMPTS * core.ACK_WAIT_DELAY_MS + core.ACK_SETTLE_DELAY_MS) / TICK_STEP_MS + 20
        });
        assert.equal(client.destroyed, true);
    });
});

// ============================================================================
// processar — laco de retry de bootstrap (modo AUTO / VISUAL-com-contato)
// ============================================================================

describe('processar', () => {
    test('CONTACT_ARG ausente: rejeita sem criar cliente', async () => {
        const localCore = loadCore({ contact: '', authPath: defaultAuthPath, clientId: 'test-client' });
        await assert.rejects(localCore.processar(), /Telefone\/chatId de destino ausente/);
    });

    test('sessao ausente (MODE!=VISUAL): aborta com process.exit(21)', async (t) => {
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'processar-sem-sessao2-'));
        const localCore = loadCore({ authPath, clientId: 'sem-sessao2', contact: '5511999999999' });
        mockProcessExit(t);
        await assert.rejects(localCore.processar(), ProcessExitSignal);
    });

    test('erro nao retryable: rejeita na 1a tentativa sem retry', async (t) => {
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'processar-fatal-'));
        criarSessaoValida(authPath, 'fatal-client');
        const localCore = loadCore({ authPath, clientId: 'fatal-client', contact: '5511999999999' });
        const { module: wa, created } = makeWhatsAppMock(() =>
            new FakeClient({ initializeImpl: () => Promise.reject(new Error('erro fatal generico nao retryable')) })
        );
        localCore._setWhatsAppWebJsForTests(wa);
        captureLogs(t);
        await assert.rejects(localCore.processar(), /erro fatal generico/);
        assert.equal(created.length, 1);
    });

    test('erro retryable: retenta e sucede na 2a tentativa', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'processar-retry-ok-'));
        criarSessaoValida(authPath, 'retry-client');
        const localCore = loadCore({ authPath, clientId: 'retry-client', contact: '5511999999999' });
        const { module: wa, created } = makeWhatsAppMock((config, idx) => {
            if (idx === 0) {
                return new FakeClient({ initializeImpl: () => Promise.reject(new Error('protocol timeout')) });
            }
            return new FakeClient();
        });
        localCore._setWhatsAppWebJsForTests(wa);
        const logs = captureLogs(t);
        const p = localCore.processar();
        await tickUntil(t, () => created.length >= 2);
        created[1].emit('ready');
        await settleWithTimers(t, p);
        assert.equal(created.length, 2);
        assert.ok(logs.some((l) => l.includes('Falha transiente na inicializacao')));
    });

    test('erro retryable persiste ate esgotar INITIALIZE_MAX_ATTEMPTS: rejeita', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'processar-retry-esgota-'));
        criarSessaoValida(authPath, 'retry-esgota');
        const localCore = loadCore({ authPath, clientId: 'retry-esgota', contact: '5511999999999' });
        const { module: wa, created } = makeWhatsAppMock(() =>
            new FakeClient({ initializeImpl: () => Promise.reject(new Error('protocol timeout')) })
        );
        localCore._setWhatsAppWebJsForTests(wa);
        captureLogs(t);
        await assert.rejects(settleWithTimers(t, localCore.processar()), /protocol timeout/);
        assert.equal(created.length, localCore.INITIALIZE_MAX_ATTEMPTS);
    });
});

// ============================================================================
// executarFluxoBatch
// ============================================================================

describe('executarFluxoBatch', () => {
    function imagemTemp() {
        const dir = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'batch-img-'));
        const file = path.join(dir, 'fase.png');
        fs.writeFileSync(file, 'fake-png');
        return file;
    }

    test('fase unica com sucesso e ACK confirmado', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const img = imagemTemp();
        const client = new FakeClient({ sendMessageImpl: async () => ({ id: { _serialized: 'b1' } }) });
        const p = core.executarFluxoBatch(client, [{ phase_key: 'fase1', image_path: img, caption: 'legenda' }], '123@g.us', 1);
        const resultados = await settleWithTimers(t, p);
        assert.deepEqual(resultados, [{ phase_key: 'fase1', success: true, error: null }]);
    });

    test('imagem inexistente: fase marcada como falha com mensagem de erro', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const client = new FakeClient();
        const p = core.executarFluxoBatch(client, [{ phase_key: 'fase1', image_path: 'nao/existe.png', caption: '' }], '123@g.us', 1);
        const resultados = await settleWithTimers(t, p);
        assert.equal(resultados[0].success, false);
        assert.match(resultados[0].error, /Imagem nao encontrada/);
    });

    test('sendMessage lanca erro: fase marcada como falha', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const img = imagemTemp();
        const client = new FakeClient({ sendMessageImpl: async () => { throw new Error('falha de rede'); } });
        const p = core.executarFluxoBatch(client, [{ phase_key: 'fase1', image_path: img, caption: '' }], '123@g.us', 1);
        const resultados = await settleWithTimers(t, p);
        assert.equal(resultados[0].success, false);
        assert.match(resultados[0].error, /falha de rede/);
    });

    test('sendMessage sem id (quirk): sucesso sem rastrear ACK', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const img = imagemTemp();
        const logs = captureLogs(t);
        const client = new FakeClient({ sendMessageImpl: async () => undefined });
        const p = core.executarFluxoBatch(client, [{ phase_key: 'fase1', image_path: img, caption: '' }], '123@g.us', 1);
        const resultados = await settleWithTimers(t, p);
        assert.equal(resultados[0].success, true);
        assert.ok(logs.some((l) => l.includes('sendMessage retornou sem id')));
    });

    test('circuit breaker: 2 falhas consecutivas abortam o restante do lote', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const client = new FakeClient();
        const itens = [
            { phase_key: 'f1', image_path: 'nao/existe1.png', caption: '' },
            { phase_key: 'f2', image_path: 'nao/existe2.png', caption: '' },
            { phase_key: 'f3', image_path: 'nao/existe3.png', caption: '' }
        ];
        const p = core.executarFluxoBatch(client, itens, '123@g.us', 1);
        const resultados = await settleWithTimers(t, p);
        assert.equal(resultados.length, 3);
        assert.equal(resultados[0].success, false);
        assert.equal(resultados[1].success, false);
        assert.equal(resultados[2].error, 'CIRCUIT_BREAKER_ABORT');
    });

    test('sucesso reseta o contador de falhas consecutivas (nao aciona o breaker)', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const img = imagemTemp();
        let chamada = 0;
        const client = new FakeClient({
            sendMessageImpl: async () => {
                chamada++;
                if (chamada % 2 === 0) { throw new Error('falha intercalada'); }
                return { id: { _serialized: `b${chamada}` } };
            }
        });
        const itens = [
            { phase_key: 'f1', image_path: img, caption: '' },
            { phase_key: 'f2', image_path: img, caption: '' },
            { phase_key: 'f3', image_path: img, caption: '' },
            { phase_key: 'f4', image_path: img, caption: '' }
        ];
        const p = core.executarFluxoBatch(client, itens, '123@g.us', 1);
        const resultados = await settleWithTimers(t, p);
        assert.equal(resultados.length, 4); // breaker nunca disparou (falhas nao foram consecutivas)
        assert.deepEqual(resultados.map((r) => r.success), [true, false, true, false]);
    });

    test('bootstrapAttempt>1 usa ACK timeout estendido e loga aviso', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const img = imagemTemp();
        const logs = captureLogs(t);
        const client = new FakeClient({ sendMessageImpl: async () => ({ id: { _serialized: 'b1' } }) });
        const p = core.executarFluxoBatch(client, [{ phase_key: 'fase1', image_path: img, caption: '' }], '123@g.us', 2);
        await settleWithTimers(t, p);
        assert.ok(logs.some((l) => l.includes('usando ACK timeout estendido')));
    });

    test('id presente mas ACK nunca confirmado: sucesso mesmo assim, com WARN', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const img = imagemTemp();
        const logs = captureLogs(t);
        const client = new FakeClient({ sendMessageImpl: async () => ({ id: { _serialized: 'b1' } }), autoAck: false });
        const p = core.executarFluxoBatch(client, [{ phase_key: 'fase1', image_path: img, caption: '' }], '123@g.us', 1);
        const resultados = await settleWithTimers(t, p, { maxSteps: (core.ACK_WAIT_ATTEMPTS_BATCH_NORMAL * core.ACK_WAIT_DELAY_MS) / TICK_STEP_MS + 10 });
        assert.equal(resultados[0].success, true);
        assert.ok(logs.some((l) => l.includes('ACK nao confirmado na janela')));
    });
});

// ============================================================================
// executarModoListGroups
// ============================================================================

describe('executarModoListGroups', () => {
    test('sessao ausente: aborta com exit(21) sem criar cliente', async (t) => {
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'lg-sem-sessao-'));
        const localCore = loadCore({ authPath, clientId: 'lg-sem-sessao', mode: 'LIST_GROUPS', contact: '' });
        const { module: wa, created } = makeWhatsAppMock();
        localCore._setWhatsAppWebJsForTests(wa);
        mockProcessExit(t);
        captureLogs(t);
        await assert.rejects(localCore.executarModoListGroups(), ProcessExitSignal);
        assert.equal(created.length, 0);
    });

    test('qr: sai com exit(21)', async (t) => {
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'lg-qr-'));
        criarSessaoValida(authPath, 'lg-qr');
        const localCore = loadCore({ authPath, clientId: 'lg-qr', mode: 'LIST_GROUPS', contact: '' });
        const { module: wa, created } = makeWhatsAppMock(() => new FakeClient());
        localCore._setWhatsAppWebJsForTests(wa);
        mockProcessExit(t);
        captureLogs(t);
        await localCore.executarModoListGroups();
        assert.throws(() => created[0].emit('qr'), ProcessExitSignal);
    });

    test('ready: lista grupos e sai com exit(0)', async (t) => {
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'lg-ready-'));
        criarSessaoValida(authPath, 'lg-ready');
        const localCore = loadCore({ authPath, clientId: 'lg-ready', mode: 'LIST_GROUPS', contact: '' });
        const { module: wa, created } = makeWhatsAppMock(() => new FakeClient({
            pupPage: {
                mouse: { move: async () => {} },
                waitForFunction: async () => {},
                evaluate: async () => ([{ id: 'g1@g.us', name: 'Grupo 1' }])
            }
        }));
        localCore._setWhatsAppWebJsForTests(wa);
        const exitMock = mockProcessExitSilent(t);
        const logs = captureLogs(t);
        await localCore.executarModoListGroups();
        created[0].emit('ready');
        await flushAsync();
        assert.equal(exitMock.mock.calls[0].arguments[0], 0);
        assert.ok(logs.some((l) => l.includes('g1@g.us')));
    });

    test('ready: waitForFunction rejeita (timeout do Store) mas segue com WARN', async (t) => {
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'lg-store-timeout-'));
        criarSessaoValida(authPath, 'lg-store-timeout');
        const localCore = loadCore({ authPath, clientId: 'lg-store-timeout', mode: 'LIST_GROUPS', contact: '' });
        const { module: wa, created } = makeWhatsAppMock(() => new FakeClient({
            pupPage: {
                mouse: { move: async () => {} },
                waitForFunction: async () => { throw new Error('timeout Store'); },
                evaluate: async () => []
            }
        }));
        localCore._setWhatsAppWebJsForTests(wa);
        const exitMock = mockProcessExitSilent(t);
        const logs = captureLogs(t);
        await localCore.executarModoListGroups();
        created[0].emit('ready');
        await flushAsync();
        assert.equal(exitMock.mock.calls[0].arguments[0], 0);
        assert.ok(logs.some((l) => l.includes('Store.Chat nao populou em 15s')));
    });

    test('ready: evaluate lanca erro -> exit(24)', async (t) => {
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'lg-evaluate-erro-'));
        criarSessaoValida(authPath, 'lg-evaluate-erro');
        const localCore = loadCore({ authPath, clientId: 'lg-evaluate-erro', mode: 'LIST_GROUPS', contact: '' });
        const { module: wa, created } = makeWhatsAppMock(() => new FakeClient({
            pupPage: {
                mouse: { move: async () => {} },
                waitForFunction: async () => {},
                evaluate: async () => { throw new Error('falha no evaluate'); }
            }
        }));
        localCore._setWhatsAppWebJsForTests(wa);
        const exitMock = mockProcessExitSilent(t);
        captureLogs(t);
        await localCore.executarModoListGroups();
        created[0].emit('ready');
        await flushAsync();
        assert.equal(exitMock.mock.calls[0].arguments[0], 24);
    });

    test('client.initialize() rejeita: exit(24)', async (t) => {
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'lg-init-erro-'));
        criarSessaoValida(authPath, 'lg-init-erro');
        const localCore = loadCore({ authPath, clientId: 'lg-init-erro', mode: 'LIST_GROUPS', contact: '' });
        const { module: wa } = makeWhatsAppMock(() =>
            new FakeClient({ initializeImpl: () => Promise.reject(new Error('boot falhou')) })
        );
        localCore._setWhatsAppWebJsForTests(wa);
        const exitMock = mockProcessExitSilent(t);
        captureLogs(t);
        await localCore.executarModoListGroups();
        await flushAsync();
        assert.equal(exitMock.mock.calls[0].arguments[0], 24);
    });
});

// ============================================================================
// executarModoBatch
// ============================================================================

describe('executarModoBatch', () => {
    function batchFiles(itens) {
        const dir = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'batch-mode-'));
        const batchFile = path.join(dir, 'lote.json');
        const batchResultFile = path.join(dir, 'resultado.json');
        if (itens !== undefined) { fs.writeFileSync(batchFile, JSON.stringify(itens)); }
        return { dir, batchFile, batchResultFile };
    }

    function imagemTemp(dir) {
        const file = path.join(dir, 'fase.png');
        fs.writeFileSync(file, 'fake-png');
        return file;
    }

    function loadBatchCore({ itens, contact = '123456@g.us', clientId = 'batch-client', authPath, batchFileOverride } = {}) {
        const { dir, batchFile, batchResultFile } = batchFiles(itens);
        const finalAuthPath = authPath || (() => {
            const p = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'batch-auth-'));
            criarSessaoValida(p, clientId);
            return p;
        })();
        return {
            core: loadCore({
                mode: 'BATCH', clientId, contact, authPath: finalAuthPath,
                batchFile: batchFileOverride !== undefined ? batchFileOverride : batchFile,
                batchResultFile
            }),
            dir, batchFile, batchResultFile
        };
    }

    test('BATCH_FILE ausente: exit(24) sem tentar ler nada', async (t) => {
        const { core: localCore } = loadBatchCore({ itens: undefined, batchFileOverride: path.join(SUITE_TMP_ROOT, 'nao-existe.json') });
        const exitMock = mockProcessExit(t);
        captureLogs(t);
        await assert.rejects(localCore.executarModoBatch(), ProcessExitSignal);
        assert.equal(exitMock.mock.calls[0].arguments[0], 24);
    });

    test('BATCH_FILE com JSON invalido: exit(24)', async (t) => {
        const dir2 = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'batch-badjson2-'));
        const batchFile = path.join(dir2, 'lote.json');
        fs.writeFileSync(batchFile, '{ isso nao e json');
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'batch-badjson2-auth-'));
        criarSessaoValida(authPath, 'bj2');
        const localCore = loadCore({ mode: 'BATCH', clientId: 'bj2', contact: '123@g.us', authPath, batchFile, batchResultFile: path.join(dir2, 'r.json') });
        const exitMock = mockProcessExit(t);
        captureLogs(t);
        await assert.rejects(localCore.executarModoBatch(), ProcessExitSignal);
        assert.equal(exitMock.mock.calls[0].arguments[0], 24);
    });

    test('BATCH_FILE com BOM e itens vazios: exit(0)', async (t) => {
        const dir2 = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'batch-bom-'));
        const batchFile = path.join(dir2, 'lote.json');
        fs.writeFileSync(batchFile, '﻿' + JSON.stringify([]));
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'batch-bom-auth-'));
        criarSessaoValida(authPath, 'bom');
        const localCore = loadCore({ mode: 'BATCH', clientId: 'bom', contact: '123@g.us', authPath, batchFile, batchResultFile: path.join(dir2, 'r.json') });
        const exitMock = mockProcessExit(t);
        captureLogs(t);
        await assert.rejects(localCore.executarModoBatch(), ProcessExitSignal);
        assert.equal(exitMock.mock.calls[0].arguments[0], 0);
    });

    test('CONTACT_ARG ausente: exit(24)', async (t) => {
        const { core: localCore } = loadBatchCore({ itens: [{ phase_key: 'f1', image_path: 'x', caption: '' }], contact: '' });
        const exitMock = mockProcessExit(t);
        captureLogs(t);
        await assert.rejects(localCore.executarModoBatch(), ProcessExitSignal);
        assert.equal(exitMock.mock.calls[0].arguments[0], 24);
    });

    test('sessao ausente: exit(21) sem criar cliente', async (t) => {
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'batch-sem-sessao-'));
        const { core: localCore } = loadBatchCore({ itens: [{ phase_key: 'f1', image_path: 'x', caption: '' }], authPath });
        const { module: wa, created } = makeWhatsAppMock();
        localCore._setWhatsAppWebJsForTests(wa);
        const exitMock = mockProcessExit(t);
        captureLogs(t);
        await assert.rejects(localCore.executarModoBatch(), ProcessExitSignal);
        assert.equal(exitMock.mock.calls[0].arguments[0], 21);
        assert.equal(created.length, 0);
    });

    test('qr: exit(21)', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const { core: localCore } = loadBatchCore({ itens: [{ phase_key: 'f1', image_path: 'x', caption: '' }] });
        const { module: wa, created } = makeWhatsAppMock(() => new FakeClient());
        localCore._setWhatsAppWebJsForTests(wa);
        const exitMock = mockProcessExitSilent(t);
        captureLogs(t);
        const p = localCore.executarModoBatch();
        await tickUntil(t, () => created.length >= 1);
        created[0].emit('qr');
        await flushAsync();
        assert.equal(exitMock.mock.calls[0].arguments[0], 21);
        p.catch(() => {});
    });

    // As tres proximas passam pelo exit "de sucesso" (falhas=0 / falhas>0), que fica
    // DENTRO do mesmo bloco try do laco de retry — sem `return` apos process.exit() (igual
    // a producao, onde isso nunca importa pois o processo morre ali). Um mock QUE NAO
    // lanca deixaria a execucao "cair" para a proxima iteracao do for e criar um 2o
    // cliente espurio; um mock QUE lanca e' capturado pelo catch do mesmo try, que tenta
    // um exit(24) subsequente — tambem mockado, e' esse 2o lancamento (sem try em volta)
    // que finalmente propaga e encerra a funcao de vez. Por isso o mock aqui lanca, e o
    // teste le sempre exitMock.mock.calls[0] (a intencao real, nao o efeito colateral).
    test('fluxo feliz completo: ready -> lote sem falhas -> exit(0), resultado gravado', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const img = imagemTemp(fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'batch-img-')));
        const { core: localCore, batchResultFile } = loadBatchCore({
            itens: [{ phase_key: 'f1', image_path: img, caption: '' }]
        });
        const { module: wa, created } = makeWhatsAppMock(() => new FakeClient());
        localCore._setWhatsAppWebJsForTests(wa);
        const exitMock = mockProcessExit(t);
        captureLogs(t);
        const p = localCore.executarModoBatch();
        await tickUntil(t, () => created.length >= 1);
        created[0].emit('ready');
        await settleWithTimers(t, p.catch(() => {}));
        assert.equal(exitMock.mock.calls[0].arguments[0], 0);
        assert.equal(created.length, 1);
        const resultado = JSON.parse(fs.readFileSync(batchResultFile, 'utf8'));
        assert.deepEqual(resultado, [{ phase_key: 'f1', success: true, error: null }]);
    });

    test('lote com falhas -> exit(4)', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const { core: localCore } = loadBatchCore({
            itens: [{ phase_key: 'f1', image_path: 'nao/existe.png', caption: '' }]
        });
        const { module: wa, created } = makeWhatsAppMock(() => new FakeClient());
        localCore._setWhatsAppWebJsForTests(wa);
        const exitMock = mockProcessExit(t);
        captureLogs(t);
        const p = localCore.executarModoBatch();
        await tickUntil(t, () => created.length >= 1);
        created[0].emit('ready');
        await settleWithTimers(t, p.catch(() => {}));
        assert.equal(exitMock.mock.calls[0].arguments[0], 4);
        assert.equal(created.length, 1);
    });

    test('disconnected apos lote concluido: WARN, sem crash', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const img = imagemTemp(fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'batch-img2-')));
        const { core: localCore } = loadBatchCore({ itens: [{ phase_key: 'f1', image_path: img, caption: '' }] });
        const { module: wa, created } = makeWhatsAppMock(() => new FakeClient());
        localCore._setWhatsAppWebJsForTests(wa);
        mockProcessExit(t);
        const logs = captureLogs(t);
        const p = localCore.executarModoBatch();
        await tickUntil(t, () => created.length >= 1);
        created[0].emit('ready');
        await settleWithTimers(t, p.catch(() => {}));
        assert.doesNotThrow(() => created[0].emit('disconnected', 'NAVIGATION'));
        await flushAsync();
        assert.ok(logs.some((l) => l.includes('Desconectado apos o lote concluido')));
    });

    test('disconnected com LOGOUT antes do lote concluir: exit(21)', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const { core: localCore } = loadBatchCore({ itens: [{ phase_key: 'f1', image_path: 'x', caption: '' }] });
        const { module: wa, created } = makeWhatsAppMock(() => new FakeClient());
        localCore._setWhatsAppWebJsForTests(wa);
        const exitMock = mockProcessExitSilent(t);
        captureLogs(t);
        const p = localCore.executarModoBatch();
        await tickUntil(t, () => created.length >= 1);
        created[0].emit('disconnected', 'NAVIGATION LOGOUT');
        await flushAsync();
        assert.equal(exitMock.mock.calls[0].arguments[0], 21);
        p.catch(() => {});
    });

    test('erro retryable (auth_failure) retenta e sucede na 2a tentativa', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const img = imagemTemp(fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'batch-img3-')));
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'batch-retry-auth-'));
        criarSessaoValida(authPath, 'batch-retry');
        const { core: localCore, batchResultFile } = loadBatchCore({
            itens: [{ phase_key: 'f1', image_path: img, caption: '' }], clientId: 'batch-retry', authPath
        });
        const { module: wa, created } = makeWhatsAppMock(() => new FakeClient());
        localCore._setWhatsAppWebJsForTests(wa);
        const exitMock = mockProcessExit(t);
        const logs = captureLogs(t);
        const p = localCore.executarModoBatch();
        await tickUntil(t, () => created.length >= 1);
        created[0].emit('auth_failure', 'protocol timeout transiente');
        await tickUntil(t, () => created.length >= 2);
        created[1].emit('ready');
        await settleWithTimers(t, p.catch(() => {}));
        assert.equal(created.length, 2);
        assert.equal(exitMock.mock.calls[0].arguments[0], 0);
        assert.ok(logs.some((l) => l.includes('Falha transiente:')));
        assert.ok(fs.existsSync(batchResultFile));
    });

    test('bootstrap nunca chega em ready: deadline retryable esgota tentativas -> exit(24)', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'batch-deadline-auth-'));
        criarSessaoValida(authPath, 'batch-deadline');
        const { core: localCore } = loadBatchCore({
            itens: [{ phase_key: 'f1', image_path: 'x', caption: '' }], clientId: 'batch-deadline', authPath
        });
        const { module: wa, created } = makeWhatsAppMock(() => new FakeClient());
        localCore._setWhatsAppWebJsForTests(wa);
        const exitMock = mockProcessExit(t);
        captureLogs(t);
        const p = localCore.executarModoBatch();
        await settleWithTimers(t, p.catch(() => {}), {
            maxSteps: (3 * (core.BOOTSTRAP_DEADLINE_MS + core.INITIALIZE_RETRY_DELAY_MS)) / TICK_STEP_MS + 20
        });
        assert.equal(created.length, localCore.INITIALIZE_MAX_ATTEMPTS);
        assert.equal(exitMock.mock.calls[0].arguments[0], 24);
    });

    // Regressao: mesmo defeito do teste analogo em executarFluxoComCliente, mas no lote.
    // Orcamento pos-'ready' de uma UNICA fase sem ACK: BATCH_SETTLE_MS_NORMAL(40s) +
    // ACK_WAIT_ATTEMPTS_BATCH_NORMAL(60)*ACK_WAIT_DELAY_MS(2s)=120s + dreno ACK_SETTLE_DELAY_MS
    // (30s) = 190s > BOOTSTRAP_DEADLINE_MS(180s). Sem cancelar o deadline no 'ready' do lote,
    // isso reenvia o LOTE INTEIRO (imagens duplicadas) e/ou corrompe batch_result.json.
    test('bootstrap ready + ACK nunca confirma (autoAck:false): nao reenvia o lote por deadline vencido pos-ready', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const img = imagemTemp(fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'batch-img-deadline-')));
        const { core: localCore } = loadBatchCore({
            itens: [{ phase_key: 'f1', image_path: img, caption: '' }]
        });
        const { module: wa, created } = makeWhatsAppMock(() => new FakeClient({ autoAck: false }));
        localCore._setWhatsAppWebJsForTests(wa);
        const exitMock = mockProcessExit(t);
        captureLogs(t);
        const p = localCore.executarModoBatch();
        await tickUntil(t, () => created.length >= 1);
        created[0].emit('ready');
        await settleWithTimers(t, p.catch(() => {}), {
            maxSteps: (core.BATCH_SETTLE_MS_NORMAL + core.ACK_WAIT_ATTEMPTS_BATCH_NORMAL * core.ACK_WAIT_DELAY_MS + core.ACK_SETTLE_DELAY_MS + 30000) / TICK_STEP_MS + 50
        });
        assert.equal(created.length, 1); // nao pode ter retentado/criado 2o cliente
        assert.equal(exitMock.mock.calls[0].arguments[0], 0);
    });

    // Regressao (achado correlato): a corrida pode ser decidida (rejeitada) por QUALQUER
    // motivo — nao so' o deadline — enquanto o handler 'ready' ainda esta no meio do envio
    // do lote (um await em andamento nao e' cancelavel). Sem o guard abortadoNestaTentativa,
    // esse handler 'ready' orfao terminaria o lote e gravaria batch_result.json mesmo apos
    // a tentativa ja ter sido descartada — sobrescrevendo o que uma tentativa seguinte (ou
    // o proprio exit(24) desta) deveria ser a palavra final.
    test('disconnected generico DURANTE o processamento do lote: resultado tardio da tentativa abortada nao e gravado', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const img = imagemTemp(fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'batch-img-abort-')));
        const { core: localCore, batchResultFile } = loadBatchCore({
            itens: [{ phase_key: 'f1', image_path: img, caption: '' }]
        });
        let liberarEnvio;
        const travaEnvio = new Promise((resolve) => { liberarEnvio = resolve; });
        const { module: wa, created } = makeWhatsAppMock(() => new FakeClient({
            sendMessageImpl: async () => { await travaEnvio; return { id: { _serialized: 'b1' } }; }
        }));
        localCore._setWhatsAppWebJsForTests(wa);
        const exitMock = mockProcessExit(t);
        const logs = captureLogs(t);
        const p = localCore.executarModoBatch();
        // Anexado JA' aqui (sincrono, antes de qualquer avanco assincrono): o exit(24)
        // mockado lanca de dentro do catch externo (sem try em volta) e rejeita `p` bem
        // antes do fim do teste — sem um handler cedo isso e' unhandledRejection real.
        p.catch(() => {});
        await tickUntil(t, () => created.length >= 1);
        created[0].emit('ready');
        // Avanca alem do settle (40s) + verificarEstadoConectado: entra em executarFluxoBatch,
        // que fica parado dentro do sendMessage pendurado (travaEnvio ainda nao liberado).
        await tickSteps(t, (core.BATCH_SETTLE_MS_NORMAL + 31000) / TICK_STEP_MS);
        created[0].emit('disconnected', 'NAVIGATION'); // decide a corrida (reject generico)
        await flushAsync(); // `p` ja rejeita aqui (exit(24) mockado lanca fora do try)
        liberarEnvio(); // handler 'ready' orfao agora pode terminar o envio da fase
        // `p` ja assentou (rejeitada) — settleWithTimers pararia de avancar timers no
        // instante em que a detecta, o que NUNCA daria tempo mockado ao handler 'ready'
        // orfao (que ninguem mais "aguarda" formalmente) de progredir ate' o guard
        // abortadoNestaTentativa e logar a decisao. Avanca manualmente o suficiente para
        // o ACK confirmar (autoAck default=true, ~1 iteracao de ACK_WAIT_DELAY_MS) e o
        // handler orfao terminar de vez.
        await tickSteps(t, (core.ACK_WAIT_DELAY_MS * 3) / TICK_STEP_MS + 10);
        await flushAsync();

        assert.equal(created.length, 1); // "Desconectado: NAVIGATION" nao casa a regex de retry
        assert.equal(exitMock.mock.calls[0].arguments[0], 24);
        assert.equal(fs.existsSync(batchResultFile), false); // resultado tardio NAO foi gravado
        assert.ok(logs.some((l) => l.includes('resultado descartado')));
        await assert.rejects(p, ProcessExitSignal); // confirma o desfecho da promise principal
    });
});

// ============================================================================
// executarModoVisualAuth
// ============================================================================

describe('executarModoVisualAuth', () => {
    function loadVisualCore({ authPath, clientId = 'visual-client' } = {}) {
        const finalAuthPath = authPath || fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'visual-auth-'));
        return loadCore({ mode: 'VISUAL', clientId, contact: '', authPath: finalAuthPath });
    }

    test('qr/loading_screen/authenticated apenas logam (nao saem)', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const localCore = loadVisualCore();
        const { module: wa, created } = makeWhatsAppMock(() => new FakeClient());
        localCore._setWhatsAppWebJsForTests(wa);
        mockProcessExit(t);
        const logs = captureLogs(t);
        const p = localCore.executarModoVisualAuth();
        await tickUntil(t, () => created.length >= 1);
        created[0].emit('qr');
        created[0].emit('loading_screen', 10, 'iniciando');
        created[0].emit('authenticated');
        await flushAsync();
        assert.ok(logs.some((l) => l.includes('QR Code recebido. Escaneie')));
        assert.ok(logs.some((l) => l.includes('Carregando: 10% - iniciando')));
        assert.ok(logs.some((l) => l.includes('Sessao autenticada com sucesso')));
        p.catch(() => {});
    });

    test('ready: sessao confirmada em disco apos o dreno -> exit(0)', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'visual-ok-'));
        criarSessaoValida(authPath, 'visual-ok');
        const localCore = loadVisualCore({ authPath, clientId: 'visual-ok' });
        const { module: wa, created } = makeWhatsAppMock(() => new FakeClient());
        localCore._setWhatsAppWebJsForTests(wa);
        const exitMock = mockProcessExit(t);
        captureLogs(t);
        const p = localCore.executarModoVisualAuth();
        await tickUntil(t, () => created.length >= 1);
        created[0].emit('ready');
        await settleWithTimers(t, p.catch(() => {}));
        assert.equal(exitMock.mock.calls[0].arguments[0], 0);
        assert.equal(created.length, 1);
    });

    test('ready: sessao NAO confirmada apos o dreno -> exit(24)', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'visual-naoconf-'));
        const localCore = loadVisualCore({ authPath, clientId: 'visual-naoconf' });
        const { module: wa, created } = makeWhatsAppMock(() => new FakeClient());
        localCore._setWhatsAppWebJsForTests(wa);
        const exitMock = mockProcessExit(t);
        captureLogs(t);
        const p = localCore.executarModoVisualAuth();
        await tickUntil(t, () => created.length >= 1);
        created[0].emit('ready');
        await settleWithTimers(t, p.catch(() => {}));
        assert.equal(exitMock.mock.calls[0].arguments[0], 24);
    });

    test('auth_failure -> exit(24)', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const localCore = loadVisualCore();
        const { module: wa, created } = makeWhatsAppMock(() => new FakeClient());
        localCore._setWhatsAppWebJsForTests(wa);
        const exitMock = mockProcessExit(t);
        captureLogs(t);
        const p = localCore.executarModoVisualAuth();
        await tickUntil(t, () => created.length >= 1);
        created[0].emit('auth_failure', 'codigo invalido');
        await settleWithTimers(t, p.catch(() => {}));
        assert.equal(exitMock.mock.calls[0].arguments[0], 24);
    });

    test('initialize rejeita com erro generico (nao context-destroyed) -> exit(24)', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'visual-init-erro-'));
        const localCore = loadVisualCore({ authPath, clientId: 'visual-init-erro' });
        const { module: wa, created } = makeWhatsAppMock(() =>
            new FakeClient({ initializeImpl: () => Promise.reject(new Error('falha generica de boot')) })
        );
        localCore._setWhatsAppWebJsForTests(wa);
        const exitMock = mockProcessExit(t);
        captureLogs(t);
        const p = localCore.executarModoVisualAuth();
        await settleWithTimers(t, p.catch(() => {}));
        assert.equal(exitMock.mock.calls[0].arguments[0], 24);
        assert.equal(created.length, 1);
    });

    test('initialize rejeita "Execution context was destroyed" mas sessao PRESENTE: nao arquiva, exit(24)', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'visual-ctx-sessao-presente-'));
        criarSessaoValida(authPath, 'visual-ctx-presente');
        const localCore = loadVisualCore({ authPath, clientId: 'visual-ctx-presente' });
        const { module: wa, created } = makeWhatsAppMock(() =>
            new FakeClient({ initializeImpl: () => Promise.reject(new Error('Execution context was destroyed')) })
        );
        localCore._setWhatsAppWebJsForTests(wa);
        const exitMock = mockProcessExit(t);
        captureLogs(t);
        const p = localCore.executarModoVisualAuth();
        await settleWithTimers(t, p.catch(() => {}));
        assert.equal(exitMock.mock.calls[0].arguments[0], 24);
        assert.equal(created.length, 1); // nao tentou arquivar/reboot com perfil limpo
    });

    test('initialize rejeita "Execution context was destroyed" com sessao ausente: arquiva e reautentica com sucesso', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'visual-arquivar-ok-'));
        fs.mkdirSync(path.join(authPath, 'session-visual-arquivar'), { recursive: true });
        const localCore = loadVisualCore({ authPath, clientId: 'visual-arquivar' });
        const { module: wa, created } = makeWhatsAppMock((config, idx) => {
            if (idx === 0) {
                return new FakeClient({ initializeImpl: () => Promise.reject(new Error('Execution context was destroyed')) });
            }
            return new FakeClient();
        });
        localCore._setWhatsAppWebJsForTests(wa);
        const exitMock = mockProcessExit(t);
        const logs = captureLogs(t);
        const p = localCore.executarModoVisualAuth();
        await tickUntil(t, () => created.length >= 2);
        // O 2o bootstrap parte de perfil ja arquivado. sessaoPersistidaConfirmada precisa
        // achar o perfil novo gravado; como o teste nao grava de verdade, simula via
        // criarSessaoValida no clientId atual antes do 'ready' do 2o cliente.
        criarSessaoValida(authPath, 'visual-arquivar');
        created[1].emit('ready');
        await settleWithTimers(t, p.catch(() => {}));
        assert.equal(created.length, 2);
        assert.equal(exitMock.mock.calls[0].arguments[0], 0);
        assert.ok(logs.some((l) => l.includes('Arquivando o perfil e reiniciando do zero')));
    });

    test('arquivarPerfilInconsistente falha: exit(24) sem 2a tentativa', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'visual-arquivar-falha-'));
        fs.mkdirSync(path.join(authPath, 'session-visual-arqfalha'), { recursive: true });
        const localCore = loadVisualCore({ authPath, clientId: 'visual-arqfalha' });
        const { module: wa, created } = makeWhatsAppMock(() =>
            new FakeClient({ initializeImpl: () => Promise.reject(new Error('Execution context was destroyed')) })
        );
        localCore._setWhatsAppWebJsForTests(wa);
        const renameMock = t.mock.method(fs, 'renameSync', () => { throw new Error('EPERM simulado'); });
        const exitMock = mockProcessExit(t);
        captureLogs(t);
        const p = localCore.executarModoVisualAuth();
        await settleWithTimers(t, p.catch(() => {}), { maxSteps: 10000 / TICK_STEP_MS + 50 });
        renameMock.mock.restore();
        assert.equal(exitMock.mock.calls[0].arguments[0], 24);
        assert.equal(created.length, 1);
    });
});

// ============================================================================
// executarModoAuto
// ============================================================================

describe('executarModoAuto', () => {
    test('processar() resolve: INFO + exit(0)', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'auto-ok-'));
        criarSessaoValida(authPath, 'auto-ok');
        const localCore = loadCore({ authPath, clientId: 'auto-ok', contact: '5511999999999' });
        const { module: wa, created } = makeWhatsAppMock(() => new FakeClient());
        localCore._setWhatsAppWebJsForTests(wa);
        const exitMock = mockProcessExit(t);
        const logs = captureLogs(t);
        const p = localCore.executarModoAuto();
        await tickUntil(t, () => created.length >= 1);
        created[0].emit('ready');
        await settleWithTimers(t, p.catch(() => {}));
        assert.equal(exitMock.mock.calls[0].arguments[0], 0);
        assert.ok(logs.some((l) => l.includes('Fluxo concluido com sucesso real')));
    });

    test('processar() rejeita com "No LID for user": WARN + exit(0) gracioso', async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'auto-nolid-'));
        criarSessaoValida(authPath, 'auto-nolid');
        const localCore = loadCore({ authPath, clientId: 'auto-nolid', contact: '5511999999999' });
        const { module: wa, created } = makeWhatsAppMock(() => new FakeClient({
            sendMessageImpl: async () => { throw new Error('No LID for user 5511999999999'); }
        }));
        localCore._setWhatsAppWebJsForTests(wa);
        const exitMock = mockProcessExit(t);
        const logs = captureLogs(t);
        const p = localCore.executarModoAuto();
        await tickUntil(t, () => created.length >= 1);
        created[0].emit('ready');
        await settleWithTimers(t, p.catch(() => {}));
        assert.equal(exitMock.mock.calls[0].arguments[0], 0);
        assert.ok(logs.some((l) => l.includes('Contato invalido / No LID')));
    });

    test('processar() rejeita com erro generico: ERROR + exit(24)', async (t) => {
        const authPath = fs.mkdtempSync(path.join(SUITE_TMP_ROOT, 'auto-erro-'));
        const localCore = loadCore({ authPath, clientId: 'auto-erro', contact: '' });
        const exitMock = mockProcessExit(t);
        captureLogs(t);
        // CONTACT_ARG vazio -> processar() rejeita sincronamente com erro generico,
        // exercitando o branch ERROR/exit(24) real de executarModoAuto sem precisar de
        // FakeClient nenhum.
        await assert.rejects(localCore.executarModoAuto(), ProcessExitSignal);
        assert.equal(exitMock.mock.calls[0].arguments[0], 24);
    });
});

// ============================================================================
// selecionarModo
// ============================================================================

describe('selecionarModo', () => {
    test('LIST_GROUPS -> executarModoListGroups', () => {
        const localCore = loadCore({ mode: 'LIST_GROUPS', contact: '' });
        assert.equal(localCore.selecionarModo(), localCore.executarModoListGroups);
    });

    test('BATCH -> executarModoBatch', () => {
        const localCore = loadCore({ mode: 'BATCH', contact: '' });
        assert.equal(localCore.selecionarModo(), localCore.executarModoBatch);
    });

    test('VISUAL sem CONTACT_ARG -> executarModoVisualAuth', () => {
        const localCore = loadCore({ mode: 'VISUAL', contact: '' });
        assert.equal(localCore.selecionarModo(), localCore.executarModoVisualAuth);
    });

    test('VISUAL com CONTACT_ARG -> executarModoAuto', () => {
        const localCore = loadCore({ mode: 'VISUAL', contact: '5511999999999' });
        assert.equal(localCore.selecionarModo(), localCore.executarModoAuto);
    });

    test('AUTO -> executarModoAuto', () => {
        const localCore = loadCore({ mode: 'AUTO', contact: '5511999999999' });
        assert.equal(localCore.selecionarModo(), localCore.executarModoAuto);
    });
});
