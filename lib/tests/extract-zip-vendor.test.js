// Testes do fork vendorizado do extract-zip (lib/vendor/extract-zip), com as correções de segurança para
// CVE-2026-19693 e CVE-2026-56876. Rodam offline, em diretórios temporários (fs.mkdtempSync), sem rede.
//
// Os zips de fixture são montados em memória por um escritor mínimo (método stored, CRC32 via zlib.crc32),
// porque as entradas maliciosas (symlinks para fora, nomes com "../") não são geradas por ferramentas normais.
//
// Dependências: yauzl, debug e get-stream são resolvidos a partir de lib/node_modules (transitivas do puppeteer).
// Se o módulo não carregar (dependência ausente, erro de sintaxe, caminho errado), cada caso REPROVA com o erro.
// Pular tudo de propósito exige EXTRACT_ZIP_PULAR_SEM_MODULO=1. Para provar a resolução isolada, rode numa cópia
// com as dependências instaladas (ver README.md desta pasta).
//
// Symlinks reais exigem privilégio no Windows (Modo de Desenvolvedor ou administrador). Sem ele, os casos que
// criam symlink são pulados com motivo explícito, exceto com a variável CI definida: aí reprovam, para que o CI
// nunca pule verificação de segurança em silêncio. Os casos de rejeição não criam symlink e rodam sempre.
//
// Prova de sensibilidade: EXTRACT_ZIP_MODULO aponta para outra implementação (ex.: o extract-zip 2.0.1 do npm),
// com NODE_PATH apontando para lib/node_modules (o original, fora de lib/, não acha as dependências sozinho).
// Os casos de ataque devem falhar contra o original, exceto o de nome com ".." (o yauzl já o recusa; ver README).
'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const zlib = require('zlib');

const MODULO = process.env.EXTRACT_ZIP_MODULO || path.join(__dirname, '..', 'vendor', 'extract-zip', 'index.js');

let extract = null;
let motivoSemModulo = null;
try {
    extract = require(MODULO);
} catch (err) {
    motivoSemModulo = `módulo não carregou (${MODULO}): ${err.message}`;
}

const MOTIVO_SEM_SYMLINK = 'criar symlink exige Modo de Desenvolvedor ou administrador no Windows (EPERM)';
const PULAR_SEM_MODULO = process.env.EXTRACT_ZIP_PULAR_SEM_MODULO === '1';
const EM_CI = process.env.CI !== undefined;

function suportaSymlink() {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'extract-zip-probe-'));
    try {
        fs.writeFileSync(path.join(dir, 'alvo.txt'), '');
        fs.symlinkSync('alvo.txt', path.join(dir, 'link.txt'));
        return true;
    } catch {
        return false;
    } finally {
        fs.rmSync(dir, { recursive: true, force: true, maxRetries: 3 });
    }
}

const SUPORTA_SYMLINK = suportaSymlink();

// Registra um caso de teste, em três situações (nesta ordem):
//  - o módulo não carregou: o caso REPROVA com o erro de carregamento; só pula com EXTRACT_ZIP_PULAR_SEM_MODULO=1;
//  - `simbolico: true` sem privilégio de symlink: pula com motivo explícito, mas REPROVA quando CI está definido;
//  - caso normal: roda.
function caso(nome, { simbolico = false } = {}, fn) {
    if (motivoSemModulo) {
        if (PULAR_SEM_MODULO) {
            test(nome, { skip: motivoSemModulo }, fn);
        } else {
            test(nome, () => { throw new Error(`fork não carregou: ${motivoSemModulo}`); });
        }
        return;
    }
    if (simbolico && !SUPORTA_SYMLINK) {
        if (EM_CI) {
            test(nome, () => { throw new Error(`${MOTIVO_SEM_SYMLINK}; em CI este caso reprova em vez de pular`); });
        } else {
            test(nome, { skip: `${MOTIVO_SEM_SYMLINK}; caso pulado` }, fn);
        }
        return;
    }
    test(nome, fn);
}

