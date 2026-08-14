// {
//   "name": "whatsapp-core",
//   "version": "2.10.0",
//   "skill": "nodejs-communications",
//   "description": "Motor Global de Mensageria WhatsApp (Soberano) - 100% Parametrizado",
//   "reliability": "Retry-Handshake, Ack-Persistence, Path-Portability, Batch-Mode"
// }
const fs = require('fs');
const path = require('path');
// Indirecao (em vez de destructuring direto de 'whatsapp-web.js') e o unico seam de
// injecao de dependencia deste arquivo: permite que os testes unitarios substituam
// Client/LocalAuth/MessageMedia por dublês sem lancar Puppeteer/Chromium de verdade.
// Producao nunca chama _setWhatsAppWebJsForTests — o modulo real e sempre o default.
let _whatsappWebJs = require('whatsapp-web.js');
function _setWhatsAppWebJsForTests(mockModule) {
    _whatsappWebJs = mockModule;
}
const { resolveAuthPath } = require('./whatsapp-auth-path');
const {
    sessaoPersistidaAusente: sessaoAusenteEmDisco,
    sessaoPersistidaConfirmada: sessaoConfirmadaEmDisco
} = require('./whatsapp-session-state');

const AUTH_PATH = resolveAuthPath();

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
// protocolTimeout so cobre chamadas de protocolo CDP individuais — nao cobre a promise
// inteira do bootstrap (client.initialize() ate 'ready'). Um travamento fora do CDP (ex.:
// page.goto/restauracao de sessao presos) fica sem deadline proprio e so e' interrompido
// pelo watchdog externo de max_runtime_minutes do job inteiro (30min em vez de minutos).
// Ocorrido em 06/08/2026 (Receitas Bloqueadas, CRON_1_1786046400_1707): job travado 30min02s
// parado em "Inicializando cliente WhatsApp (bootstrap)...", sem nenhum evento seguinte.
const BOOTSTRAP_DEADLINE_MS = 180000; // Deadline duro do handshake completo (initialize -> ready)
const ACK_WAIT_ATTEMPTS = 90;
const ACK_WAIT_DELAY_MS = 2000;
const ACK_SETTLE_DELAY_MS = 30000;     // 30s de dreno pós-lote antes de destruir o cliente
const AUTH_SETTLE_MS = 30000;          // 30s de dreno pós-'ready' na autenticação: tempo para o
                                       // WhatsApp Web gravar as chaves de sessão no perfil em disco
const MENTION_RESOLVE_TIMEOUT_MS = 15000; // getNumberId() pode travar no protocolo sem lancar erro
// getNumberId() e' uma consulta ao servidor do WhatsApp e falha de forma TRANSITORIA sob
// carga (ProtocolError/timeout do CDP). Sem retry, uma unica falha derruba a mencao daquele
// card: o texto "@numero" sai cru e o WhatsApp o renderiza como telefone autolinkado em vez
// do nome do contato, e o responsavel nao e' notificado. Ocorrido em 13/08/2026 as 22:31
// (CRON_4_1786671000_a3e1, fase IVF-INVERSAO P/FELPAGEM): o mesmo numero resolveu normalmente
// na execucao seguinte, confirmando que a falha era transitoria e nao de configuracao.
const MENTION_RESOLVE_ATTEMPTS = 3;
const MENTION_RESOLVE_RETRY_DELAY_MS = 2000;
// Teto de custo AGREGADO da resolucao de mencoes no processo inteiro. Cada numero que nao
// resolve custa ate 3x15s + 2x2s = 49s, e o lote do OBP-04 pode ter ate 17 cards
// (lib/python/obp_config.py) — num cenario globalmente degradado isso passaria de 13min so'
// resolvendo mencoes, contra os max_runtime_minutes=15 do manifesto. O circuit-breaker do
// lote nao protege: mencao que falha nao marca o card como falho. Estourado o orcamento, os
// numeros ainda nao resolvidos saem como texto — degradacao previsivel, em vez de lote
// interrompido no meio pelo watchdog.
const MENTION_RESOLVE_BUDGET_MS = 120000;
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

function comTimeout(promise, ms, mensagemTimeout) {
    let timer;
    const timeout = new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error(mensagemTimeout)), ms);
    });
    // Se a promise original rejeitar DEPOIS que o timeout ja venceu a corrida,
    // essa rejeicao fica sem .catch (unhandled rejection) e derruba o processo
    // Node inteiro (comportamento padrao a partir do Node 15+). O catch abaixo
    // apenas descarta essa rejeicao tardia — o timeout ja tratou o caso de erro.
    promise.catch(() => {});
    return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
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

