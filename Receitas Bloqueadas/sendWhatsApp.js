// =============================================================================
// sendWhatsApp.js — Versão corrigida
// Correções:
//   1. Bootstrap log gravado ANTES de qualquer require (rastreabilidade máxima)
//   2. QR em modo silencioso → abort imediato (não aguarda 5 retries)
//   3. Logs detalhados com pid, cwd, argv desde o início
//   4. Sessão expirada → ExitCode=21 para BAT relançar em PAIRING
// =============================================================================

// BOOTSTRAP LOG — usa append síncrono nativa do Node (sem dependência externa)
// Este bloco DEVE ser o primeiro código a executar.
const fs = require('fs');
const path = require('path');

const BOOTSTRAP_LOG_FILE = path.join(__dirname, 'sendWhatsApp-bootstrap.log');

function _bootstrapTs() {
  const d = new Date();
  const p = (n, w) => String(n).padStart(w || 2, '0');
  return `${p(d.getDate())}/${p(d.getMonth()+1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function _bootstrapLog(msg) {
  const linha = `[${_bootstrapTs()}] [NODE] ${msg}\r\n`;
  try { fs.appendFileSync(BOOTSTRAP_LOG_FILE, linha, 'utf8'); } catch (_) {}
  try {
    const main = path.join(__dirname, 'ReceitasBloqueadas.txt');
    fs.appendFileSync(main, linha, 'utf8');
  } catch (_) {}
}

_bootstrapLog(`=== BOOTSTRAP NODE INICIADO ===`);
_bootstrapLog(`pid=${process.pid} | node=${process.version} | cwd=${process.cwd()}`);
_bootstrapLog(`argv=${JSON.stringify(process.argv)}`);
_bootstrapLog(`__dirname=${__dirname}`);

// Agora importa os módulos pesados
const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');

const CONFIG_FILE = path.join(__dirname, 'whatsapp-config.json');

const EXIT_CODES = {
  SUCCESS: 0,
  DISABLED: 0,
  MISSING_ATTACHMENT: 11,
  FINAL_ERROR: 20,
  REAUTH_REQUIRED: 21,
  INVALID_CONFIG: 22,
  COOLDOWN_ACTIVE: 23,
  FATAL: 99
};

let CONFIG = null;
let globalShutdownInProgress = false;

function agoraBR() {
  const d = new Date();
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const yyyy = d.getFullYear();
  const hh = String(d.getHours()).padStart(2, '0');
  const mi = String(d.getMinutes()).padStart(2, '0');
  const ss = String(d.getSeconds()).padStart(2, '0');
  return `${dd}/${mm}/${yyyy} ${hh}:${mi}:${ss}`;
}

function ensureDir(dirPath) {
  if (!dirPath) return;
  fs.mkdirSync(dirPath, { recursive: true });
}

function ensureParentDir(filePath) {
  if (!filePath) return;
  ensureDir(path.dirname(filePath));
}

function getActiveLogFile() {
  // Tenta usar o logFile configurado; caso CONFIG não esteja pronto, usa o bootstrap
  if (CONFIG && CONFIG.paths && CONFIG.paths.logFile) {
    return CONFIG.paths.logFile;
  }
  // Fallback: tenta inferir o path padrão mesmo sem CONFIG
  return path.join(__dirname, 'ReceitasBloqueadas.txt');
}

function appendLine(filePath, line) {
  ensureParentDir(filePath);
  fs.appendFileSync(filePath, line, { encoding: 'utf8' });
}

function escreverLog(origem, mensagem) {
  const linha = `[${agoraBR()}] [${origem}] ${mensagem}\r\n`;

  try {
    appendLine(getActiveLogFile(), linha);
  } catch (erroLogPrincipal) {
    try {
      appendLine(BOOTSTRAP_LOG_FILE, linha);
      appendLine(
        BOOTSTRAP_LOG_FILE,
        `[${agoraBR()}] [NODE] AVISO: Falha ao gravar no log principal (${erroLogPrincipal.message}).\r\n`
      );
    } catch (_) {}
  }

  try {
    if (process.stdout && process.stdout.isTTY) {
      process.stdout.write(linha);
    }
  } catch (_) {}
}

function formatarErro(erro) {
  if (!erro) return 'erro-desconhecido';

  if (erro instanceof Error) {
    const name = erro.name || 'Error';
    const message = erro.message || 'sem-mensagem';
    const exitCode = erro.exitCode ? ` | exitCode=${erro.exitCode}` : '';
    const stack = erro.stack
      ? erro.stack
          .split('\n')
          .slice(1, 4)
          .map(l => l.trim())
          .join(' | ')
      : '';

    return `${name}: ${message}${exitCode}${stack ? ` | stack=${stack}` : ''}`;
  }

  return String(erro);
}

class ManagedError extends Error {
  constructor(message, exitCode) {
    super(message);
    this.name = 'ManagedError';
    this.exitCode = exitCode;
  }
}

function normalizarPhone(phone) {
  return String(phone || '').replace(/\D/g, '');
}

function unique(arr) {
  return [...new Set(arr)];
}

function serializarId(id) {
  if (!id) return '';
  if (typeof id === 'string') return id;
  if (typeof id === 'object' && id._serialized) return id._serialized;
  if (typeof id === 'object' && id.id && id.id._serialized) return id.id._serialized;
  return String(id);
}

function extrairNumero(chatId) {
  return String(chatId || '')
    .split('@')[0]
    .replace(/\D/g, '');
}

function safeJsonParse(texto, origem) {
  try {
    return JSON.parse(texto);
  } catch (erro) {
    throw new ManagedError(
      `JSON inválido em ${origem}: ${erro.message}`,
      EXIT_CODES.INVALID_CONFIG
    );
  }
}

function validarInteiroPositivo(nome, valor, minimo = 1) {
  if (!Number.isInteger(valor) || valor < minimo) {
    throw new ManagedError(
      `${nome} inválido: esperado inteiro >= ${minimo}, recebido=${valor}`,
      EXIT_CODES.INVALID_CONFIG
    );
  }
}

function carregarConfig() {
  if (!fs.existsSync(CONFIG_FILE)) {
    throw new ManagedError(
      `Arquivo de configuração não encontrado: ${CONFIG_FILE}`,
      EXIT_CODES.INVALID_CONFIG
    );
  }

  const raw = fs.readFileSync(CONFIG_FILE, 'utf8');
  const userConfig = safeJsonParse(raw, CONFIG_FILE);

  const legacyMentionEnabled = userConfig?.target?.mention?.enabled ?? false;
  const legacyMentionPhone = normalizarPhone(userConfig?.target?.mention?.phone);

  const mentionsList = Array.isArray(userConfig?.target?.mentions?.list)
    ? userConfig.target.mentions.list
    : [];

  const mentionsEnabled =
    userConfig?.target?.mentions?.enabled ??
    legacyMentionEnabled;

  const normalizedMentions = mentionsList
    .map(item => {
      if (typeof item === 'string') {
        return { phone: normalizarPhone(item) };
      }

      return {
        phone: normalizarPhone(item?.phone)
      };
    })
    .filter(item => item.phone);

  if (legacyMentionEnabled && legacyMentionPhone && normalizedMentions.length === 0) {
    normalizedMentions.push({ phone: legacyMentionPhone });
  }

  const config = {
    app: {
      enabled: userConfig?.app?.enabled ?? true
    },
    paths: {
      attachmentPath:
        userConfig?.paths?.attachmentPath ??
        'C:\\Automacoes\\Receitas Bloqueadas\\Receitas Bloqueadas.xlsm',
      logFile:
        userConfig?.paths?.logFile ??
        'C:\\Automacoes\\Receitas Bloqueadas\\ReceitasBloqueadas.txt',
      stateFile: path.isAbsolute(userConfig?.paths?.stateFile || '')
        ? userConfig.paths.stateFile
        : path.join(__dirname, userConfig?.paths?.stateFile ?? 'whatsapp-state.json'),
      authDir: path.isAbsolute(userConfig?.paths?.authDir || '')
        ? userConfig.paths.authDir
        : path.join(__dirname, userConfig?.paths?.authDir ?? '.wwebjs_auth')
    },
    target: {
      enabled: userConfig?.target?.enabled ?? true,
      type: String(userConfig?.target?.type ?? 'group').trim().toLowerCase(),
      groupName: String(userConfig?.target?.groupName ?? '').trim(),
      contactPhone: normalizarPhone(userConfig?.target?.contactPhone),
      contactId: String(userConfig?.target?.contactId ?? '').trim(),
      mentions: {
        enabled: mentionsEnabled,
        list: normalizedMentions
      }
    },
    message: {
      sendAttachment: userConfig?.message?.sendAttachment ?? true,
      caption: {
        enabled: userConfig?.message?.caption?.enabled ?? true,
        title: {
          enabled: userConfig?.message?.caption?.title?.enabled ?? true,
          text: userConfig?.message?.caption?.title?.text ?? 'Receitas Bloqueadas'
        },
        body: {
          enabled: userConfig?.message?.caption?.body?.enabled ?? true,
          text:
            userConfig?.message?.caption?.body?.text ??
            'Segue planilha atualizada em anexo.'
        },
        execId: {
          enabled: userConfig?.message?.caption?.execId?.enabled ?? false,
          label: userConfig?.message?.caption?.execId?.label ?? 'Execução:',
          fallback: userConfig?.message?.caption?.execId?.fallback ?? 'sem-exec-id'
        }
      }
    },
    idempotency: {
      enabled: userConfig?.idempotency?.enabled ?? true,
      retryFailedAfterMs: userConfig?.idempotency?.retryFailedAfterMs ?? 0,
      keepSuccessForMs: userConfig?.idempotency?.keepSuccessForMs ?? 30 * 24 * 60 * 60 * 1000,
      keepFailureForMs: userConfig?.idempotency?.keepFailureForMs ?? 7 * 24 * 60 * 60 * 1000
    },
    terminal: {
      showQr: userConfig?.terminal?.showQr ?? true
    },
    auth: {
      clientId: userConfig?.auth?.clientId ?? 'receitas-bloqueadas'
    },
    runtime: {
      headless: userConfig?.runtime?.headless ?? true
    },
    retry: {
      enabled: userConfig?.retry?.enabled ?? true,
      maxAttempts: userConfig?.retry?.maxAttempts ?? 3,
      attemptDelayMs: userConfig?.retry?.attemptDelayMs ?? 20000,
      sendSettleMs: userConfig?.retry?.sendSettleMs ?? 8000,
      finalWaitMs: userConfig?.retry?.finalWaitMs ?? 5000,
      initTimeoutMs: userConfig?.retry?.initTimeoutMs ?? 180000
    }
  };

  validarInteiroPositivo('retry.maxAttempts', config.retry.maxAttempts, 1);
  validarInteiroPositivo('retry.attemptDelayMs', config.retry.attemptDelayMs, 0);
  validarInteiroPositivo('retry.sendSettleMs', config.retry.sendSettleMs, 0);
  validarInteiroPositivo('retry.finalWaitMs', config.retry.finalWaitMs, 0);
  validarInteiroPositivo('retry.initTimeoutMs', config.retry.initTimeoutMs, 1000);
  validarInteiroPositivo('idempotency.retryFailedAfterMs', config.idempotency.retryFailedAfterMs, 0);
  validarInteiroPositivo('idempotency.keepSuccessForMs', config.idempotency.keepSuccessForMs, 0);
  validarInteiroPositivo('idempotency.keepFailureForMs', config.idempotency.keepFailureForMs, 0);

  ensureDir(config.paths.authDir);
  ensureParentDir(config.paths.stateFile);
  ensureParentDir(config.paths.logFile);

  return config;
}

try {
  _bootstrapLog('Chamando carregarConfig()...');
  CONFIG = carregarConfig();
  _bootstrapLog(`Config carregada com sucesso. logFile=${CONFIG.paths.logFile}`);
} catch (erro) {
  _bootstrapLog(`ERRO FATAL AO CARREGAR CONFIG: ${String(erro?.message || erro)}`);
  escreverLog('NODE', `ERRO FATAL AO CARREGAR CONFIG: ${formatarErro(erro)}`);
  process.exit(erro.exitCode || EXIT_CODES.FATAL);
}

const EXEC_ID = (process.argv[2] || '').trim();
const RUNTIME_MODE = String(process.argv[3] || '').trim().toUpperCase();

// Log imediato com contexto de execução (antes de qualquer operação de negócio)
escreverLog('NODE', `=== INICIO EXECUCAO NODE ===`);
escreverLog('NODE', `pid=${process.pid} | node=${process.version} | cwd=${process.cwd()}`);
escreverLog('NODE', `argv=${JSON.stringify(process.argv)}`);
escreverLog('NODE', `EXEC_ID=${EXEC_ID || 'sem-exec-id'} | RUNTIME_MODE=${RUNTIME_MODE || 'AUTO'}`);
escreverLog('NODE', `CONFIG_FILE=${CONFIG_FILE}`);
escreverLog('NODE', `logFile=${CONFIG.paths.logFile}`);
escreverLog('NODE', `authDir=${CONFIG.paths.authDir}`);
escreverLog('NODE', `stateFile=${CONFIG.paths.stateFile}`);

function getSessionDir() {
  return path.join(CONFIG.paths.authDir, `session-${CONFIG.auth.clientId}`);
}

function countFilesRecursively(dirPath, limit = 2000) {
  let count = 0;
  const queue = [dirPath];

  while (queue.length > 0) {
    const atual = queue.shift();
    let entries = [];

    try {
      entries = fs.readdirSync(atual, { withFileTypes: true });
    } catch (_) {
      continue;
    }

    for (const entry of entries) {
      const full = path.join(atual, entry.name);
      if (entry.isDirectory()) {
        queue.push(full);
      } else {
        count += 1;
        if (count >= limit) return count;
      }
    }
  }

  return count;
}

function getSessionSnapshot() {
  const sessionDir = getSessionDir();
  const exists = fs.existsSync(sessionDir);
  const fileCount = exists ? countFilesRecursively(sessionDir) : 0;

  return {
    sessionDir,
    exists,
    fileCount
  };
}

function hasSavedSession() {
  try {
    const snapshot = getSessionSnapshot();
    return snapshot.exists && snapshot.fileCount > 0;
  } catch {
    return false;
  }
}

function shouldRunVisible() {
  if (RUNTIME_MODE === 'PAIRING') {
    escreverLog('NODE', 'shouldRunVisible=SIM (RUNTIME_MODE=PAIRING)');
    return true;
  }
  const sessaoSalva = hasSavedSession();
  if (!sessaoSalva) {
    escreverLog('NODE', 'shouldRunVisible=SIM (sessao nao encontrada ou vazia)');
    return true;
  }
  const visivel = !CONFIG.runtime.headless;
  escreverLog('NODE', `shouldRunVisible=${visivel ? 'SIM' : 'NAO'} (sessao=EXISTE | headlessConfig=${CONFIG.runtime.headless ? 'SIM' : 'NAO'})`);
  return visivel;
}

const FORCE_VISIBLE = shouldRunVisible();

function getMaxAttempts() {
  return CONFIG.retry.enabled ? CONFIG.retry.maxAttempts : 1;
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function garantirEstruturaEstado(estado) {
  if (!estado || typeof estado !== 'object') {
    return {
      sentExecutions: {},
      failedDeliveries: {}
    };
  }

  if (!estado.sentExecutions || typeof estado.sentExecutions !== 'object') {
    estado.sentExecutions = {};
  }

  if (!estado.failedDeliveries || typeof estado.failedDeliveries !== 'object') {
    estado.failedDeliveries = {};
  }

  return estado;
}

function limparEstadoExpirado(estado) {
  let alterado = false;
  const agoraMs = Date.now();

  const keepSuccessForMs = CONFIG.idempotency.keepSuccessForMs;
  const keepFailureForMs = CONFIG.idempotency.keepFailureForMs;

  if (keepSuccessForMs > 0) {
    for (const [key, info] of Object.entries(estado.sentExecutions)) {
      const epoch = Number(info?.sentAtEpochMs || 0);
      if (epoch > 0 && (agoraMs - epoch) > keepSuccessForMs) {
        delete estado.sentExecutions[key];
        alterado = true;
      }
    }
  }

  if (keepFailureForMs > 0) {
    for (const [key, info] of Object.entries(estado.failedDeliveries)) {
      const epoch = Number(info?.lastFailureEpochMs || 0);
      if (epoch > 0 && (agoraMs - epoch) > keepFailureForMs) {
        delete estado.failedDeliveries[key];
        alterado = true;
      }
    }
  }

  return alterado;
}

function carregarEstado() {
  try {
    if (!fs.existsSync(CONFIG.paths.stateFile)) {
      return {
        sentExecutions: {},
        failedDeliveries: {}
      };
    }

    const raw = fs.readFileSync(CONFIG.paths.stateFile, 'utf8');
    const parsed = safeJsonParse(raw, CONFIG.paths.stateFile);
    return garantirEstruturaEstado(parsed);
  } catch (erro) {
    escreverLog('NODE', `AVISO: Falha ao carregar stateFile. Reiniciando estrutura. Detalhe=${formatarErro(erro)}`);
    return {
      sentExecutions: {},
      failedDeliveries: {}
    };
  }
}

function salvarEstado(estado) {
  const payload = JSON.stringify(estado, null, 2);
  const tempPath = `${CONFIG.paths.stateFile}.tmp`;

  try {
    fs.writeFileSync(tempPath, payload, 'utf8');
    fs.renameSync(tempPath, CONFIG.paths.stateFile);
  } catch (erro) {
    try {
      if (fs.existsSync(tempPath)) {
        fs.unlinkSync(tempPath);
      }
    } catch (_) {}
    throw erro;
  }
}

function carregarEstadoComHousekeeping() {
  const estado = carregarEstado();
  const alterado = limparEstadoExpirado(estado);
  if (alterado) {
    salvarEstado(estado);
  }
  return estado;
}

function obterFalhaAnterior(entregaKey) {
  const estado = carregarEstadoComHousekeeping();
  return estado.failedDeliveries[entregaKey] || null;
}

function registrarFalhaEntrega(execKey, entregaKey, erro, exitCode, tentativaAtual, maxTentativas) {
  const estado = carregarEstadoComHousekeeping();
  const agoraMs = Date.now();
  const falhaAnterior = estado.failedDeliveries[entregaKey] || {};

  const proximaTentativaMs = CONFIG.idempotency.retryFailedAfterMs > 0
    ? (agoraMs + CONFIG.idempotency.retryFailedAfterMs)
    : 0;

  estado.failedDeliveries[entregaKey] = {
    firstFailureEpochMs: Number(falhaAnterior.firstFailureEpochMs || agoraMs),
    firstFailureAtBR: falhaAnterior.firstFailureAtBR || agoraBR(),
    lastFailureEpochMs: agoraMs,
    lastFailureAtBR: agoraBR(),
    consecutiveFailures: Number(falhaAnterior.consecutiveFailures || 0) + 1,
    lastExecId: EXEC_ID || null,
    lastExecKey: execKey,
    lastExitCode: exitCode || EXIT_CODES.FINAL_ERROR,
    lastAttempt: tentativaAtual,
    maxAttempts: maxTentativas,
    targetType: CONFIG.target.type,
    targetLabel: getTargetLabel(),
    attachment: CONFIG.message.sendAttachment ? CONFIG.paths.attachmentPath : null,
    lastError: formatarErro(erro),
    nextRetryAtEpochMs: proximaTentativaMs,
    nextRetryAtBR: proximaTentativaMs > 0 ? new Date(proximaTentativaMs).toLocaleString('pt-BR') : null
  };

  salvarEstado(estado);
}

function limparFalhaEntrega(entregaKey) {
  const estado = carregarEstadoComHousekeeping();
  if (estado.failedDeliveries[entregaKey]) {
    delete estado.failedDeliveries[entregaKey];
    salvarEstado(estado);
  }
}

function obterAssinaturaArquivo(filePath) {
  const st = fs.statSync(filePath);
  return {
    size: st.size,
    mtimeMs: Math.trunc(st.mtimeMs)
  };
}

function getMentionPhones() {
  if (!CONFIG.target.mentions.enabled) return [];

  const phones = CONFIG.target.mentions.list
    .map(item => normalizarPhone(item?.phone))
    .filter(Boolean);

  return unique(phones);
}

function getMentionIds() {
  return getMentionPhones().map(phone => `${phone}@c.us`);
}

function getConfiguredContactId() {
  return serializarId(CONFIG.target.contactId || '');
}

function getFallbackContactIdFromPhone() {
  if (CONFIG.target.contactPhone) return `${CONFIG.target.contactPhone}@c.us`;
  return '';
}

function getTargetLabel() {
  if (CONFIG.target.type === 'group') {
    return CONFIG.target.groupName;
  }

  return CONFIG.target.contactPhone || CONFIG.target.contactId || 'destino-sem-id';
}

function validarChatId(chatId) {
  return /@(c|g)\.us$/.test(String(chatId || '').trim());
}

function validarConfig() {
  if (!CONFIG.app.enabled) return;

  if (!CONFIG.target.enabled) {
    throw new ManagedError('Destino desabilitado por configuração.', EXIT_CODES.INVALID_CONFIG);
  }

  if (!['group', 'contact'].includes(CONFIG.target.type)) {
    throw new ManagedError(`target.type inválido: ${CONFIG.target.type}`, EXIT_CODES.INVALID_CONFIG);
  }

  if (CONFIG.target.type === 'group' && !CONFIG.target.groupName) {
    throw new ManagedError(
      'target.groupName é obrigatório quando target.type = "group".',
      EXIT_CODES.INVALID_CONFIG
    );
  }

  if (
    CONFIG.target.type === 'contact' &&
    !CONFIG.target.contactPhone &&
    !getConfiguredContactId()
  ) {
    throw new ManagedError(
      'target.contactPhone ou target.contactId é obrigatório quando target.type = "contact".',
      EXIT_CODES.INVALID_CONFIG
    );
  }

  if (CONFIG.target.contactId && !validarChatId(CONFIG.target.contactId)) {
    throw new ManagedError(
      'target.contactId inválido. Use algo como 5547999999999@c.us.',
      EXIT_CODES.INVALID_CONFIG
    );
  }

  if (CONFIG.target.mentions.enabled && getMentionPhones().length === 0) {
    throw new ManagedError(
      'target.mentions.enabled=true, mas nenhuma menção válida foi informada.',
      EXIT_CODES.INVALID_CONFIG
    );
  }

  if (CONFIG.message.sendAttachment && !CONFIG.paths.attachmentPath) {
    throw new ManagedError(
      'paths.attachmentPath deve ser informado quando sendAttachment = true.',
      EXIT_CODES.INVALID_CONFIG
    );
  }

  if (!CONFIG.message.sendAttachment && !CONFIG.message.caption.enabled) {
    throw new ManagedError(
      'Nada para enviar: sendAttachment=false e caption.enabled=false.',
      EXIT_CODES.INVALID_CONFIG
    );
  }
}

function montarExecKey() {
  const partes = [
    CONFIG.target.type,
    getTargetLabel(),
    EXEC_ID || 'sem-exec-id'
  ];

  if (CONFIG.message.sendAttachment) {
    const sig = obterAssinaturaArquivo(CONFIG.paths.attachmentPath);
    partes.push(String(sig.size), String(sig.mtimeMs));
  } else {
    partes.push('sem-anexo');
  }

  const mentions = getMentionPhones();
  if (mentions.length > 0) {
    partes.push(`mentions=${mentions.join(',')}`);
  }

  return partes.join('|');
}

function montarEntregaKey() {
  const partes = [
    CONFIG.target.type,
    getTargetLabel()
  ];

  if (CONFIG.message.sendAttachment) {
    const sig = obterAssinaturaArquivo(CONFIG.paths.attachmentPath);
    partes.push(String(sig.size), String(sig.mtimeMs));
  } else {
    partes.push('sem-anexo');
  }

  const mentions = getMentionPhones();
  if (mentions.length > 0) {
    partes.push(`mentions=${mentions.join(',')}`);
  }

  return partes.join('|');
}

function jaEnviado(execKey) {
  const estado = carregarEstadoComHousekeeping();
  return !!estado.sentExecutions[execKey];
}

function marcarEnviado(execKey, messageId, destino) {
  const estado = carregarEstadoComHousekeeping();
  estado.sentExecutions[execKey] = {
    sentAtEpochMs: Date.now(),
    sentAtBR: agoraBR(),
    execId: EXEC_ID || null,
    targetType: CONFIG.target.type,
    targetLabel: destino?.targetLabel || getTargetLabel(),
    targetSource: destino?.source || null,
    mentions: getMentionPhones(),
    attachment: CONFIG.message.sendAttachment ? CONFIG.paths.attachmentPath : null,
    messageId: messageId || null
  };
  salvarEstado(estado);
}

async function localizarGrupo(client, nomeGrupo) {
  const chats = await client.getChats();
  const grupos = chats.filter(c => c.isGroup);

  const grupo = grupos.find(g => {
    const nome = String(g.name || g.subject || '').trim().toLowerCase();
    return nome === nomeGrupo.trim().toLowerCase();
  });

  if (!grupo) {
    throw new Error(`Grupo '${nomeGrupo}' não encontrado`);
  }

  return grupo;
}

async function tentarResolverPorNumero(client, phone) {
  const numero = normalizarPhone(phone);
  if (!numero) return null;

  if (typeof client.getNumberId === 'function') {
    try {
      const numberId = await client.getNumberId(numero);
      const serialized = serializarId(numberId);

      if (serialized) {
        escreverLog('NODE', `Contato resolvido por getNumberId: ${numero} -> ${serialized}`);
        return {
          chatId: serialized,
          targetLabel: numero,
          source: 'getNumberId'
        };
      }

      escreverLog('NODE', `getNumberId retornou vazio para ${numero}.`);
    } catch (erro) {
      escreverLog('NODE', `AVISO: getNumberId falhou para ${numero}: ${formatarErro(erro)}`);
    }
  } else {
    escreverLog('NODE', 'AVISO: client.getNumberId não está disponível nesta versão.');
  }

  try {
    const chats = await client.getChats();

    const chat = chats.find(c => {
      if (c.isGroup) return false;

      const serialized = serializarId(c.id);
      const numeroChat = extrairNumero(serialized);

      return numeroChat === numero || serialized === `${numero}@c.us`;
    });

    if (chat) {
      const serialized = serializarId(chat.id);
      escreverLog('NODE', `Contato resolvido por getChats: ${numero} -> ${serialized}`);
      return {
        chatId: serialized,
        targetLabel: numero,
        source: 'getChats'
      };
    }

    escreverLog('NODE', `Contato ${numero} não encontrado em getChats.`);
  } catch (erro) {
    escreverLog('NODE', `AVISO: getChats falhou ao procurar ${numero}: ${formatarErro(erro)}`);
  }

  return null;
}

async function validarDestinoContato(client, chatId, label, source, allowUnvalidated = false) {
  const serialized = serializarId(chatId);
  if (!serialized) return null;

  try {
    if (typeof client.getChatById !== 'function') {
      escreverLog('NODE', 'AVISO: client.getChatById não está disponível nesta versão.');
      return {
        chatId: serialized,
        targetLabel: label || extrairNumero(serialized),
        source: `${source} (sem getChatById)`
      };
    }

    const chat = await client.getChatById(serialized);
    const finalId = serializarId(chat?.id) || serialized;

    escreverLog('NODE', `Contato validado por getChatById: ${serialized} -> ${finalId}`);
    return {
      chatId: finalId,
      targetLabel: label || extrairNumero(finalId),
      source: `${source} + getChatById`
    };
  } catch (erro) {
    escreverLog('NODE', `AVISO: getChatById falhou para ${serialized}: ${formatarErro(erro)}`);

    if (allowUnvalidated && validarChatId(serialized)) {
      escreverLog('NODE', `Prosseguindo com chatId não validado: ${serialized}`);
      return {
        chatId: serialized,
        targetLabel: label || extrairNumero(serialized),
        source: `${source} (não validado)`
      };
    }

    return null;
  }
}

async function resolverDestino(client) {
  if (CONFIG.target.type === 'group') {
    const grupo = await localizarGrupo(client, CONFIG.target.groupName);
    return {
      chatId: serializarId(grupo.id),
      targetLabel: CONFIG.target.groupName,
      source: 'group'
    };
  }

  const contactIdConfig = getConfiguredContactId();
  const contactPhone = normalizarPhone(CONFIG.target.contactPhone);

  if (contactIdConfig) {
    const validado = await validarDestinoContato(
      client,
      contactIdConfig,
      contactPhone || contactIdConfig,
      'contactId-config',
      true
    );

    if (validado) return validado;
  }

  if (contactPhone) {
    const resolvido = await tentarResolverPorNumero(client, contactPhone);

    if (resolvido) {
      const validado = await validarDestinoContato(
        client,
        resolvido.chatId,
        resolvido.targetLabel,
        resolvido.source,
        true
      );

      if (validado) return validado;
    }
  }

  const fallbackId = getFallbackContactIdFromPhone();
  if (fallbackId) {
    const validado = await validarDestinoContato(
      client,
      fallbackId,
      contactPhone || fallbackId,
      'fallback-phone@c.us',
      true
    );

    if (validado) return validado;
  }

  throw new Error(
    `Não foi possível resolver o contato no WhatsApp: phone=${contactPhone || 'vazio'} contactId=${contactIdConfig || 'vazio'}`
  );
}

function montarLegenda() {
  if (!CONFIG.message.caption.enabled) return '';

  const linhas = [];

  if (CONFIG.message.caption.title.enabled && CONFIG.message.caption.title.text) {
    linhas.push(CONFIG.message.caption.title.text);
  }

  const mentionPhones = getMentionPhones();
  if (mentionPhones.length > 0) {
    linhas.push(mentionPhones.map(phone => `@${phone}`).join(' '));
  }

  if (CONFIG.message.caption.body.enabled && CONFIG.message.caption.body.text) {
    linhas.push(CONFIG.message.caption.body.text);
  }

  if (CONFIG.message.caption.execId.enabled) {
    linhas.push(
      `${CONFIG.message.caption.execId.label} ${EXEC_ID || CONFIG.message.caption.execId.fallback}`
    );
  }

  return linhas.join('\n').trim();
}

function montarOpcoesEnvio(enviarComAnexo) {
  const opcoes = {};
  const legenda = montarLegenda();
  const mentionIds = getMentionIds();

  if (enviarComAnexo && legenda) {
    opcoes.caption = legenda;
  }

  if (mentionIds.length > 0) {
    opcoes.mentions = mentionIds;
  }

  return opcoes;
}

async function enviarConteudo(client, destino) {
  const enviarComAnexo = CONFIG.message.sendAttachment;
  const legenda = montarLegenda();
  const opcoes = montarOpcoesEnvio(enviarComAnexo);

  if (enviarComAnexo) {
    if (!fs.existsSync(CONFIG.paths.attachmentPath)) {
      throw new ManagedError(
        `Anexo não encontrado: ${CONFIG.paths.attachmentPath}`,
        EXIT_CODES.MISSING_ATTACHMENT
      );
    }

    const media = MessageMedia.fromFilePath(CONFIG.paths.attachmentPath);
    return client.sendMessage(destino.chatId, media, opcoes);
  }

  if (!legenda) {
    throw new ManagedError(
      'Nada para enviar: legenda vazia e sendAttachment=false.',
      EXIT_CODES.INVALID_CONFIG
    );
  }

  return client.sendMessage(destino.chatId, legenda, opcoes);
}

function enriquecerErroLid(erro, destino) {
  const msg = String(erro?.message || erro || '');

  if (/No LID for user/i.test(msg)) {
    return new ManagedError(
      `No LID for user ao enviar para ${destino?.targetLabel || 'contato'} ` +
      `(origem=${destino?.source || 'desconhecida'}). ` +
      `Tente atualizar o whatsapp-web.js, recriar a sessão .wwebjs_auth e iniciar uma conversa manual com esse contato no WhatsApp antes do envio automatizado.`,
      EXIT_CODES.FINAL_ERROR
    );
  }

  return erro instanceof Error ? erro : new Error(msg);
}

async function destroyClientSilently(client) {
  if (!client) return;
  try {
    await client.destroy();
  } catch (erro) {
    escreverLog('NODE', `AVISO: Falha ao destruir client: ${formatarErro(erro)}`);
  }
}

async function enviarUmaTentativa(tentativa) {
  return new Promise(async (resolve, reject) => {
    let client = null;
    let timeoutSeguranca = null;
    let finalizado = false;
    let qrCount = 0;
    let authenticatedCount = 0;
    let readyCount = 0;
    let qrAbortRequested = false;
    let ultimoLoadingKey = '';
    const startedAt = Date.now();

    async function sucesso(resultado) {
      if (finalizado) return;
      finalizado = true;
      clearTimeout(timeoutSeguranca);
      await destroyClientSilently(client);
      resolve(resultado);
    }

    async function falha(erro) {
      if (finalizado) return;
      finalizado = true;
      clearTimeout(timeoutSeguranca);
      await destroyClientSilently(client);
      reject(erro);
    }

    async function abortarPorReautenticacao() {
      if (qrAbortRequested || finalizado) return;
      qrAbortRequested = true;

      escreverLog(
        'NODE',
        `REAUTH: QR recebido em modo silencioso (FORCE_VISIBLE=NAO). Sessao expirada/invalida. Abortando tentativa ${tentativa} imediatamente com ExitCode=${EXIT_CODES.REAUTH_REQUIRED}.`
      );

      await falha(
        new ManagedError(
          `Sessão salva encontrada, porém o WhatsApp exigiu QR em modo silencioso (tentativa=${tentativa}). ` +
          `Reautenticação interativa necessária. O BAT deve relançar em modo PAIRING.`,
          EXIT_CODES.REAUTH_REQUIRED
        )
      );
    }

    try {
      const sessionSnapshot = getSessionSnapshot();

      escreverLog(
        'NODE',
        `Tentativa ${tentativa}/${getMaxAttempts()} - Inicializando cliente WhatsApp. pid=${process.pid} node=${process.version}`
      );
      escreverLog(
        'NODE',
        `Runtime: cwd=${process.cwd()} | execId=${EXEC_ID || 'sem-exec-id'} | RUNTIME_MODE=${RUNTIME_MODE || 'vazio/AUTO'} | FORCE_VISIBLE=${FORCE_VISIBLE ? 'SIM' : 'NAO'} | headlessEfetivo=${FORCE_VISIBLE ? 'false(visivel)' : String(CONFIG.runtime.headless)}`
      );
      escreverLog(
        'NODE',
        `Sessao: exists=${sessionSnapshot.exists ? 'SIM' : 'NAO'} | files=${sessionSnapshot.fileCount} | dir=${sessionSnapshot.sessionDir}`
      );
      escreverLog(
        'NODE',
        `Config: clientId=${CONFIG.auth.clientId} | authDir=${CONFIG.paths.authDir} | maxAttempts=${getMaxAttempts()} | initTimeoutMs=${CONFIG.retry.initTimeoutMs}`
      );

      client = new Client({
        authStrategy: new LocalAuth({
          dataPath: CONFIG.paths.authDir,
          clientId: CONFIG.auth.clientId
        }),
        takeoverOnConflict: true,
        takeoverTimeoutMs: 5000,
        qrMaxRetries: 5,
        authTimeoutMs: 60000,
        puppeteer: {
          headless: FORCE_VISIBLE ? false : CONFIG.runtime.headless,
          args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu'
          ]
        }
      });

      client.on('qr', qr => {
        qrCount += 1;

        escreverLog(
          'NODE',
          `QR Code recebido. count=${qrCount} | telaVisivel=${FORCE_VISIBLE ? 'SIM' : 'NAO'} | tentativa=${tentativa}/${getMaxAttempts()} | elapsedMs=${Date.now() - startedAt}`
        );

        if (!FORCE_VISIBLE) {
          // Modo silencioso: QR = sessão inválida → abortar IMEDIATAMENTE
          // Não aguardar os 5 retries do qrMaxRetries (evita ~5 min de espera inútil)
          escreverLog(
            'NODE',
            `REAUTH: Modo silencioso (headless) e QR recebido no count=${qrCount}. Abortando imediatamente.`
          );
          void abortarPorReautenticacao();
          return;
        }

        // Modo visível (PAIRING): exibir QR no terminal
        if (CONFIG.terminal.showQr) {
          try {
            qrcode.generate(qr, { small: true });
            escreverLog('NODE', `QR Code exibido no terminal. count=${qrCount}`);
          } catch (erro) {
            escreverLog('NODE', `AVISO: Falha ao renderizar QR no terminal: ${formatarErro(erro)}`);
          }
        } else {
          escreverLog('NODE', `QR nao exibido (terminal.showQr=false). count=${qrCount}`);
        }

        escreverLog('NODE', 'Aguardando leitura do QR Code na janela visivel do navegador.');
      });

      client.on('authenticated', () => {
        authenticatedCount += 1;
        escreverLog(
          'NODE',
          `Sessão autenticada com sucesso. count=${authenticatedCount} | elapsedMs=${Date.now() - startedAt}`
        );
      });

      client.on('auth_failure', async msg => {
        await falha(
          new ManagedError(
            `FALHA DE AUTENTICACAO: ${msg}`,
            EXIT_CODES.FINAL_ERROR
          )
        );
      });

      client.on('disconnected', async reason => {
        if (!finalizado) {
          await falha(
            new ManagedError(
              `Cliente desconectado: ${reason}`,
              EXIT_CODES.FINAL_ERROR
            )
          );
        }
      });

      client.on('change_state', state => {
        escreverLog('NODE', `Estado do cliente alterado: ${state}`);
      });

      client.on('loading_screen', (percent, message) => {
        const key = `${percent}|${message}`;
        if (key !== ultimoLoadingKey) {
          ultimoLoadingKey = key;
          escreverLog('NODE', `Loading screen: ${percent}% | ${message}`);
        }
      });

      client.on('ready', async () => {
        let destino = null;
        readyCount += 1;

        try {
          escreverLog(
            'NODE',
            `Cliente WhatsApp pronto. readyCount=${readyCount} | elapsedMs=${Date.now() - startedAt}`
          );

          destino = await resolverDestino(client);
          escreverLog(
            'NODE',
            `Destino resolvido: tipo=${CONFIG.target.type}, alvo=${destino.targetLabel}, chatId=${destino.chatId}, origem=${destino.source}`
          );

          const retorno = await enviarConteudo(client, destino);
          const messageId = retorno?.id?._serialized || null;

          escreverLog(
            'NODE',
            `Envio concluído com sucesso para ${destino.targetLabel}. ID=${messageId || 'sem-id'}`
          );

          escreverLog('NODE', `Aguardando ${CONFIG.retry.sendSettleMs / 1000}s para estabilização do envio (settle).`);
          await sleep(CONFIG.retry.sendSettleMs);
          
          escreverLog('NODE', `Aguardando mais ${CONFIG.retry.finalWaitMs / 1000}s para sincronização multi-device antes de encerrar.`);
          await sleep(CONFIG.retry.finalWaitMs);

          await sucesso({ messageId, destino });
        } catch (erro) {
          await falha(enriquecerErroLid(erro, destino));
        }
      });

      timeoutSeguranca = setTimeout(async () => {
        await falha(
          new ManagedError(
            `TIMEOUT de segurança atingido. elapsedMs=${Date.now() - startedAt} | qrCount=${qrCount} | authenticatedCount=${authenticatedCount} | readyCount=${readyCount}`,
            EXIT_CODES.FINAL_ERROR
          )
        );
      }, CONFIG.retry.initTimeoutMs);

      escreverLog('NODE', 'Chamando client.initialize()...');
      await client.initialize();
      escreverLog('NODE', 'client.initialize() retornou controle para o processo.');
    } catch (erro) {
      await falha(erro);
    }
  });
}

async function shutdownWithLog(signal) {
  if (globalShutdownInProgress) return;
  globalShutdownInProgress = true;
  escreverLog('NODE', `Sinal recebido: ${signal}. Encerrando processo.`);
  process.exit(EXIT_CODES.FATAL);
}

process.on('SIGINT', () => {
  void shutdownWithLog('SIGINT');
});

process.on('SIGTERM', () => {
  void shutdownWithLog('SIGTERM');
});

process.on('uncaughtException', erro => {
  escreverLog('NODE', `UNCAUGHT_EXCEPTION: ${formatarErro(erro)}`);
  process.exit(erro?.exitCode || EXIT_CODES.FATAL);
});

process.on('unhandledRejection', motivo => {
  escreverLog('NODE', `UNHANDLED_REJECTION: ${formatarErro(motivo)}`);
  process.exit(motivo?.exitCode || EXIT_CODES.FATAL);
});

(async () => {
  try {
    if (!CONFIG.app.enabled) {
      escreverLog('NODE', 'AVISO: envio global desabilitado por configuração.');
      process.exit(EXIT_CODES.DISABLED);
    }

    validarConfig();

    escreverLog('NODE', `Arquivo de configuração carregado: ${CONFIG_FILE}`);
    escreverLog('NODE', `Diretório de autenticação: ${CONFIG.paths.authDir}`);
    escreverLog('NODE', `Diretório de sessão esperado: ${getSessionDir()}`);
    escreverLog('NODE', `Execução recebida: ${EXEC_ID || 'sem-exec-id'}`);
    escreverLog('NODE', `Destino configurado: ${CONFIG.target.type} -> ${getTargetLabel()}`);
    escreverLog('NODE', `Menções configuradas: ${getMentionPhones().join(', ') || 'nenhuma'}`);
    escreverLog(
      'NODE',
      `Resumo de runtime: headlessConfig=${CONFIG.runtime.headless ? 'SIM' : 'NAO'} | modoVisualEfetivo=${FORCE_VISIBLE ? 'SIM' : 'NAO'} | terminalShowQr=${CONFIG.terminal.showQr ? 'SIM' : 'NAO'} | maxAttempts=${getMaxAttempts()}`
    );

    if (CONFIG.message.sendAttachment) {
      if (!fs.existsSync(CONFIG.paths.attachmentPath)) {
        escreverLog('NODE', `ERRO: Arquivo de anexo não encontrado: ${CONFIG.paths.attachmentPath}`);
        process.exit(EXIT_CODES.MISSING_ATTACHMENT);
      }

      const sig = obterAssinaturaArquivo(CONFIG.paths.attachmentPath);
      escreverLog(
        'NODE',
        `Anexo validado: path=${CONFIG.paths.attachmentPath} | size=${sig.size} | mtimeMs=${sig.mtimeMs}`
      );
    } else {
      escreverLog('NODE', 'Envio sem anexo por configuração.');
    }

    const execKey = montarExecKey();
    const entregaKey = montarEntregaKey();
    escreverLog('NODE', `Chave de idempotência: ${execKey}`);
    escreverLog('NODE', `Chave de entrega: ${entregaKey}`);

    if (CONFIG.idempotency.enabled) {
      const falhaAnterior = obterFalhaAnterior(entregaKey);
      if (falhaAnterior) {
        escreverLog(
          'NODE',
          `Falha anterior registrada para a mesma entrega. lastFailureAt=${falhaAnterior.lastFailureAtBR || 'desconhecido'} | consecutiveFailures=${falhaAnterior.consecutiveFailures || 0} | nextRetryAt=${falhaAnterior.nextRetryAtBR || 'imediato'}`
        );

        const agoraMs = Date.now();
        const nextRetryEpoch = Number(falhaAnterior.nextRetryAtEpochMs || 0);
        if (nextRetryEpoch > agoraMs) {
          const esperaMs = nextRetryEpoch - agoraMs;
          escreverLog(
            'NODE',
            `Cooldown de retry ativo para esta entrega. Aguarde ${(esperaMs / 1000).toFixed(0)}s para nova tentativa.`
          );
          escreverLog(
            'NODE',
            `Encerrando sem novo envio para evitar duplicidade/race. ExitCode=${EXIT_CODES.COOLDOWN_ACTIVE}.`
          );
          process.exit(EXIT_CODES.COOLDOWN_ACTIVE);
        }
      }
    }

    if (CONFIG.idempotency.enabled && jaEnviado(execKey)) {
      escreverLog('NODE', `Execução já enviada anteriormente. Ignorando reenvio. ExecKey=${execKey}`);
      process.exit(EXIT_CODES.SUCCESS);
    }

    let ultimoErro = null;
    const maxAttempts = getMaxAttempts();

    for (let tentativa = 1; tentativa <= maxAttempts; tentativa++) {
      try {
        const { messageId, destino } = await enviarUmaTentativa(tentativa);

        if (CONFIG.idempotency.enabled) {
          marcarEnviado(execKey, messageId, destino);
          limparFalhaEntrega(entregaKey);
        }

        escreverLog('NODE', 'Processo de envio finalizado com sucesso.');
        process.exit(EXIT_CODES.SUCCESS);
      } catch (erro) {
        ultimoErro = erro;
        escreverLog('NODE', `Falha na tentativa ${tentativa}: ${formatarErro(erro)}`);

        if (erro?.exitCode === EXIT_CODES.REAUTH_REQUIRED) {
          if (CONFIG.idempotency.enabled) {
            registrarFalhaEntrega(execKey, entregaKey, erro, EXIT_CODES.REAUTH_REQUIRED, tentativa, maxAttempts);
          }

          escreverLog(
            'NODE',
            'Reautenticação interativa necessária. Encerrando com código específico para o BAT relançar em modo visível.'
          );
          process.exit(EXIT_CODES.REAUTH_REQUIRED);
        }

        if (/No LID for user/i.test(String(erro.message || ''))) {
          escreverLog(
            'NODE',
            'Erro de resolução LID detectado. Interrompendo novas tentativas para evitar retries inúteis.'
          );
          break;
        }

        if (tentativa < maxAttempts) {
          escreverLog(
            'NODE',
            `Aguardando ${CONFIG.retry.attemptDelayMs / 1000}s para nova tentativa.`
          );
          await sleep(CONFIG.retry.attemptDelayMs);
        }
      }
    }

    const finalCode = ultimoErro?.exitCode || EXIT_CODES.FINAL_ERROR;

    if (CONFIG.idempotency.enabled) {
      registrarFalhaEntrega(execKey, entregaKey, ultimoErro, finalCode, maxAttempts, maxAttempts);
    }

    escreverLog(
      'NODE',
      `ERRO FINAL: envio não concluído após ${maxAttempts} tentativas. ExitCode=${finalCode}. Motivo: ${ultimoErro ? formatarErro(ultimoErro) : 'desconhecido'}`
    );
    process.exit(finalCode);
  } catch (erro) {
    escreverLog('NODE', `ERRO FATAL: ${formatarErro(erro)}`);
    process.exit(erro?.exitCode || EXIT_CODES.FATAL);
  }
})();