const MODO_ARQUIVO = 0o100644;
const MODO_EXECUTAVEL = 0o100755;
const MODO_DIRETORIO = 0o040755;
const MODO_SYMLINK = 0o120777;

// Monta um zip (método stored) com entradas { nome, dados, modo }. Nomes que terminam em "/" são diretórios.
function montarZip(entradas) {
    const partes = [];
    const centrais = [];
    let offset = 0;

    for (const { nome, dados = '', modo = MODO_ARQUIVO } of entradas) {
        const nomeBuf = Buffer.from(nome, 'utf8');
        const dadosBuf = Buffer.isBuffer(dados) ? dados : Buffer.from(dados, 'utf8');
        const crc = zlib.crc32(dadosBuf);
        const ehDiretorio = nome.endsWith('/');
        // Modo Unix nos 16 bits altos; bit 0x10 marca diretório no atributo DOS.
        const atributos = ((modo << 16) | (ehDiretorio ? 0x10 : 0)) >>> 0;

        const local = Buffer.alloc(30);
        local.writeUInt32LE(0x04034b50, 0);
        local.writeUInt16LE(20, 4);
        local.writeUInt16LE(0x0800, 6);
        local.writeUInt16LE(0, 8);
        local.writeUInt16LE(0, 10);
        local.writeUInt16LE(0x21, 12);
        local.writeUInt32LE(crc, 14);
        local.writeUInt32LE(dadosBuf.length, 18);
        local.writeUInt32LE(dadosBuf.length, 22);
        local.writeUInt16LE(nomeBuf.length, 26);
        local.writeUInt16LE(0, 28);
        partes.push(local, nomeBuf, dadosBuf);

        const central = Buffer.alloc(46);
        central.writeUInt32LE(0x02014b50, 0);
        central.writeUInt16LE((3 << 8) | 20, 4); // criado em Unix
        central.writeUInt16LE(20, 6);
        central.writeUInt16LE(0x0800, 8);
        central.writeUInt16LE(0, 10);
        central.writeUInt16LE(0, 12);
        central.writeUInt16LE(0x21, 14);
        central.writeUInt32LE(crc, 16);
        central.writeUInt32LE(dadosBuf.length, 20);
        central.writeUInt32LE(dadosBuf.length, 24);
        central.writeUInt16LE(nomeBuf.length, 28);
        central.writeUInt16LE(0, 30);
        central.writeUInt16LE(0, 32);
        central.writeUInt16LE(0, 34);
        central.writeUInt16LE(0, 36);
        central.writeUInt32LE(atributos, 38);
        central.writeUInt32LE(offset, 42);
        centrais.push(central, nomeBuf);

        offset += local.length + nomeBuf.length + dadosBuf.length;
    }

    const diretorioCentral = Buffer.concat(centrais);
    const fim = Buffer.alloc(22);
    fim.writeUInt32LE(0x06054b50, 0);
    fim.writeUInt16LE(entradas.length, 8);
    fim.writeUInt16LE(entradas.length, 10);
    fim.writeUInt32LE(diretorioCentral.length, 12);
    fim.writeUInt32LE(offset, 16);
    return Buffer.concat([...partes, diretorioCentral, fim]);
}

function ambiente() {
    const base = fs.mkdtempSync(path.join(os.tmpdir(), 'extract-zip-vendor-'));
    return { base, dest: path.join(base, 'dest'), zip: path.join(base, 'entrada.zip') };
}

function limpar(amb) {
    fs.rmSync(amb.base, { recursive: true, force: true, maxRetries: 3 });
}

// Grava o zip e extrai em amb.dest (que ainda não existe; a própria extração o cria).
async function extrair(amb, entradas, opcoes = {}) {
    fs.writeFileSync(amb.zip, montarZip(entradas));
    return extract(amb.zip, { dir: amb.dest, ...opcoes });
}