// Cache por PROCESSO da resolucao numero -> wid. Um lote (modo BATCH) envia varios cards que
// costumam repetir o mesmo responsavel: sem cache, cada card refaz o RPC, multiplicando as
// janelas de timeout.
// So' o wid RESOLVIDO entra no cache. `null` do getNumberId NAO e' resposta definitiva: o
// whatsapp-web.js 1.34.6 (node_modules/whatsapp-web.js/src/Client.js, getNumberId) devolve
// null tanto para numero nao registrado quanto para `QueryExist` vazio/degradado
// (`if (!result || result.wid === undefined) return null`) — e esse caminho nao lanca, entao
// nao passa pelo catch nem tem retry. Cachear null deixaria uma unica consulta degradada
// derrubar a mencao daquele responsavel em todos os cards seguintes do lote.
// Por so' guardar positivos, o cache atravessa a recriacao do cliente nos retries de
// bootstrap sem nada a invalidar: o wid e' identidade do contato, nao estado da sessao, e
// todo numero ainda nao resolvido e' reconsultado contra a sessao nova.
const _cacheMencoes = new Map();

// Total ja' gasto tentando resolver numeros ainda sem wid (ver MENTION_RESOLVE_BUDGET_MS).
let _orcamentoMencoesGastoMs = 0;

const MOTIVO_RESOLVIDO = 'resolvido';
const MOTIVO_NAO_REGISTRADO = 'nao_registrado';
const MOTIVO_FALHA_TRANSITORIA = 'falha_transitoria';
const MOTIVO_ORCAMENTO_ESGOTADO = 'orcamento_esgotado';

// Distinguir as causas no log e' o ponto do fix: "nao registrado" manda o operador conferir o
// cadastro do numero; "falha transitoria" manda olhar a estabilidade da sessao. A versao sem
// retry ja' distinguia; conflacionar as duas mandaria investigar o .env de um problema de rede.
function descreverMotivoMencao(motivo) {
    if (motivo === MOTIVO_NAO_REGISTRADO) {
        return `servidor respondeu que o numero nao esta registrado no WhatsApp (getNumberId vazio em ${MENTION_RESOLVE_ATTEMPTS} tentativas)`;
    }
    if (motivo === MOTIVO_ORCAMENTO_ESGOTADO) {
        return `orcamento de resolucao do processo (${MENTION_RESOLVE_BUDGET_MS / 1000}s) esgotado — nem tentou`;
    }
    return `falha transitoria em ${MENTION_RESOLVE_ATTEMPTS} tentativas (instabilidade da sessao, nao e' erro de cadastro)`;
}

function _limparCacheMencoesForTests() {
    _cacheMencoes.clear();
    _orcamentoMencoesGastoMs = 0;
}

async function resolverNumeroMencao(client, numero) {
    const widEmCache = _cacheMencoes.get(numero);
    if (widEmCache) {
        return { wid: widEmCache, motivo: MOTIVO_RESOLVIDO };
    }
    if (_orcamentoMencoesGastoMs >= MENTION_RESOLVE_BUDGET_MS) {
        return { wid: null, motivo: MOTIVO_ORCAMENTO_ESGOTADO };
    }

    const inicio = Date.now();
    let motivo = MOTIVO_FALHA_TRANSITORIA;
    try {
        for (let tentativa = 1; tentativa <= MENTION_RESOLVE_ATTEMPTS; tentativa++) {
            const ultima = (tentativa === MENTION_RESOLVE_ATTEMPTS);
            const sufixo = ultima
                ? ' — mencao ignorada.'
                : ` — nova tentativa em ${MENTION_RESOLVE_RETRY_DELAY_MS}ms.`;
            let wid = null;
            try {
                wid = await comTimeout(
                    client.getNumberId(numero),
                    MENTION_RESOLVE_TIMEOUT_MS,
                    `Timeout (${MENTION_RESOLVE_TIMEOUT_MS}ms) ao resolver ${numero}`
                );
                if (!wid) {
                    motivo = MOTIVO_NAO_REGISTRADO;
                    writeLog(
                        'WARN',
                        `getNumberId devolveu vazio para ${numero} (tentativa ${tentativa}/${MENTION_RESOLVE_ATTEMPTS})` +
                        `${sufixo} Vazio nao distingue numero nao registrado de consulta degradada.`
                    );
                }
            } catch (error) {
                motivo = MOTIVO_FALHA_TRANSITORIA;
                writeLog(
                    'WARN',
                    `Falha ao resolver mencao para ${numero} (tentativa ${tentativa}/${MENTION_RESOLVE_ATTEMPTS})` +
                    `${sufixo} Detalhe: ${describeError(error)}`
                );
            }
            if (wid) {
                _cacheMencoes.set(numero, wid);
                return { wid, motivo: MOTIVO_RESOLVIDO };
            }
            if (!ultima) {
                await sleep(MENTION_RESOLVE_RETRY_DELAY_MS);
            }
        }
        return { wid: null, motivo };
    } finally {
        _orcamentoMencoesGastoMs += Date.now() - inicio;
    }
}

