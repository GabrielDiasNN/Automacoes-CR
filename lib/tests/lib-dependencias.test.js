// Guarda das dependencias Node de lib/ (motor WhatsApp). Le apenas arquivos do proprio repositorio:
// sem rede, sem npm install, sem tocar em node_modules. Falha se alguem reintroduzir o patch-package,
// quebrar o override para o fork do extract-zip, desalinhar o whatsapp-web.js ou regredir o basic-ftp.
// Cada mensagem de falha diz o que restaurar; as relacionadas ao lock trazem o procedimento de regeneracao.
//
// Por que o override usa "file:../../../vendor/extract-zip": o npm resolve override "file:" relativo a
// pasta do pacote que depende de extract-zip (node_modules/@puppeteer/browsers/), e nao a raiz de lib/.
// Por isso "file:vendor/extract-zip" quebra a regeneracao do lock (ENOENT), enquanto o prefixo ../../../
// aponta para lib/vendor/extract-zip. Dentro do lock, o no fica com resolved "file:vendor/extract-zip".
'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');

const LIB = path.join(__dirname, '..');

function lerJson(relativo) {
    return JSON.parse(fs.readFileSync(path.join(LIB, relativo), 'utf8'));
}

const PACKAGE = lerJson('package.json');
const LOCK = lerJson('package-lock.json');
const PACOTES = LOCK.packages;

const COMO_REGENERAR = [
    'Como regenerar o lock sem quebrar o fork do extract-zip:',
    '  1. copie lib/ (sem node_modules) para uma pasta temporaria;',
    '  2. remova o no "node_modules/extract-zip" do package-lock.json da copia;',
    '  3. rode "npm install --package-lock-only --ignore-scripts" na copia;',
    '  4. confira que o no volta com version 2.0.2-automacoes.1 e resolved "file:vendor/extract-zip";',
    '  5. copie o lock de volta para lib/, preservando CRLF.',
    'Se o npm reresolver extract-zip para outro caminho, restaure o bloco "node_modules/extract-zip"',
    'do lock anterior (git show) e rode "npm ci" numa copia limpa para validar.',
].join('\n');

// Compara apenas o nucleo major.minor.patch (ignora prerelease). Basta para as minimas exigidas aqui.
function compararCore(a, b) {
    const pa = a.split('-')[0].split('.').map(Number);
    const pb = b.split('-')[0].split('.').map(Number);
    for (let i = 0; i < 3; i++) {
        const d = (pa[i] || 0) - (pb[i] || 0);
        if (d !== 0) { return d; }
    }
    return 0;
}

// Nomes de pacote proibidos em lib/ e suas listas de dependencia, no lock inteiro.
const PROIBIDOS = ['braces', 'patch-package', 'qrcode-terminal'];

test('(a) package.json sem patch-package e com postinstall aplicar-patches', () => {
    const declarados = [
        ...Object.keys(PACKAGE.dependencies || {}),
        ...Object.keys(PACKAGE.devDependencies || {}),
        ...Object.keys(PACKAGE.optionalDependencies || {}),
    ];
    assert.ok(!declarados.includes('patch-package'),
        'lib/package.json declara patch-package de novo. O patch-package puxa braces/micromatch com CVE sem ' +
        'correcao: o postinstall deve ficar em "node scripts/aplicar-patches.js" (ver lib/README.md).');
    assert.equal(PACKAGE.scripts && PACKAGE.scripts.postinstall, 'node scripts/aplicar-patches.js',
        'postinstall de lib/package.json deve ser "node scripts/aplicar-patches.js" (substitui o patch-package).');
    assert.ok(fs.existsSync(path.join(LIB, 'scripts', 'aplicar-patches.js')),
        'lib/scripts/aplicar-patches.js nao existe: o postinstall depende dele.');
});

test('(b) override do extract-zip aponta para o fork em lib/vendor/extract-zip', () => {
    const override = PACKAGE.overrides && PACKAGE.overrides['extract-zip'];
    assert.ok(override, 'lib/package.json perdeu o override de extract-zip (deve apontar para o fork vendorizado).');
    assert.match(override, /^file:.*vendor\/extract-zip$/,
        `override de extract-zip deve ser "file:...vendor/extract-zip", encontrado "${override}".`);

    const fork = lerJson(path.join('vendor', 'extract-zip', 'package.json'));
    assert.equal(fork.name, 'extract-zip', 'lib/vendor/extract-zip/package.json nao declara name "extract-zip".');
    assert.match(fork.version, /^\d+\.\d+\.\d+-[0-9A-Za-z.-]+$/,
        `versao do fork deve ser prerelease (ex.: 2.0.2-automacoes.1), encontrada "${fork.version}".`);
    assert.ok(compararCore(fork.version, '2.0.1') > 0,
        `versao do fork (${fork.version}) deve ser maior que 2.0.1 (a que tem as CVEs de symlink/caminho).`);
});