// Verifica existência de entrada no disco sem seguir symlink (existsSync falha em links quebrados).
function temEntrada(caminho) {
    try {
        fs.lstatSync(caminho);
        return true;
    } catch {
        return false;
    }
}

caso('zip legítimo: subdiretórios, executável e nome com ".." no meio extraem como esperado', {}, async () => {
    const amb = ambiente();
    try {
        await extrair(amb, [
            { nome: 'raiz/', modo: MODO_DIRETORIO },
            { nome: 'raiz/sub/', modo: MODO_DIRETORIO },
            { nome: 'raiz/sub/texto.txt', dados: 'olá, mundo' },
            { nome: 'raiz/bin/run.sh', dados: '#!/bin/sh\necho ok\n', modo: MODO_EXECUTAVEL },
            { nome: 'raiz/..nota.txt', dados: 'nota' },
        ]);
        assert.ok(fs.statSync(path.join(amb.dest, 'raiz', 'sub')).isDirectory());
        assert.equal(fs.readFileSync(path.join(amb.dest, 'raiz', 'sub', 'texto.txt'), 'utf8'), 'olá, mundo');
        assert.equal(fs.readFileSync(path.join(amb.dest, 'raiz', 'bin', 'run.sh'), 'utf8'), '#!/bin/sh\necho ok\n');
        assert.equal(fs.readFileSync(path.join(amb.dest, 'raiz', '..nota.txt'), 'utf8'), 'nota');
        if (process.platform !== 'win32') {
            const modoRun = fs.statSync(path.join(amb.dest, 'raiz', 'bin', 'run.sh')).mode;
            assert.notEqual(modoRun & 0o111, 0, 'arquivo executável perdeu o bit de execução');
        }
    } finally {
        limpar(amb);
    }
});

caso('symlink com alvo relativo seguro, que sai de sub/ e volta ao destino, é aceito', { simbolico: true }, async () => {
    const amb = ambiente();
    try {
        await extrair(amb, [
            { nome: 'sub/', modo: MODO_DIRETORIO },
            { nome: 'alvo.txt', dados: 'conteúdo' },
            { nome: 'sub/link.txt', dados: '../alvo.txt', modo: MODO_SYMLINK },
        ]);
        const link = path.join(amb.dest, 'sub', 'link.txt');
        assert.ok(fs.lstatSync(link).isSymbolicLink());
        assert.equal(fs.readFileSync(link, 'utf8'), 'conteúdo');
    } finally {
        limpar(amb);
    }
});

caso('cadeia de symlinks que fica dentro do destino é aceita (padrão de bundles macOS)', { simbolico: true }, async () => {
    const amb = ambiente();
    try {
        await extrair(amb, [
            { nome: 'd/', modo: MODO_DIRETORIO },
            { nome: 'd/alvo.txt', dados: 'conteúdo' },
            { nome: 'lk1', dados: 'd', modo: MODO_SYMLINK },
            { nome: 'lk2', dados: 'lk1', modo: MODO_SYMLINK },
        ]);
        assert.ok(fs.lstatSync(path.join(amb.dest, 'lk2')).isSymbolicLink());
        // lk2 -> lk1 -> d: lk2 é link de diretório, então lk2/alvo.txt lê d/alvo.txt pela cadeia.
        // Leitura pela cadeia só é verificada fora do Windows. Lá, lk1 aponta para "d", que já existe quando o link
        // é criado, então o Node o cria com tipo "dir" sozinho (a limitação herdada só vale para alvo inexistente).
        // Essa leitura com privilégio no Windows ainda não foi confirmada; o guard sai quando for.
        if (process.platform !== 'win32') {
            assert.equal(fs.readFileSync(path.join(amb.dest, 'lk2', 'alvo.txt'), 'utf8'), 'conteúdo');
        }
    } finally {
        limpar(amb);
    }
});