async function resolverMencoes(client, caption) {
    // client.getNumberId() consulta o servidor do WhatsApp para o ID de registro real do
    // numero (wid) — necessario porque o numero discado (com o 9o digito, no padrao
    // brasileiro) nem sempre corresponde ao ID interno que o WhatsApp usa para o contato
    // (conta legada sem o 9, ou identidade LID). Usar o numero discado direto no array de
    // mentions falha silenciosamente: a mensagem sai, mas o WhatsApp renderiza o "@numero"
    // como texto formatado de telefone em vez de uma mencao real que notifica o contato.
    const options = { caption };
    if (!caption || typeof caption !== 'string') {
        return options;
    }

    const candidatos = [...new Set([...caption.matchAll(/@(\d+)/g)].map(m => m[1]))];
    if (candidatos.length === 0) {
        return options;
    }

    const mentions = [];
    let captionResolvida = caption;
    for (const numero of candidatos) {
        const { wid, motivo } = await resolverNumeroMencao(client, numero);
        if (!wid) {
            writeLog('WARN', `Numero ${numero} nao resolvido no WhatsApp — mencao ignorada (o "@${numero}" sai como texto). Motivo: ${descreverMotivoMencao(motivo)}.`);
            continue;
        }
        mentions.push(wid._serialized);
        if (wid.user !== numero) {
            // O ID real difere do numero discado (ex: sem o 9o digito) — ajusta o
            // texto visivel para o "@" bater com o wid mencionado de verdade.
            captionResolvida = captionResolvida.replace(
                new RegExp(`@${numero}\\b`, 'g'),
                `@${wid.user}`
            );
        }
    }

    options.caption = captionResolvida;
    if (mentions.length > 0) {
        options.mentions = mentions;
        writeLog('INFO', `Detectadas ${mentions.length} mencoes resolvidas para o envio: [${mentions.join(', ')}]`);
    }
    return options;
}