test('(c) lock resolve node_modules/extract-zip para o fork e nao contem braces, patch-package nem qrcode-terminal', () => {
    const no = PACOTES['node_modules/extract-zip'];
    assert.ok(no, 'package-lock.json nao tem o no node_modules/extract-zip.\n' + COMO_REGENERAR);
    assert.equal(no.version, '2.0.2-automacoes.1',
        `lock resolve extract-zip para ${no.version}, esperado 2.0.2-automacoes.1.\n${COMO_REGENERAR}`);
    assert.equal(no.resolved, 'file:vendor/extract-zip',
        `lock resolve extract-zip para "${no.resolved}", esperado "file:vendor/extract-zip".\n${COMO_REGENERAR}`);

    for (const nome of PROIBIDOS) {
        const nos = Object.keys(PACOTES).filter((k) => k === `node_modules/${nome}` || k.endsWith(`/node_modules/${nome}`));
        assert.deepEqual(nos, [], `package-lock.json ainda contem o pacote "${nome}": ${nos.join(', ')}.\n${COMO_REGENERAR}`);

        for (const [chave, entrada] of Object.entries(PACOTES)) {
            const listas = ['dependencies', 'devDependencies', 'optionalDependencies', 'peerDependencies'];
            for (const lista of listas) {
                const dep = entrada[lista] && Object.prototype.hasOwnProperty.call(entrada[lista], nome);
                assert.ok(!dep, `o no "${chave || '(raiz)'}" do lock declara "${nome}" em ${lista}.\n${COMO_REGENERAR}`);
            }
        }
    }
});

test('(d) whatsapp-web.js exatamente 1.34.7 no package.json e no lock', () => {
    assert.equal(PACKAGE.dependencies['whatsapp-web.js'], '1.34.7',
        'lib/package.json deve fixar whatsapp-web.js em 1.34.7 (versao validada com o patch do lib/patches).');
    assert.equal(PACOTES[''].dependencies['whatsapp-web.js'], '1.34.7',
        'a raiz do package-lock.json deve declarar whatsapp-web.js 1.34.7.\n' + COMO_REGENERAR);
    assert.ok(PACOTES['node_modules/whatsapp-web.js'], 'package-lock.json nao tem node_modules/whatsapp-web.js.');
    assert.equal(PACOTES['node_modules/whatsapp-web.js'].version, '1.34.7',
        `lock resolve whatsapp-web.js para ${PACOTES['node_modules/whatsapp-web.js'].version}, esperado 1.34.7.\n${COMO_REGENERAR}`);
});

test('(e) basic-ftp >= 6.2.1 no override de lib/package.json e resolvido em versao >= 6.2.1 no lock, inclusive versoes aninhadas', () => {
    // O lock sozinho não basta: se o override sair (ou voltar para 5.x) e o lock ficar intacto, o npm ci deixa de
    // impor 6.2.1 sem que nenhum outro teste acuse. Por isso o override é conferido em lib/package.json também.
    const override = PACKAGE.overrides && PACKAGE.overrides['basic-ftp'];
    assert.ok(override, 'lib/package.json perdeu o override de basic-ftp. Restaure "overrides": { "basic-ftp": "6.2.1" }.\n' + COMO_REGENERAR);
    assert.match(override, /^\d+\.\d+\.\d+/, `override de basic-ftp malformado em lib/package.json: "${override}".`);
    assert.ok(compararCore(override, '6.2.1') >= 0,
        `override de basic-ftp em lib/package.json esta em ${override}, abaixo de 6.2.1. Restaure "6.2.1".\n${COMO_REGENERAR}`);

    const nos = Object.keys(PACOTES).filter((k) => k === 'node_modules/basic-ftp' || k.endsWith('/node_modules/basic-ftp'));
    assert.ok(nos.length > 0, 'package-lock.json nao contem basic-ftp.\n' + COMO_REGENERAR);
    for (const chave of nos) {
        const versao = PACOTES[chave].version;
        assert.match(versao, /^\d+\.\d+\.\d+/, `versao malformada de basic-ftp em "${chave}": ${versao}`);
        assert.ok(compararCore(versao, '6.2.1') >= 0,
            `basic-ftp em "${chave}" esta em ${versao}, abaixo de 6.2.1 (override de lib/package.json).\n${COMO_REGENERAR}`);
    }
});