caso('symlink com alvo absoluto é rejeitado e nada é criado', {}, async () => {
    const amb = ambiente();
    try {
        const fora = path.join(amb.base, 'fora.txt');
        await assert.rejects(
            extrair(amb, [{ nome: 'abs', dados: fora, modo: MODO_SYMLINK }]),
            /alvo absoluto/,
        );
        assert.equal(fs.existsSync(fora), false);
        assert.equal(temEntrada(path.join(amb.dest, 'abs')), false);
    } finally {
        limpar(amb);
    }
});

caso('symlink com alvo que começa por unidade (C:) é rejeitado em qualquer plataforma', {}, async () => {
    const amb = ambiente();
    try {
        await assert.rejects(
            extrair(amb, [{ nome: 'un', dados: 'C:\\Windows\\win.ini', modo: MODO_SYMLINK }]),
            /alvo absoluto/,
        );
        assert.equal(temEntrada(path.join(amb.dest, 'un')), false);
    } finally {
        limpar(amb);
    }
});

caso('symlink com alvo "../../fora.txt", que sai do destino, é rejeitado', {}, async () => {
    const amb = ambiente();
    try {
        await assert.rejects(
            extrair(amb, [
                { nome: 'sub/', modo: MODO_DIRETORIO },
                { nome: 'sub/link', dados: '../../fora.txt', modo: MODO_SYMLINK },
            ]),
            /aponta para fora do diretório de extração/,
        );
        assert.equal(fs.existsSync(path.join(amb.base, 'fora.txt')), false);
        assert.equal(temEntrada(path.join(amb.dest, 'sub', 'link')), false);
    } finally {
        limpar(amb);
    }
});

caso('symlink para fora seguido de arquivo de mesmo nome: a primeira entrada é rejeitada e nada é gravado fora', {}, async () => {
    const amb = ambiente();
    try {
        await assert.rejects(
            extrair(amb, [
                { nome: 'x', dados: '../fora.txt', modo: MODO_SYMLINK },
                { nome: 'x', dados: 'PWNED' },
            ]),
            /aponta para fora do diretório de extração/,
        );
        assert.equal(fs.existsSync(path.join(amb.base, 'fora.txt')), false);
        assert.equal(temEntrada(path.join(amb.dest, 'x')), false);
    } finally {
        limpar(amb);
    }
});

caso('arquivo regular sobre symlink de mesmo nome é rejeitado e não segue o link', { simbolico: true }, async () => {
    const amb = ambiente();
    try {
        await assert.rejects(
            extrair(amb, [
                { nome: 'real.txt', dados: 'original' },
                { nome: 'alias', dados: 'real.txt', modo: MODO_SYMLINK },
                { nome: 'alias', dados: 'SOBRESCRITO' },
            ]),
            /já existe como symlink/,
        );
        assert.equal(fs.readFileSync(path.join(amb.dest, 'real.txt'), 'utf8'), 'original');
    } finally {
        limpar(amb);
    }
});

caso('symlink que escapa seguindo outro symlink ("a" -> "." e "b" -> "a/../x") é rejeitado', { simbolico: true }, async () => {
    const amb = ambiente();
    try {
        await assert.rejects(
            extrair(amb, [
                { nome: 'a', dados: '.', modo: MODO_SYMLINK },
                { nome: 'b', dados: 'a/../x', modo: MODO_SYMLINK },
            ]),
            /aponta para fora do diretório de extração/,
        );
        assert.equal(fs.existsSync(path.join(amb.base, 'x')), false);
    } finally {
        limpar(amb);
    }
});

caso('".." logo após componente inexistente no alvo é rejeitado como não verificável', {}, async () => {
    const amb = ambiente();
    try {
        await assert.rejects(
            extrair(amb, [{ nome: 'y', dados: 'novo/../x', modo: MODO_SYMLINK }]),
            /não verificável/,
        );
        assert.equal(temEntrada(path.join(amb.dest, 'y')), false);
    } finally {
        limpar(amb);
    }
});