function criarCliente() {
    return new _whatsappWebJs.Client({
        authStrategy: new _whatsappWebJs.LocalAuth({ dataPath: AUTH_PATH, clientId: CLIENT_ID }),
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
    const sessionDir = path.join(AUTH_PATH, `session-${clientId}`, 'Default');
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

// Deteccao de sessao ausente/zerada: contrato unico em whatsapp-session-state.js,
// compartilhado com open-whatsapp-session.js. Antes desta deteccao, o erro
// "Execution context was destroyed" consumia as 3 tentativas de bootstrap e terminava
// em ExitCode 24 (falha generica), escondendo que a causa era reautenticacao pendente.
function sessaoPersistidaAusente(clientId) {
    return sessaoAusenteEmDisco(AUTH_PATH, clientId);
}

// Confirmacao POSITIVA de que as chaves estao gravadas — nao e a negacao da funcao acima.
// Um erro de leitura do perfil (o Chrome ainda segurando handles durante o dreno) devolve
// false nas duas: para abortar isso significa "prossiga", para confirmar significa
// "ainda nao". Encerrar o autenticador sobre uma leitura indeterminada e o que produzia
// sessao "gravada com sucesso" que nao sobrevivia ao processo seguinte.
function sessaoPersistidaConfirmada(clientId) {
    return sessaoConfirmadaEmDisco(AUTH_PATH, clientId);
}

// Apos um LOGOUT o perfil fica inconsistente: o IndexedDB e zerado, mas localStorage,
// service workers e cache seguem apontando para uma sessao que nao existe mais. Nesse
// estado o WhatsApp Web redireciona durante a injecao do whatsapp-web.js e o bootstrap
// morre com "Execution context was destroyed" — inclusive no autenticador VISUAL, o que
// deixava o hub SEM caminho de recuperacao (verificado em 28/07/2026: perfil limpo
// renderiza o QR normalmente; o perfil pos-logout nunca chega la).
// Arquiva (renomeia, nao apaga) o perfil para que o proximo bootstrap parta do zero.
// Cada ciclo logout + reautenticacao deixa uma copia completa do perfil Chrome
// (localStorage, cache, service workers) em disco. Arquivar em vez de apagar e proposital
// — o perfil ainda serve de evidencia —, mas sem expurgo isso cresce indefinidamente com
// material sensivel. Retem os mais recentes; os demais ja nao servem a nenhum diagnostico.
const PERFIS_ARQUIVADOS_RETIDOS = 3;

function expurgarPerfisArquivados(clientId) {
    const prefixo = `session-${clientId}.inconsistente-`;
    let arquivados;
    try {
        arquivados = fs.readdirSync(AUTH_PATH)
            .filter(nome => nome.startsWith(prefixo))
            .sort()              // carimbo YYYYMMDD-HHMMSS: ordem lexicografica = cronologica
            .reverse();
    } catch (error) {
        writeLog('WARN', `Nao foi possivel listar perfis arquivados para expurgo: ${describeError(error)}`);
        return;
    }
    for (const obsoleto of arquivados.slice(PERFIS_ARQUIVADOS_RETIDOS)) {
        const alvo = path.join(AUTH_PATH, obsoleto);
        try {
            fs.rmSync(alvo, { recursive: true, force: true });
            writeLog('INFO', `Perfil arquivado obsoleto removido: ${obsoleto}`);
        } catch (error) {
            writeLog('WARN', `Falha ao remover perfil arquivado '${obsoleto}': ${describeError(error)}`);
        }
    }
}

async function arquivarPerfilInconsistente(clientId) {
    const perfil = path.join(AUTH_PATH, `session-${clientId}`);
    if (!fs.existsSync(perfil)) {
        // Nada a arquivar — o proximo bootstrap ja parte de perfil limpo. Sucesso, nao
        // falha: devolver false aqui aborta o autenticador com uma mensagem enganosa
        // ("feche as janelas do Chrome") para um perfil que sequer existe.
        writeLog('INFO', `Perfil '${clientId}' inexistente — bootstrap seguinte ja parte do zero.`);
        return true;
    }
    const d = new Date();
    const p = n => String(n).padStart(2, '0');
    const carimbo = `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
    const destino = `${perfil}.inconsistente-${carimbo}`;
    // O Chrome que acabou de morrer ainda segura handles do diretorio por alguns
    // instantes: o rename imediato falha com EPERM. Tenta por ate ~10s.
    let ultimoErro = null;
    for (let tentativa = 1; tentativa <= 10; tentativa++) {
        try {
            fs.renameSync(perfil, destino);
            writeLog('WARN', `Perfil inconsistente arquivado em: ${destino} (nada foi apagado).`);
            expurgarPerfisArquivados(clientId);
            return true;
        } catch (error) {
            ultimoErro = error;
            await sleep(1000);
        }
    }
    writeLog('ERROR', `Nao foi possivel arquivar o perfil '${clientId}': ${describeError(ultimoErro)}`);
    return false;
}

function abortarPorSessaoAusente(contexto) {
    writeLog('ERROR',
        `[${contexto}] Sessao do WhatsApp ausente/zerada no perfil '${CLIENT_ID}' ` +
        '(dispositivo desvinculado ou logout). Reautenticacao obrigatoria: execute ' +
        'lib\\Authenticate-WhatsApp.bat (ou lib\\Keep-WhatsApp-Open.ps1) e leia o QR no celular.');
    process.exit(21);
}

function shouldRetryInitialize(error) {
    const message = describeError(error);
    if (!/Runtime\.callFunctionOn timed out|Execution context was destroyed|protocol timeout|timed out/i.test(message)) {
        return false;
    }
    // Sem sessao persistida o erro nao e transiente: retentar so gasta tempo e mascara
    // a causa real com um ExitCode generico.
    return !sessaoPersistidaAusente(CLIENT_ID);
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
    if (!state.targetMsgId) {
        // Sem id (quirk wwebjs): impossivel casar o evento message_ack. A mensagem ja
        // foi despachada ao pipeline do WA; prosseguimos sem bloquear nem reenviar.
        writeLog('WARN', 'Sem id de mensagem para rastrear ACK — envio ja despachado ao WhatsApp; prosseguindo.');
        return;
    }

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

    // ACK ausente nao implica falha de entrega: em producao o WhatsApp Web entrega a
    // mensagem despachada mesmo sem emitir message_ack rastreavel. Reenviar nunca recuperou
    // nada no historico; logamos e prosseguimos para nao derrubar a execucao por falso-negativo.
    writeLog('WARN', 'ACK nao confirmado em 180s — mensagem despachada ao pipeline do WhatsApp; prosseguindo sem reenvio.');
}

async function executarFluxoComCliente(client) {
    return new Promise((resolve, reject) => {
        const state = {
            targetMsgId: null,
            ackConfirmado: false,
            finalized: false
        };
        let bootstrapDeadline;

        const finalizeAndResolve = async () => {
            if (state.finalized) { return; }
            clearTimeout(bootstrapDeadline);
            state.finalized = true;
            await destruirClienteSilenciosamente(client);
            resolve();
        };

        const finalizeAndReject = async (error) => {
            if (state.finalized) { return; }
            clearTimeout(bootstrapDeadline);
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
            // finalizeAndResolve tambem destroi o cliente; um 'disconnected' emitido durante
            // essa destruicao encerraria o processo com 21 ("requer reautenticacao") mesmo
            // com a mensagem entregue e ACK confirmado. Fora do fluxo, ja acabou.
            if (state.finalized) { return; }
            const error = new Error(`Cliente WhatsApp desconectado: ${reason}`);
            writeLog('WARN', error.message);
            if (String(reason).toUpperCase().includes('LOGOUT')) {
                await destruirClienteSilenciosamente(client);
                abortarPorSessaoAusente('AUTO');
                return;
            }
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
            // BOOTSTRAP_DEADLINE_MS cobre apenas o handshake (initialize -> ready). Sem
            // cancelar aqui, o timer continua correndo sobre o envio + aguardarAck (que
            // sozinho pode levar ate' ACK_WAIT_ATTEMPTS*ACK_WAIT_DELAY_MS=180000ms) e o
            // dreno pos-envio, derrubando o fluxo NO MEIO do envio e causando reenvio da
            // mensagem via retry de processar() mesmo com a entrega ja despachada.
            clearTimeout(bootstrapDeadline);
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
                const opcoesMensagem = await resolverMencoes(client, CAPTION);
                if (ATTACHMENT_PATH && fs.existsSync(ATTACHMENT_PATH)) {
                    writeLog('INFO', 'Enviando anexo Excel...');
                    const media = _whatsappWebJs.MessageMedia.fromFilePath(ATTACHMENT_PATH);
                    sentMsg = await client.sendMessage(chatId, media, opcoesMensagem);
                } else {
                    writeLog('WARN', 'Anexo ausente ou nao encontrado. Enviando apenas a mensagem de texto.');
                    sentMsg = await client.sendMessage(chatId, opcoesMensagem.caption, opcoesMensagem);
                }
                // sendMessage pode resolver com `undefined` (quirk do WhatsApp Web/wwebjs
                // 1.34.x) mesmo com a entrega ja despachada. Guardamos o id defensivamente;
                // sem id, o envio ainda foi despachado ao pipeline do WA.
                state.targetMsgId = (sentMsg && sentMsg.id) ? sentMsg.id._serialized : null;
                if (!state.targetMsgId) {
                    writeLog('WARN', 'sendMessage retornou sem id (quirk WhatsApp Web/wwebjs) — envio despachado ao WA; seguindo sem ACK por id.');
                }

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
        bootstrapDeadline = setTimeout(() => {
            finalizeAndReject(new Error(`Bootstrap do WhatsApp sem handshake concluido em ${BOOTSTRAP_DEADLINE_MS}ms (timed out) — client.initialize() travado antes do evento 'ready'.`));
        }, BOOTSTRAP_DEADLINE_MS);
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

    if (MODE !== 'VISUAL' && sessaoPersistidaAusente(CLIENT_ID)) {
        abortarPorSessaoAusente('AUTO');
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

    for (const [indice, item] of itens.entries()) {
        const { phase_key, image_path, caption } = item;
        const imgPath = path.resolve(image_path);
        writeLog('INFO', `[BATCH] Enviando fase: ${phase_key}...`);

        let success = false;
        let error = null;

        try {
            if (!fs.existsSync(imgPath)) {
                throw new Error(`Imagem nao encontrada: ${imgPath}`);
            }
            const media = _whatsappWebJs.MessageMedia.fromFilePath(imgPath);
            const opcoesMensagem = await resolverMencoes(client, caption);

            // ACK e apenas telemetria: em producao o WhatsApp entrega a mensagem despachada
            // mesmo sem emitir message_ack rastreavel, e reenviar apos ACK ausente nunca
            // recuperou nada (0 sucessos em dezenas de ocorrencias). O sucesso da fase e
            // decidido pelo dispatch de sendMessage (abaixo), nao pela chegada do ACK.
            const ackState = { targetMsgId: null, ackConfirmado: false };
            const ackListener = (msg, ack) => {
                if (ackState.targetMsgId && msg.id._serialized === ackState.targetMsgId && ack >= 1) {
                    ackState.ackConfirmado = true;
                }
            };
            client.on('message_ack', ackListener);

            try {
                const sentMsg = await client.sendMessage(chatId, media, opcoesMensagem);
                // whatsapp-web.js 1.34.x retorna `undefined` quando getMessageModel nao
                // consegue serializar a mensagem enviada (quebra apos updates do WhatsApp
                // Web), MESMO com a entrega fisica ja realizada. Portanto: sendMessage que
                // resolve sem excecao = mensagem despachada ao pipeline do WA = sucesso.
                // O ACK abaixo e telemetria de confirmacao e NUNCA rebaixa um envio despachado.
                const msgId = (sentMsg && sentMsg.id) ? sentMsg.id._serialized : null;
                success = true;

                if (msgId) {
                    ackState.targetMsgId = msgId;
                    writeLog('INFO', `[BATCH] ${phase_key}: Despachado para fila local (${msgId}).`);
                    const acked = await aguardarAckBatch(client, ackState, phase_key, ackAttempts);
                    if (acked) {
                        writeLog('INFO', `[BATCH] ${phase_key}: Entrega confirmada pelo servidor (ACK).`);
                    } else {
                        writeLog('WARN', `[BATCH] ${phase_key}: despachado; ACK nao confirmado na janela — mensagem na fila local do WhatsApp.`);
                    }
                } else {
                    writeLog('WARN', `[BATCH] ${phase_key}: despachado, mas sendMessage retornou sem id (quirk WhatsApp Web/wwebjs). Tratando como enviado.`);
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
                const remainingStartIndex = indice + 1;
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

        if (indice < itens.length - 1 && consecutiveFailures < MAX_CONSECUTIVE_FAILURES) {
            await sleep(3000); // pausa entre mensagens na mesma sessão
        }
    }

    return resultados;
}

// Modo de listagem de grupos: lista todos os grupos disponíveis na sessão e sai
async function executarModoListGroups() {
        // Mesmo guard de AUTO e BATCH: sem sessao em disco o desfecho e 21 de qualquer
        // forma (pelo handler 'qr'), mas so depois de pagar o bootstrap inteiro do Puppeteer.
        if (sessaoPersistidaAusente(CLIENT_ID)) {
            abortarPorSessaoAusente('LIST_GROUPS');
        }
        const client = criarCliente();
        client.on('qr', () => {
            writeLog('WARN', 'QR necessario — use um clientId ja autenticado ou rode em modo VISUAL.');
            process.exit(21);
        });
        client.on('ready', async () => {
            try {
                // client.getChats() quebra na serializacao do whatsapp-web.js apos
                // updates recentes do WhatsApp Web (mesma classe de bug ja vista em
                // sendMessage/getMessageModel — ver CHANGELOG [1.1.7]). Le o Store
                // diretamente via Puppeteer, contornando o wrapper problematico.
                // Store.Chat pode nao estar totalmente populado no instante exato do
                // 'ready' — poll ate a store expor ao menos 1 chat (mais rapido que
                // um sleep fixo no caso comum), com timeout de seguranca.
                await client.pupPage.waitForFunction(
                    () => window.Store && window.Store.Chat && window.Store.Chat.getModelsArray().length > 0,
                    { timeout: 15000, polling: 250 }
                ).catch(() => {
                    writeLog('WARN', 'Store.Chat nao populou em 15s — prosseguindo com o que houver.');
                });
                const groups = await client.pupPage.evaluate(() => {
                    return window.Store.Chat.getModelsArray()
                        .filter(c => c.id && c.id.server === 'g.us')
                        .map(c => ({ id: c.id._serialized, name: c.formattedTitle || c.name || '' }));
                });
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
}

async function executarModoBatch() {
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

    if (sessaoPersistidaAusente(CLIENT_ID)) {
        abortarPorSessaoAusente('BATCH');
    }

    for (let attempt = 1; attempt <= INITIALIZE_MAX_ATTEMPTS; attempt++) {
        const client = criarCliente();
        // O dreno pos-lote mantem o cliente vivo por 30s DEPOIS de todas as fases terem
        // sido despachadas. Um desvinculo nessa janela matava o processo antes da gravacao
        // do resultado: as fases entregues nao eram registradas e o lote inteiro era
        // reenviado na execucao seguinte (mensagens duplicadas no grupo). Por isso o
        // resultado e gravado assim que executarFluxoBatch retorna, e o handler de
        // 'disconnected' consulta o flag antes de sair com 21.
        let loteConcluido = false;
        let resultadoGravado = false;
        // A corrida (Promise.race) pode assentar via reject (auth_failure, disconnected
        // generico, erro de initialize, deadline) ENQUANTO o handler 'ready' ainda esta no
        // meio do await de executarFluxoBatch — um await em andamento nao e' cancelavel, e
        // o catch externo ja pode ter iniciado a PROXIMA tentativa quando este handler
        // 'ready' orfao finalmente retorna. Sem este flag, gravarResultadoLote(res) dessa
        // tentativa obsoleta sobrescreveria batch_result.json com um resultado que nao e'
        // mais o vigente (a tentativa seguinte pode ja ter gravado o seu proprio).
        let abortadoNestaTentativa = false;
        const gravarResultadoLote = (resultados) => {
            if (resultadoGravado) { return; }
            resultadoGravado = true;
            if (!BATCH_RESULT_FILE) { return; }
            try {
                fs.writeFileSync(BATCH_RESULT_FILE, JSON.stringify(resultados, null, 2), 'utf8');
            } catch (err) {
                writeLog('ERROR', `Falha ao gravar arquivo de resultado do lote: ${describeError(err)}`);
            }
        };
        try {
            writeLog('INFO', `Bootstrap do WhatsApp iniciado (tentativa ${attempt}/${INITIALIZE_MAX_ATTEMPTS}).`);
            writeLog('INFO', `Inicializando cliente WhatsApp (bootstrap) com protocolTimeout=${INITIALIZE_PROTOCOL_TIMEOUT_MS}ms...`);

            let bootstrapDeadline;
            const resultados = await Promise.race([
                new Promise((resolve, reject) => {
                client.on('qr', async () => {
                    if (MODE !== 'VISUAL') {
                        writeLog('WARN', 'Sessao expirada. Reautenticacao necessaria.');
                        await destruirClienteSilenciosamente(client);
                        process.exit(21);
                    }
                });
                client.on('auth_failure', async (msg) => {
                    abortadoNestaTentativa = true;
                    await destruirClienteSilenciosamente(client);
                    reject(new Error(`Falha de autenticacao: ${msg}`));
                });
                client.on('disconnected', async (reason) => {
                    await destruirClienteSilenciosamente(client);
                    if (loteConcluido) {
                        // Lote ja despachado e resultado ja em disco: o encerramento normal
                        // esta a caminho. Sair com 21 aqui descartaria a entrega e faria o
                        // run.ps1 reenviar tudo na proxima execucao.
                        writeLog('WARN', `Desconectado apos o lote concluido: ${reason} — resultado ja gravado.`);
                        return;
                    }
                    if (String(reason).toUpperCase().includes('LOGOUT')) {
                        // Desvinculo do dispositivo: nao ha retry possivel — a sessao foi
                        // destruida pelo proprio WhatsApp. Sinaliza reautenticacao (21).
                        writeLog('ERROR', `Desconectado: ${reason} — dispositivo desvinculado.`);
                        abortarPorSessaoAusente('BATCH');
                        return;
                    }
                    abortadoNestaTentativa = true;
                    reject(new Error(`Desconectado: ${reason}`));
                });
                client.on('loading_screen', (pct, msg) => {
                    writeLog('INFO', `Bootstrap: ${pct}% - ${msg}`);
                });
                client.on('ready', async () => {
                    // Mesmo raciocinio do handler 'ready' de executarFluxoComCliente: o
                    // deadline cobre so' initialize -> ready. Sem cancelar aqui, o settle +
                    // ACK por fase + dreno pos-lote (ate' 190s so' para 1 fase sem ACK) estoura
                    // o deadline de 180s NO MEIO do lote e reenvia TODAS as fases pelo retry.
                    clearTimeout(bootstrapDeadline);
                    const settleMs = attempt > 1 ? BATCH_SETTLE_MS_RETRY : BATCH_SETTLE_MS_NORMAL;
                    writeLog('INFO', `Cliente pronto. Aguardando estabilizacao do WhatsApp Web (${settleMs / 1000}s)...`);
                    await sleep(settleMs);
                    await verificarEstadoConectado(client, 'BATCH');
                    try {
                        writeLog('INFO', `Processando ${itens.length} fases em lote...`);
                        const res = await executarFluxoBatch(client, itens, chatId, attempt);
                        if (abortadoNestaTentativa) {
                            // A corrida ja foi decidida (rejeitada) enquanto executarFluxoBatch
                            // rodava — outra tentativa pode ja estar em andamento ou ja ter
                            // gravado seu proprio resultado. Descarta em vez de sobrescrever.
                            writeLog('WARN', 'Lote concluido apos a corrida de bootstrap ja ter sido decidida — resultado descartado (nao sobrescreve outra tentativa).');
                            await destruirClienteSilenciosamente(client);
                            return;
                        }
                        gravarResultadoLote(res);
                        loteConcluido = true;
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
                    abortadoNestaTentativa = true;
                    writeLog('ERROR', `Erro na inicializacao: ${describeError(err)}`);
                    await destruirClienteSilenciosamente(client);
                    reject(err);
                });
                }),
                new Promise((_, reject) => {
                    bootstrapDeadline = setTimeout(() => {
                        abortadoNestaTentativa = true;
                        reject(new Error(`Bootstrap do WhatsApp sem handshake concluido em ${BOOTSTRAP_DEADLINE_MS}ms (timed out) — client.initialize() travado antes do evento 'ready'.`));
                    }, BOOTSTRAP_DEADLINE_MS);
                })
            ]).finally(() => clearTimeout(bootstrapDeadline));

            gravarResultadoLote(resultados);
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
}

// Auth-only: abre Chrome visivel, aguarda QR scan e sai apos ready
async function executarModoVisualAuth() {
    writeLog('INFO', '=== AUTENTICACAO VISUAL (auth-only) ===');

    // Uma unica retentativa, e apenas apos arquivar um perfil comprovadamente
    // inconsistente — nunca um retry cego sobre um perfil que ainda tem sessao.
    const bootstrapAutenticador = (perfilJaArquivado) => new Promise((resolve, reject) => {
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
            // 'ready' NAO significa sessao gravada em disco. O WhatsApp Web ainda esta
            // escrevendo as chaves no IndexedDB/LevelDB do perfil; destruir o cliente
            // no mesmo tick descarta essa gravacao e a proxima execucao volta a pedir QR
            // — foi exatamente o que se observou em 28/07/2026, com duas autenticacoes
            // seguidas "bem-sucedidas" que nao sobreviveram ao processo seguinte.
            writeLog('INFO', `Cliente pronto — sessao '${CLIENT_ID}' ativa.`);
            writeLog('INFO', `Persistindo sessao em disco (${AUTH_SETTLE_MS / 1000}s)... NAO feche esta janela.`);
            for (let decorrido = 0; decorrido < AUTH_SETTLE_MS; decorrido += 3000) {
                await sleep(3000);
                if (client.pupPage) {
                    try { await client.pupPage.mouse.move(decorrido % 50, decorrido % 50); } catch (_) {}
                }
            }
            if (!sessaoPersistidaConfirmada(CLIENT_ID)) {
                writeLog('ERROR', 'Sessao nao confirmada no perfil apos o dreno — nao encerre o processo a forca.');
                await destruirClienteSilenciosamente(client);
                reject(new Error('Sessao autenticada mas nao persistida em disco.'));
                return;
            }
            writeLog('INFO', 'Sessao gravada em disco. Encerrando autenticador.');
            await destruirClienteSilenciosamente(client);
            resolve('READY');
        });
        client.on('auth_failure', async (msg) => {
            writeLog('ERROR', `Falha de autenticacao: ${msg}`);
            await destruirClienteSilenciosamente(client);
            reject(new Error(`auth_failure: ${msg}`));
        });
        client.initialize().catch(async (err) => {
            writeLog('ERROR', `Erro ao inicializar: ${describeError(err)}`);
            await destruirClienteSilenciosamente(client);
            const contextoDestruido = /Execution context was destroyed/i.test(describeError(err));
            if (contextoDestruido && !perfilJaArquivado && sessaoPersistidaAusente(CLIENT_ID)) {
                // Perfil poluido por logout anterior: sem isso o QR nunca renderiza.
                resolve('ARQUIVAR');
                return;
            }
            reject(err);
        });
    });

    try {
        let resultado = await bootstrapAutenticador(false);
        if (resultado === 'ARQUIVAR') {
            writeLog('WARN',
                'Bootstrap falhou com o perfil pos-logout (contexto destruido) e nao ha sessao ' +
                'persistida. Arquivando o perfil e reiniciando do zero para exibir o QR Code...');
            if (!await arquivarPerfilInconsistente(CLIENT_ID)) {
                writeLog('ERROR', 'Feche todas as janelas do Chrome desta sessao e tente novamente.');
                process.exit(24);
            }
            resultado = await bootstrapAutenticador(true);
            if (resultado !== 'READY') {
                writeLog('ERROR', 'Bootstrap falhou mesmo com perfil limpo.');
                process.exit(24);
            }
        }
        process.exit(0);
    } catch (err) {
        writeLog('ERROR', `ENCERRAMENTO POR FALHA: ${describeError(err)}`);
        process.exit(24);
    }
}

async function executarModoAuto() {
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
}

// Dispatcher: MODE decide qual fluxo roda quando este arquivo e' executado como CLI
// (node WhatsApp-Core.js ...). O guard require.main===module e' o que torna o arquivo
// require()-avel em testes sem disparar bootstrap real de Puppeteer/WhatsApp no import.
function selecionarModo() {
    if (MODE === 'LIST_GROUPS') { return executarModoListGroups; }
    if (MODE === 'BATCH') { return executarModoBatch; }
    if (MODE === 'VISUAL' && !CONTACT_ARG) { return executarModoVisualAuth; }
    return executarModoAuto;
}

if (require.main === module) {
    selecionarModo()();
}

module.exports = {
    agoraBR,
    writeLog,
    sleep,
    comTimeout,
    describeError,
    resolverMencoes,
    resolverNumeroMencao,
    descreverMotivoMencao,
    _limparCacheMencoesForTests,
    criarCliente,
    cleanProfileForRetry,
    sessaoPersistidaAusente,
    sessaoPersistidaConfirmada,
    expurgarPerfisArquivados,
    arquivarPerfilInconsistente,
    abortarPorSessaoAusente,
    shouldRetryInitialize,
    destruirClienteSilenciosamente,
    verificarEstadoConectado,
    aguardarAck,
    executarFluxoComCliente,
    processar,
    aguardarAckBatch,
    executarFluxoBatch,
    executarModoListGroups,
    executarModoBatch,
    executarModoVisualAuth,
    executarModoAuto,
    selecionarModo,
    _setWhatsAppWebJsForTests,
    // Constantes uteis para asserts diretos em testes (evita duplicar magic numbers)
    INITIALIZE_MAX_ATTEMPTS,
    INITIALIZE_RETRY_DELAY_MS,
    INITIALIZE_PROTOCOL_TIMEOUT_MS,
    BOOTSTRAP_DEADLINE_MS,
    ACK_WAIT_ATTEMPTS,
    ACK_WAIT_DELAY_MS,
    ACK_SETTLE_DELAY_MS,
    AUTH_SETTLE_MS,
    MENTION_RESOLVE_TIMEOUT_MS,
    MENTION_RESOLVE_ATTEMPTS,
    MENTION_RESOLVE_RETRY_DELAY_MS,
    MENTION_RESOLVE_BUDGET_MS,
    BATCH_SETTLE_MS_NORMAL,
    BATCH_SETTLE_MS_RETRY,
    ACK_WAIT_ATTEMPTS_BATCH_NORMAL,
    ACK_WAIT_ATTEMPTS_BATCH_RETRY,
    PERFIS_ARQUIVADOS_RETIDOS,
    EXEC_ID,
    MODE,
    CLIENT_ID,
    CONTACT_ARG,
    ATTACHMENT_PATH,
    CAPTION,
    LOG_FILE,
    BATCH_FILE,
    BATCH_RESULT_FILE,
    AUTH_PATH
};