// O yauzl (decodeStrings padrão) já recusa nomes com ".." ("invalid relative path") antes do fork. A checagem
// própria do fork é defesa em profundidade; o que este caso garante é a propriedade essencial: nada fora do destino.
caso('entrada com "../" no nome é rejeitada antes de criar diretórios fora do destino', {}, async () => {
    const amb = ambiente();
    try {
        await assert.rejects(
            extrair(amb, [{ nome: '../fora-dir/a/b/evil.txt', dados: 'x' }]),
            /resolve para fora do diretório de extração|invalid relative path/,
        );
        assert.equal(fs.existsSync(path.join(amb.base, 'fora-dir')), false);
    } finally {
        limpar(amb);
    }
});

caso('prefixo-irmão ("../dest-evil") não passa como se estivesse dentro de "dest"', {}, async () => {
    const amb = ambiente();
    try {
        await assert.rejects(
            extrair(amb, [{ nome: 'link', dados: '../dest-evil/alvo.txt', modo: MODO_SYMLINK }]),
            /aponta para fora do diretório de extração/,
        );
        assert.equal(fs.existsSync(path.join(amb.base, 'dest-evil')), false);
    } finally {
        limpar(amb);
    }
});

// Junção pré-existente no destino (ancestral que já existia antes da extração). Não exige privilégio no Windows;
// fora do Windows vira symlink comum. Para fora do destino, nada pode ser criado lá, nem os diretórios intermediários.
caso('ancestral pré-existente que é junção para fora: nada é criado fora, antes da rejeição', {}, async () => {
    const amb = ambiente();
    try {
        const fora = path.join(amb.base, 'outside');
        fs.mkdirSync(fora);
        fs.mkdirSync(amb.dest);
        fs.symlinkSync(fora, path.join(amb.dest, 'out'), 'junction');
        await assert.rejects(
            extrair(amb, [{ nome: 'out/novo/arq.txt', dados: 'x' }]),
            /Out of bound path/,
        );
        assert.equal(fs.existsSync(path.join(fora, 'novo')), false, 'diretório criado fora do destino pelo mkdir');
    } finally {
        limpar(amb);
    }
});

caso('ancestral pré-existente que é junção para dentro do destino: extração legítima continua funcionando', {}, async () => {
    const amb = ambiente();
    try {
        fs.mkdirSync(amb.dest);
        fs.mkdirSync(path.join(amb.dest, 'real'));
        fs.symlinkSync(path.join(amb.dest, 'real'), path.join(amb.dest, 'j'), 'junction');
        await extrair(amb, [{ nome: 'j/novo/arq.txt', dados: 'ok' }]);
        assert.equal(fs.readFileSync(path.join(amb.dest, 'real', 'novo', 'arq.txt'), 'utf8'), 'ok');
    } finally {
        limpar(amb);
    }
});

// Entrada de diretório "out/" sobre junção pré-existente para fora. Em POSIX, lstat com barra final segue o link:
// sem tirar a barra final, a guarda não rejeitaria e o mkdir seria no-op sobre o alvo externo. No Windows a junção
// já era rejeitada antes do ajuste; o caso existe para pegar essa divergência entre plataformas. Sem privilégio de symlink.
caso('entrada de diretório "out/" sobre junção pré-existente para fora é rejeitada em qualquer plataforma', {}, async () => {
    const amb = ambiente();
    try {
        const fora = path.join(amb.base, 'outside');
        fs.mkdirSync(fora);
        fs.mkdirSync(amb.dest);
        fs.symlinkSync(fora, path.join(amb.dest, 'out'), 'junction');
        await assert.rejects(
            extrair(amb, [{ nome: 'out/', modo: MODO_DIRETORIO }]),
            /já existe como symlink/,
        );
        assert.deepEqual(fs.readdirSync(fora), [], 'a entrada de diretório mexeu no alvo externo do link');
    } finally {
        limpar(amb);
    }
});

caso('cadeia de 32 links que se repete é rejeitada logo, sem custo exponencial', {}, async () => {
    // Árvore de links virtual: s0 -> "s1/s1", ..., s31 -> ".". Cada componente que é link se repete na resolução, então
    // sem orçamento o custo dobraria a cada nível. Os links são simulados em lstat/readlink, então o caso roda sem
    // privilégio de symlink (inclusive no Windows local).
    const amb = ambiente();
    const LIMITE_DE_CHAMADAS = 1000; // medido com o orçamento de saltos: 93 chamadas; o teto deixa folga
    const CORTE = 200000; // o código sem orçamento passa disso: o corte faz o caso reprovar em uns 10 s, sem travar
    const lstatOriginal = fs.promises.lstat;
    const readlinkOriginal = fs.promises.readlink;
    let chamadas = 0;
    try {
        fs.mkdirSync(amb.dest);
        // realpath nativo, o mesmo que o módulo usa (promises.realpath). No Windows o JS difere no nome curto (GABRIE~1).
        const real = fs.realpathSync.native(amb.dest);
        const virtuais = new Map();
        for (let k = 0; k < 32; k++) {
            virtuais.set(path.join(real, `s${k}`), k === 31 ? '.' : `s${k + 1}/s${k + 1}`);
        }
        const contar = () => {
            chamadas += 1;
            if (chamadas > CORTE) {
                throw Object.assign(new Error('corte do teste: resolução sem limite de custo'), { code: 'CORTE_DO_TESTE' });
            }
        };
        fs.promises.lstat = async (caminho, ...resto) => {
            contar();
            if (virtuais.has(caminho)) return { isSymbolicLink: () => true, isDirectory: () => false };
            return lstatOriginal.call(fs.promises, caminho, ...resto);
        };
        fs.promises.readlink = async (caminho, ...resto) => {
            contar();
            if (virtuais.has(caminho)) return virtuais.get(caminho);
            return readlinkOriginal.call(fs.promises, caminho, ...resto);
        };

        let erro = null;
        try {
            await extrair(amb, [{ nome: 'lk', dados: 's0/s0', modo: MODO_SYMLINK }]);
        } catch (err) {
            erro = err;
        }
        assert.ok(erro, 'a extração devia ser rejeitada');
        assert.match(erro.message, /cadeia de links longa demais/);
        assert.ok(chamadas <= LIMITE_DE_CHAMADAS, `${chamadas} chamadas ao fs; o custo voltou a crescer sem limite`);
        assert.equal(temEntrada(path.join(real, 'lk')), false);
    } finally {
        fs.promises.lstat = lstatOriginal;
        fs.promises.readlink = readlinkOriginal;
        limpar(amb);
    }
});

caso('link pré-existente com alvo absoluto dentro do destino é recusado, e a mensagem diz que o link vem do disco', {}, async () => {
    const amb = ambiente();
    try {
        fs.mkdirSync(amb.dest);
        fs.mkdirSync(path.join(amb.dest, 'real'));
        fs.symlinkSync(path.join(amb.dest, 'real'), path.join(amb.dest, 'j'), 'junction');
        await assert.rejects(
            extrair(amb, [{ nome: 'k', dados: 'j/f', modo: MODO_SYMLINK }]),
            /link pré-existente "j" com alvo absoluto .*\(rejeitado/,
        );
        assert.equal(temEntrada(path.join(amb.dest, 'k')), false);
    } finally {
        limpar(amb);
    }
});

caso('opts.dir relativo continua rejeitado (API pública preservada)', {}, async () => {
    await assert.rejects(
        extract(path.join(os.tmpdir(), 'inexistente.zip'), { dir: 'relativo' }),
        /absolute/,
    );
});

caso('onEntry é chamado para cada entrada aceita (API pública preservada)', {}, async () => {
    const amb = ambiente();
    const vistos = [];
    try {
        await extrair(
            amb,
            [{ nome: 'a.txt', dados: 'a' }, { nome: 'pasta/b.txt', dados: 'b' }],
            { onEntry: entry => vistos.push(entry.fileName) },
        );
        assert.deepEqual(vistos, ['a.txt', 'pasta/b.txt']);
    } finally {
        limpar(amb);
    }
});
