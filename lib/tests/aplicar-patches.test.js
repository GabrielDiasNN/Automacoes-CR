// Testes do aplicador de patches (lib/scripts/aplicar-patches.js), que substitui o patch-package
// no postinstall de lib/. Rodam 100% offline, em diretórios temporários (fs.mkdtempSync), sem
// rede e sem tocar em node_modules real. O casamento é estrito: cada hunk é verificado só na
// posição do cabeçalho, sem deslocamento.
'use strict';

const { test, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const { aplicarPatches, analisarPatch, resolverAlvo, ErroPatch } = require('../scripts/aplicar-patches.js');

const PATCH_REAL = path.join(__dirname, '..', 'patches', 'whatsapp-web.js+1.34.7.patch');

let base; // diretório temporário do teste
let raiz; // equivalente a lib/ (contém node_modules/ e patches/)
let dirPatches;

beforeEach(() => {
    base = fs.mkdtempSync(path.join(os.tmpdir(), 'aplicar-patches-'));
    raiz = path.join(base, 'lib');
    dirPatches = path.join(raiz, 'patches');
    fs.mkdirSync(path.join(raiz, 'node_modules', 'pkg'), { recursive: true });
    fs.mkdirSync(dirPatches, { recursive: true });
});

afterEach(() => {
    // maxRetries: o Windows pode manter um arquivo travado por um instante (antivírus, indexação).
    fs.rmSync(base, { recursive: true, force: true, maxRetries: 3 });
});

function escrever(caminhoRelativo, conteudo) {
    const absoluto = path.join(raiz, ...caminhoRelativo.split('/'));
    fs.mkdirSync(path.dirname(absoluto), { recursive: true });
    fs.writeFileSync(absoluto, conteudo, 'utf8');
}

function ler(caminhoRelativo) {
    return fs.readFileSync(path.join(raiz, ...caminhoRelativo.split('/')));
}

function patch(nome, linhas) {
    fs.writeFileSync(path.join(dirPatches, nome), `${linhas.join('\n')}\n`, 'utf8');
}

function aplicar() {
    return aplicarPatches({ raiz, diretorioPatches: dirPatches });
}

const ALVO_BASICO = 'node_modules/pkg/mod.js';
const ORIGINAL_BASICO = ['function a() {', '    return 1;', '}', '', 'module.exports = a;', ''].join('\n');
const ESPERADO_BASICO = ['function a() {', '    return 2;', '    // novo', '}', '', 'module.exports = a;', ''].join('\n');
const PATCH_BASICO = [
    'diff --git a/node_modules/pkg/mod.js b/node_modules/pkg/mod.js',
    'index 1111111..2222222 100644',
    '--- a/node_modules/pkg/mod.js',
    '+++ b/node_modules/pkg/mod.js',
    '@@ -1,5 +1,6 @@',
    ' function a() {',
    '-    return 1;',
    '+    return 2;',
    '+    // novo',
    ' }',
    ' ',
    ' module.exports = a;',
];

test('aplica um hunk simples e grava o resultado', () => {
    escrever(ALVO_BASICO, ORIGINAL_BASICO);
    patch('0001-basico.patch', PATCH_BASICO);

    const resultados = aplicar();

    assert.deepEqual(resultados, [{ patch: '0001-basico.patch', caminho: ALVO_BASICO, status: 'aplicado' }]);
    assert.equal(ler(ALVO_BASICO).toString('utf8'), ESPERADO_BASICO);
});

test('segunda execução é idempotente: reporta já aplicado e não altera o arquivo byte a byte', () => {
    escrever(ALVO_BASICO, ORIGINAL_BASICO);
    patch('0001-basico.patch', PATCH_BASICO);
    aplicar();
    const antes = ler(ALVO_BASICO);

    const resultados = aplicar();

    assert.equal(resultados[0].status, 'ja-aplicado');
    assert.deepEqual(ler(ALVO_BASICO), antes);
});

test('contexto divergente falha com erro claro e não altera o arquivo', () => {
    escrever(ALVO_BASICO, ORIGINAL_BASICO.replace('return 1;', 'return 9;'));
    patch('0001-basico.patch', PATCH_BASICO);
    const antes = ler(ALVO_BASICO);

    assert.throws(
        () => aplicar(),
        (e) => e instanceof ErroPatch && /não casa/.test(e.message) && /0001-basico\.patch/.test(e.message),
    );
    assert.deepEqual(ler(ALVO_BASICO), antes);
});

// Substitui o antigo "tolera deslocamento": por desenho, linhas acrescidas acima do contexto são erro.
test('linhas acrescidas acima do contexto são erro: o casamento só vale na posição do cabeçalho', () => {
    const prefixo = '// topo 1\n// topo 2\n// topo 3\n';
    escrever(ALVO_BASICO, prefixo + ORIGINAL_BASICO);
    patch('0001-basico.patch', PATCH_BASICO);
    const antes = ler(ALVO_BASICO);

    assert.throws(() => aplicar(), (e) => e instanceof ErroPatch && /não casa/.test(e.message));
    assert.deepEqual(ler(ALVO_BASICO), antes);
});

// Substitui o antigo "casa em mais de um lugar da janela": sem janela, o bloco repetido não é ambíguo.
test('bloco repetido no arquivo: o hunk é aplicado só no ponto do cabeçalho', () => {
    escrever(ALVO_BASICO, `${ORIGINAL_BASICO}\n${ORIGINAL_BASICO}`);
    patch('0001-basico.patch', PATCH_BASICO);

    assert.equal(aplicar()[0].status, 'aplicado');
    assert.equal(ler(ALVO_BASICO).toString('utf8'), `${ESPERADO_BASICO}\n${ORIGINAL_BASICO}`);
});

test('preserva CRLF do arquivo, inclusive nas linhas inseridas', () => {
    escrever(ALVO_BASICO, ORIGINAL_BASICO.replace(/\n/g, '\r\n'));
    patch('0001-basico.patch', PATCH_BASICO); // patch com LF

    aplicar();

    assert.equal(ler(ALVO_BASICO).toString('utf8'), ESPERADO_BASICO.replace(/\n/g, '\r\n'));
});

test('patch com CRLF casa com arquivo LF e mantém LF', () => {
    escrever(ALVO_BASICO, ORIGINAL_BASICO);
    fs.writeFileSync(path.join(dirPatches, '0001-basico.patch'), `${PATCH_BASICO.join('\r\n')}\r\n`, 'utf8');

    aplicar();

    assert.equal(ler(ALVO_BASICO).toString('utf8'), ESPERADO_BASICO);
});

test('recusa caminhos que saem da raiz (../ e absolutos) sem tocar em nada fora dela', () => {
    fs.writeFileSync(path.join(base, 'fora.js'), 'SENTINELA\n', 'utf8');
    const variantes = [
        ['--- a/../fora.js', '+++ b/../fora.js'],
        ['--- a/node_modules/../../fora.js', '+++ b/node_modules/../../fora.js'],
        ['--- a/node_modules/pkg/../../../fora.js', '+++ b/node_modules/pkg/../../../fora.js'],
        ['--- /etc/passwd', '+++ b//etc/passwd'],
        ['--- a/C:/fora.js', '+++ b/C:/fora.js'],
    ];

    for (const [antigo, novo] of variantes) {
        patch('0009-traversal.patch', [antigo, novo, '@@ -1,2 +1,2 @@', '-SENTINELA', '+X', ' OUTRA']);
        assert.throws(
            () => aplicar(),
            (e) => e instanceof ErroPatch && /caminho recusado/.test(e.message),
            `variante: ${antigo}`,
        );
    }
    assert.equal(fs.readFileSync(path.join(base, 'fora.js'), 'utf8'), 'SENTINELA\n');
});

// Segunda camada (resolverAlvo), que não depende da validação léxica do parser.
test('resolverAlvo recusa caminho que sai da raiz e aceita caminho interno', () => {
    assert.throws(
        () => resolverAlvo(path.resolve(raiz), '../fora.js'),
        (e) => e instanceof ErroPatch && /fora da raiz/.test(e.message),
    );
    assert.equal(
        resolverAlvo(path.resolve(raiz), 'node_modules/pkg/x.js'),
        path.join(path.resolve(raiz), 'node_modules', 'pkg', 'x.js'),
    );
});

// Diretório linkado (junction no Windows, que não exige privilégio; symlink nos demais sistemas)
// dentro da raiz, apontando para fora dela: o arquivo alvo resolve para fora e deve ser recusado.
test('link simbólico dentro da raiz que aponta para fora é recusado', () => {
    const foraDir = path.join(base, 'fora');
    fs.mkdirSync(foraDir);
    fs.writeFileSync(path.join(foraDir, 'x.js'), 'SENTINELA\n', 'utf8');
    fs.symlinkSync(foraDir, path.join(raiz, 'node_modules', 'pkg', 'linkdir'), 'junction');
    patch('0005-symlink.patch', [
        '--- a/node_modules/pkg/linkdir/x.js',
        '+++ b/node_modules/pkg/linkdir/x.js',
        '@@ -1,2 +1,2 @@',
        '-SENTINELA',
        '+X',
        ' OUTRA',
    ]);

    assert.throws(
        () => aplicar(),
        (e) => e instanceof ErroPatch && /link simbólico/.test(e.message),
    );
    assert.equal(fs.readFileSync(path.join(foraDir, 'x.js'), 'utf8'), 'SENTINELA\n');
});

test('patch com dois arquivos e dois hunks no mesmo arquivo', () => {
    const modOriginal = `${Array.from({ length: 20 }, (_, i) => `linha ${String(i + 1).padStart(2, '0')}`).join('\n')}\n`;
    escrever('node_modules/pkg/mod.js', modOriginal);
    escrever('node_modules/pkg/other.js', 'alfa\nbeta\ngama\n');
    patch('0002-multi.patch', [
        'diff --git a/node_modules/pkg/mod.js b/node_modules/pkg/mod.js',
        '--- a/node_modules/pkg/mod.js',
        '+++ b/node_modules/pkg/mod.js',
        '@@ -1,3 +1,3 @@',
        ' linha 01',
        '-linha 02',
        '+linha dois',
        ' linha 03',
        '@@ -14,3 +14,4 @@',
        ' linha 14',
        '-linha 15',
        '+linha quinze',
        '+linha quinze b',
        ' linha 16',
        'diff --git a/node_modules/pkg/other.js b/node_modules/pkg/other.js',
        '--- a/node_modules/pkg/other.js',
        '+++ b/node_modules/pkg/other.js',
        '@@ -1,3 +1,3 @@',
        ' alfa',
        '-beta',
        '+BETA',
        ' gama',
    ]);

    const textoPatch = fs.readFileSync(path.join(dirPatches, '0002-multi.patch'), 'utf8');
    const arquivos = analisarPatch(textoPatch, '0002-multi.patch');
    assert.deepEqual(arquivos.map((a) => [a.caminho, a.hunks.length]), [
        ['node_modules/pkg/mod.js', 2],
        ['node_modules/pkg/other.js', 1],
    ]);

    const resultados = aplicar();

    assert.deepEqual(resultados.map((r) => [r.caminho, r.status]), [
        ['node_modules/pkg/mod.js', 'aplicado'],
        ['node_modules/pkg/other.js', 'aplicado'],
    ]);
    assert.equal(
        ler('node_modules/pkg/mod.js').toString('utf8'),
        modOriginal.replace('linha 02', 'linha dois').replace('linha 15', 'linha quinze\nlinha quinze b'),
    );
    assert.equal(ler('node_modules/pkg/other.js').toString('utf8'), 'alfa\nBETA\ngama\n');
});

test('falha em um patch não grava nenhum arquivo, nem os dos patches anteriores', () => {
    escrever('node_modules/pkg/a.js', 'um\ndois\n');
    escrever('node_modules/pkg/b.js', 'x\ny\n');
    patch('0001-ok.patch', [
        'diff --git a/node_modules/pkg/a.js b/node_modules/pkg/a.js',
        '--- a/node_modules/pkg/a.js',
        '+++ b/node_modules/pkg/a.js',
        '@@ -1,2 +1,2 @@',
        ' um',
        '-dois',
        '+DOIS',
    ]);
    patch('0002-divergente.patch', [
        '--- a/node_modules/pkg/b.js',
        '+++ b/node_modules/pkg/b.js',
        '@@ -1,2 +1,2 @@',
        ' nao-existe',
        '-y',
        '+Y',
    ]);
    const antesA = ler('node_modules/pkg/a.js');
    const antesB = ler('node_modules/pkg/b.js');

    assert.throws(
        () => aplicar(),
        (e) => e instanceof ErroPatch && /0002-divergente\.patch/.test(e.message),
    );
    assert.deepEqual(ler('node_modules/pkg/a.js'), antesA);
    assert.deepEqual(ler('node_modules/pkg/b.js'), antesB);
});

test('recusa formatos não suportados: rename, binário, modo, criação e remoção', () => {
    const casos = {
        rename: [
            'diff --git a/node_modules/pkg/a.js b/node_modules/pkg/b.js',
            'rename from node_modules/pkg/a.js',
            'rename to node_modules/pkg/b.js',
        ],
        binario: [
            'diff --git a/node_modules/pkg/x.png b/node_modules/pkg/x.png',
            'Binary files a/node_modules/pkg/x.png and b/node_modules/pkg/x.png differ',
        ],
        modo: [
            'diff --git a/node_modules/pkg/a.js b/node_modules/pkg/a.js',
            'old mode 100644',
            'new mode 100755',
        ],
        criacao: [
            'diff --git a/node_modules/pkg/novo.js b/node_modules/pkg/novo.js',
            'new file mode 100644',
            '--- /dev/null',
            '+++ b/node_modules/pkg/novo.js',
            '@@ -0,0 +1 @@',
            '+x',
        ],
        criacaoSemModo: ['--- /dev/null', '+++ b/node_modules/pkg/novo.js', '@@ -0,0 +1 @@', '+x'],
        remocao: ['--- a/node_modules/pkg/a.js', '+++ /dev/null', '@@ -1 +0,0 @@', '-x'],
    };

    for (const [nome, linhas] of Object.entries(casos)) {
        assert.throws(
            () => analisarPatch(`${linhas.join('\n')}\n`, nome),
            (e) => e instanceof ErroPatch && /não suportad[oa]/.test(e.message),
            `caso: ${nome}`,
        );
    }
});

test('hunk sem linha de contexto é recusado', () => {
    const texto = ['--- a/node_modules/pkg/a.js', '+++ b/node_modules/pkg/a.js', '@@ -0,0 +1 @@', '+x', ''].join('\n');

    assert.throws(
        () => analisarPatch(texto, 'sem-contexto.patch'),
        (e) => e instanceof ErroPatch && /sem linhas de contexto/.test(e.message),
    );
});

test('hunk só de contexto, sem nenhuma alteração, é recusado', () => {
    const texto = ['--- a/node_modules/pkg/a.js', '+++ b/node_modules/pkg/a.js', '@@ -1,2 +1,2 @@', ' um', ' dois', ''].join('\n');

    assert.throws(
        () => analisarPatch(texto, 'sem-alteracao.patch'),
        (e) => e instanceof ErroPatch && /sem alteração/.test(e.message),
    );
});

test('pacote alvo ausente em node_modules é erro explícito', () => {
    patch('0003-sem-pacote.patch', [
        '--- a/node_modules/nao-instalado/x.js',
        '+++ b/node_modules/nao-instalado/x.js',
        '@@ -1,2 +1,2 @@',
        ' a',
        '-b',
        '+c',
    ]);

    assert.throws(
        () => aplicar(),
        (e) => e instanceof ErroPatch && /ausente em node_modules/.test(e.message),
    );
});

test('arquivo alvo ausente dentro de um pacote instalado é erro explícito', () => {
    patch('0004-sem-arquivo.patch', [
        '--- a/node_modules/pkg/nao-existe.js',
        '+++ b/node_modules/pkg/nao-existe.js',
        '@@ -1,2 +1,2 @@',
        ' a',
        '-b',
        '+c',
    ]);

    assert.throws(
        () => aplicar(),
        (e) => e instanceof ErroPatch && /arquivo alvo ausente/.test(e.message),
    );
});

// Paridade com o patch real de lib/patches. O fixture reproduz o arquivo Utils.js do
// whatsapp-web.js 1.34.7 nas linhas 483 a 488 (o contexto do hunk @@ -483,6 +483,11 @@).
test('paridade: aplica o patch real do whatsapp-web.js sobre o contexto real', () => {
    const alvo = 'node_modules/whatsapp-web.js/src/util/Injected/Utils.js';
    const preambulo = Array.from({ length: 482 }, (_, i) => `// preenchimento ${i + 1}`);
    const contexto = [
        '            ...extraOptions,',
        '        };',
        '',
        "        // Bot's won't reply if canonicalUrl is set (linking)",
        '        if (botOptions) {',
        '            delete message.canonicalUrl;',
    ];
    const inseridoPeloPatch = [
        "        // MediaData is a model whose private __x_id field collides with Msg's",
        '        // internal id field when its enumerable properties are spread above,',
        '        // breaking getValidatedSender() during Msg initialization.',
        '        delete message.__x_id;',
        '',
    ];
    const rodape = ['        }', '', '        if (isChannel) {'];

    fs.mkdirSync(path.join(raiz, 'node_modules', 'whatsapp-web.js'), { recursive: true });
    escrever(alvo, [...preambulo, ...contexto, ...rodape].join('\n') + '\n');
    fs.copyFileSync(PATCH_REAL, path.join(dirPatches, 'whatsapp-web.js+1.34.7.patch'));

    const resultados = aplicar();

    assert.equal(resultados[0].status, 'aplicado');
    assert.equal(resultados[0].caminho, alvo);
    const esperado = [...preambulo, ...contexto.slice(0, 3), ...inseridoPeloPatch, ...contexto.slice(3), ...rodape];
    const obtido = ler(alvo).toString('utf8');
    assert.equal(obtido, esperado.join('\n') + '\n');
    assert.equal(obtido.split('\n')[488], '        delete message.__x_id;');

    // Segunda execução sobre o arquivo já patchado: idempotente.
    const antes = ler(alvo);
    assert.equal(aplicar()[0].status, 'ja-aplicado');
    assert.deepEqual(ler(alvo), antes);
});

// O bloco novo existe inteiro em outro lugar do arquivo, mas o hunk tem de ser decidido só no seu ponto.
const CFG_COM_DUPLICATA = [
    'const cfg = {',
    '  timeout: 5,',
    '  extra: true,',
    '  retries: 3,',
    '};',
    'const outro = {',
    '  timeout: 5,',
    '  retries: 3,',
    '};',
    '',
].join('\n');
const HUNK_REMOVE_EXTRA = [
    `--- a/${ALVO_BASICO}`,
    `+++ b/${ALVO_BASICO}`,
    '@@ -2,3 +2,2 @@',
    '   timeout: 5,',
    '-  extra: true,',
    '   retries: 3,',
];

test('bloco novo duplicado fora do ponto do hunk não impede a aplicação', () => {
    escrever(ALVO_BASICO, CFG_COM_DUPLICATA);
    patch('0006-duplicado.patch', HUNK_REMOVE_EXTRA);

    const resultados = aplicar();

    assert.equal(resultados[0].status, 'aplicado');
    assert.equal(
        ler(ALVO_BASICO).toString('utf8'),
        [
            'const cfg = {',
            '  timeout: 5,',
            '  retries: 3,',
            '};',
            'const outro = {',
            '  timeout: 5,',
            '  retries: 3,',
            '};',
            '',
        ].join('\n'),
    );
});

// Substitui o antigo "estado ambíguo": o ponto do cabeçalho já está aplicado, e o bloco antigo que existe
// só em outro lugar do arquivo não é casado ali. Resultado: já aplicado, sem gravar.
test('bloco antigo só fora do ponto do cabeçalho não é aplicado lá: o ponto já está aplicado, sem gravar', () => {
    const original = [
        'const cfg = {',
        '  timeout: 5,',
        '  retries: 3,',
        '};',
        'const outro = {',
        '  timeout: 5,',
        '  extra: true,',
        '  retries: 3,',
        '};',
        '',
    ].join('\n');
    escrever(ALVO_BASICO, original);
    patch('0006-fora-do-ponto.patch', HUNK_REMOVE_EXTRA);

    assert.equal(aplicar()[0].status, 'ja-aplicado');
    assert.equal(ler(ALVO_BASICO).toString('utf8'), original);
});

// Substitui o antigo "já aplicado com linhas acrescidas acima": sem deslocamento, isso é contexto divergente.
test('já aplicado com linhas acrescidas acima do hunk não é reconhecido: erro, sem gravar', () => {
    escrever(ALVO_BASICO, `// topo\n${ESPERADO_BASICO}`);
    patch('0001-basico.patch', PATCH_BASICO);
    const antes = ler(ALVO_BASICO);

    assert.throws(() => aplicar(), (e) => e instanceof ErroPatch && /não casa/.test(e.message));
    assert.deepEqual(ler(ALVO_BASICO), antes);
});

// Linhas '+', '-' ou ' ' além da contagem do cabeçalho @@ não podem ser descartadas em silêncio.
test('linha de inserção além da contagem do cabeçalho @@ é erro, não é descartada em silêncio', () => {
    escrever('node_modules/pkg/a.js', 'a\nz\n');
    patch('0007-excesso-mais.patch', [
        '--- a/node_modules/pkg/a.js',
        '+++ b/node_modules/pkg/a.js',
        '@@ -1,1 +1,2 @@',
        ' a',
        '+b',
        '+c',
    ]);
    const antes = ler('node_modules/pkg/a.js');

    assert.throws(
        () => aplicar(),
        (e) => e instanceof ErroPatch && /além da contagem/.test(e.message),
    );
    assert.deepEqual(ler('node_modules/pkg/a.js'), antes);
});

test('linha de remoção além da contagem do cabeçalho @@ é erro', () => {
    escrever('node_modules/pkg/a.js', 'a\nx\nz\n');
    patch('0007-excesso-menos.patch', [
        '--- a/node_modules/pkg/a.js',
        '+++ b/node_modules/pkg/a.js',
        '@@ -1,1 +1,1 @@',
        ' a',
        '-x',
    ]);

    assert.throws(
        () => aplicar(),
        (e) => e instanceof ErroPatch && /além da contagem/.test(e.message),
    );
    assert.equal(ler('node_modules/pkg/a.js').toString('utf8'), 'a\nx\nz\n');
});

test('linha de contexto além da contagem do cabeçalho @@ é erro', () => {
    escrever('node_modules/pkg/a.js', 'a\nb\n');
    patch('0007-excesso-ctx.patch', [
        '--- a/node_modules/pkg/a.js',
        '+++ b/node_modules/pkg/a.js',
        '@@ -1,1 +1,1 @@',
        ' a',
        ' b',
    ]);

    assert.throws(
        () => aplicar(),
        (e) => e instanceof ErroPatch && /além da contagem/.test(e.message),
    );
});

test('assinatura de git format-patch ("-- ") depois do último hunk continua ignorada', () => {
    escrever('node_modules/pkg/a.js', 'um\ndois\n');
    patch('0008-format-patch.patch', [
        '--- a/node_modules/pkg/a.js',
        '+++ b/node_modules/pkg/a.js',
        '@@ -1,2 +1,2 @@',
        ' um',
        '-dois',
        '+DOIS',
        '-- ',
        '2.45.0',
    ]);

    assert.equal(aplicar()[0].status, 'aplicado');
    assert.equal(ler('node_modules/pkg/a.js').toString('utf8'), 'um\nDOIS\n');
});

// O alvo é lido como UTF-8 estrito: byte inválido vira erro, e não U+FFFD gravado no lugar do original.
test('alvo que não é UTF-8 válido é recusado antes de gravar qualquer arquivo', () => {
    escrever('node_modules/pkg/a.js', 'um\ndois\n');
    fs.writeFileSync(path.join(raiz, 'node_modules', 'pkg', 'x.js'), Buffer.from('// ação\nx = 1;\ny = 2;\n', 'latin1'));
    patch('0001-ok.patch', [
        'diff --git a/node_modules/pkg/a.js b/node_modules/pkg/a.js',
        '--- a/node_modules/pkg/a.js',
        '+++ b/node_modules/pkg/a.js',
        '@@ -1,2 +1,2 @@',
        ' um',
        '-dois',
        '+DOIS',
    ]);
    patch('0002-latin1.patch', [
        '--- a/node_modules/pkg/x.js',
        '+++ b/node_modules/pkg/x.js',
        '@@ -2,2 +2,2 @@',
        ' x = 1;',
        '-y = 2;',
        '+y = 3;',
    ]);
    const antesX = ler('node_modules/pkg/x.js');
    const antesA = ler('node_modules/pkg/a.js');

    assert.throws(
        () => aplicar(),
        (e) => e instanceof ErroPatch && /UTF-8/.test(e.message) && /0002-latin1\.patch/.test(e.message),
    );
    assert.deepEqual(ler('node_modules/pkg/x.js'), antesX);
    assert.deepEqual(ler('node_modules/pkg/a.js'), antesA);
});

// Inserção no fim do arquivo: o bloco antigo (só contexto) é prefixo do novo. Na segunda execução o
// bloco antigo ainda casa no ponto do hunk, e o bloco novo também: o hunk já está aplicado.
test('segunda execução de hunk que insere no fim do arquivo é idempotente (não duplica a linha)', () => {
    escrever('node_modules/pkg/a.js', 'x\ny\n');
    patch('0001-fim.patch', [
        '--- a/node_modules/pkg/a.js',
        '+++ b/node_modules/pkg/a.js',
        '@@ -1,2 +1,3 @@',
        ' x',
        ' y',
        '+z',
    ]);

    assert.equal(aplicar()[0].status, 'aplicado');
    assert.equal(ler('node_modules/pkg/a.js').toString('utf8'), 'x\ny\nz\n');

    assert.equal(aplicar()[0].status, 'ja-aplicado');
    assert.equal(ler('node_modules/pkg/a.js').toString('utf8'), 'x\ny\nz\n');
});

// O bloco novo existe inteiro mais abaixo, mas o contexto no ponto do hunk diverge (return 9 no lugar de
// return 1). Não é "já aplicado": o hunk tem de falhar com erro claro.
test('contexto divergente no ponto do hunk não vira "já aplicado" só porque o bloco novo existe mais abaixo', () => {
    const preenchimento = Array.from({ length: 100 }, (_, i) => `// preenchimento ${i + 1}`);
    const original = [
        'function a() {',
        '    return 9;',
        '}',
        '',
        'module.exports = a;',
        ...preenchimento,
        'function a() {',
        '    return 2;',
        '    // novo',
        '}',
        '',
        'module.exports = a;',
        '',
    ].join('\n');
    escrever(ALVO_BASICO, original);
    patch('0001-basico.patch', PATCH_BASICO);

    assert.throws(
        () => aplicar(),
        (e) => e instanceof ErroPatch && /não casa/.test(e.message) && /0001-basico\.patch/.test(e.message),
    );
    assert.equal(ler(ALVO_BASICO).toString('utf8'), original);
});

// A quebra final do arquivo de patch não pode completar um hunk truncado como se fosse contexto vazio.
test('hunk truncado não é completado pela quebra final do arquivo de patch', () => {
    escrever('node_modules/pkg/a.js', 'a\nb\n\nd\n');
    patch('0001-truncado.patch', [
        '--- a/node_modules/pkg/a.js',
        '+++ b/node_modules/pkg/a.js',
        '@@ -1,3 +1,3 @@',
        ' a',
        '-b',
        '+c',
    ]);
    const antes = ler('node_modules/pkg/a.js');

    assert.throws(
        () => aplicar(),
        (e) => e instanceof ErroPatch && /truncado/.test(e.message),
    );
    assert.deepEqual(ler('node_modules/pkg/a.js'), antes);
});

// Um hunk aberto que encontra outro @@ é truncado, não "linha inesperada" (diagnóstico do lugar errado).
test('hunk truncado seguido de outro @@ é reportado como truncado, não como linha inesperada', () => {
    const nome = '0001-truncado-meio.patch';
    patch(nome, [
        '--- a/node_modules/pkg/a.js',
        '+++ b/node_modules/pkg/a.js',
        '@@ -1,3 +1,3 @@',
        ' a',
        '-b',
        '+B',
        '@@ -3,2 +3,2 @@',
        ' c',
        '-d',
        '+D',
    ]);

    assert.throws(
        () => analisarPatch(fs.readFileSync(path.join(dirPatches, nome), 'utf8'), nome),
        (e) => e instanceof ErroPatch && /truncado/.test(e.message) && /0001-truncado-meio\.patch/.test(e.message),
    );
});

test('linha de contexto vazia escrita no fim do hunk continua aceita', () => {
    escrever('node_modules/pkg/a.js', 'a\nb\n\nd\n');
    fs.writeFileSync(
        path.join(dirPatches, '0001-contexto-vazio.patch'),
        '--- a/node_modules/pkg/a.js\n+++ b/node_modules/pkg/a.js\n@@ -1,3 +1,3 @@\n a\n-b\n+c\n\n',
        'utf8',
    );

    assert.equal(aplicar()[0].status, 'aplicado');
    assert.equal(ler('node_modules/pkg/a.js').toString('utf8'), 'a\nc\n\nd\n');
});

// O BOM fica fora do casamento: um hunk na linha 1 de arquivo com BOM tem de casar, e o BOM é reposto.
test('hunk na primeira linha de arquivo com BOM casa e o BOM é preservado na gravação', () => {
    fs.writeFileSync(
        path.join(raiz, 'node_modules', 'pkg', 'a.js'),
        Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), Buffer.from('um\ndois\n', 'utf8')]),
    );
    patch('0001-bom-linha1.patch', [
        '--- a/node_modules/pkg/a.js',
        '+++ b/node_modules/pkg/a.js',
        '@@ -1,2 +1,2 @@',
        ' um',
        '-dois',
        '+DOIS',
    ]);

    assert.equal(aplicar()[0].status, 'aplicado');
    assert.deepEqual(
        ler('node_modules/pkg/a.js'),
        Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), Buffer.from('um\nDOIS\n', 'utf8')]),
    );
});

// Caminho do git: o contexto da linha 1 traz o BOM copiado do arquivo. Tem de continuar casando.
test('patch do git com BOM no contexto da linha 1 também casa, e o BOM não é duplicado', () => {
    fs.writeFileSync(
        path.join(raiz, 'node_modules', 'pkg', 'a.js'),
        Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), Buffer.from('um\ndois\n', 'utf8')]),
    );
    patch('0001-bom-git.patch', [
        '--- a/node_modules/pkg/a.js',
        '+++ b/node_modules/pkg/a.js',
        '@@ -1,2 +1,2 @@',
        ' \uFEFFum',
        '-dois',
        '+DOIS',
    ]);

    assert.equal(aplicar()[0].status, 'aplicado');
    assert.deepEqual(
        ler('node_modules/pkg/a.js'),
        Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), Buffer.from('um\nDOIS\n', 'utf8')]),
    );
});

// Patch salvo com BOM (editor ou PowerShell -Encoding UTF8): o BOM sai antes da análise.
test('patch salvo com BOM é aceito e o BOM não entra no cabeçalho ---', () => {
    escrever('node_modules/pkg/a.js', 'um\ndois\n');
    fs.writeFileSync(
        path.join(dirPatches, '0001-bom-patch.patch'),
        '\uFEFF--- a/node_modules/pkg/a.js\n+++ b/node_modules/pkg/a.js\n@@ -1,2 +1,2 @@\n um\n-dois\n+DOIS\n',
        'utf8',
    );

    assert.equal(aplicar()[0].status, 'aplicado');
    assert.equal(ler('node_modules/pkg/a.js').toString('utf8'), 'um\nDOIS\n');
});

// CRLF sem quebra final: cada linha que ganha sucessor sai com o EOL do arquivo, e a última linha
// não recebe CR solto nem quebra que o arquivo original não tinha.
test('CRLF sem quebra final: inserção no fim não grava LF no meio nem CR solto no fim', () => {
    escrever('node_modules/pkg/a.js', 'a\r\nb\r\nc');
    patch('0001-crlf-sem-quebra.patch', [
        '--- a/node_modules/pkg/a.js',
        '+++ b/node_modules/pkg/a.js',
        '@@ -1,3 +1,4 @@',
        ' a',
        ' b',
        ' c',
        '+d',
    ]);

    assert.equal(aplicar()[0].status, 'aplicado');
    assert.equal(ler('node_modules/pkg/a.js').toString('utf8'), 'a\r\nb\r\nc\r\nd');
});

test('CRLF sem quebra final: a última linha antiga ganha o EOL do arquivo ao receber sucessor', () => {
    escrever('node_modules/pkg/a.js', 'a\r\nb');
    patch('0001-crlf-sem-quebra-2.patch', [
        '--- a/node_modules/pkg/a.js',
        '+++ b/node_modules/pkg/a.js',
        '@@ -1,2 +1,3 @@',
        ' a',
        ' b',
        '+c',
    ]);

    assert.equal(aplicar()[0].status, 'aplicado');
    assert.equal(ler('node_modules/pkg/a.js').toString('utf8'), 'a\r\nb\r\nc');
});

// Dois hunks: o primeiro insere sem contexto posterior (o bloco antigo é prefixo do novo) e o segundo
// troca uma linha depois do deslocamento. A reexecução não pode duplicar a inserção nem reaplicar a troca.
test('reexecução de dois hunks, com inserção sem contexto posterior, é idempotente', () => {
    escrever('node_modules/pkg/a.js', 'a\nb\nc\nd\ne\nf\n');
    patch('0001-dois-hunks.patch', [
        '--- a/node_modules/pkg/a.js',
        '+++ b/node_modules/pkg/a.js',
        '@@ -1,2 +1,3 @@',
        ' a',
        ' b',
        '+x',
        '@@ -4,2 +5,2 @@',
        ' d',
        '-e',
        '+E',
    ]);

    assert.equal(aplicar()[0].status, 'aplicado');
    assert.equal(ler('node_modules/pkg/a.js').toString('utf8'), 'a\nb\nx\nc\nd\nE\nf\n');

    assert.equal(aplicar()[0].status, 'ja-aplicado');
    assert.equal(ler('node_modules/pkg/a.js').toString('utf8'), 'a\nb\nx\nc\nd\nE\nf\n');
});

// Remoção no fim do arquivo: o bloco novo ('a', 'b') é prefixo do antigo ('a', 'b', 'a'). Enquanto o
// arquivo não foi alterado o hunk tem de ser aplicado; depois, a reexecução reconhece o estado final.
test('remoção no fim do arquivo é aplicada e a reexecução reconhece o estado final', () => {
    escrever('node_modules/pkg/a.js', 'a\nb\na\n');
    patch('0001-remocao-fim.patch', [
        '--- a/node_modules/pkg/a.js',
        '+++ b/node_modules/pkg/a.js',
        '@@ -1,3 +1,2 @@',
        ' a',
        ' b',
        '-a',
    ]);

    assert.equal(aplicar()[0].status, 'aplicado');
    assert.equal(ler('node_modules/pkg/a.js').toString('utf8'), 'a\nb\n');

    assert.equal(aplicar()[0].status, 'ja-aplicado');
    assert.equal(ler('node_modules/pkg/a.js').toString('utf8'), 'a\nb\n');
});

// Reexecução com inserção antes do contexto (no topo ou no meio): o hunk já aplicado tem de ser reconhecido.
test('reexecução de hunk que insere linhas no topo do arquivo é idempotente', () => {
    escrever(ALVO_BASICO, 'a\nb\nc\n');
    patch('0001-topo.patch', [
        '--- a/node_modules/pkg/mod.js',
        '+++ b/node_modules/pkg/mod.js',
        '@@ -1,2 +1,3 @@',
        '+import z;',
        ' a',
        ' b',
    ]);

    assert.equal(aplicar()[0].status, 'aplicado');
    assert.equal(ler(ALVO_BASICO).toString('utf8'), 'import z;\na\nb\nc\n');

    assert.equal(aplicar()[0].status, 'ja-aplicado');
    assert.equal(ler(ALVO_BASICO).toString('utf8'), 'import z;\na\nb\nc\n');
});

test('reexecução de hunk que insere linhas no meio, antes do contexto, é idempotente', () => {
    escrever(ALVO_BASICO, 'a\nb\nc\nd\n');
    patch('0001-meio.patch', [
        '--- a/node_modules/pkg/mod.js',
        '+++ b/node_modules/pkg/mod.js',
        '@@ -3,2 +3,3 @@',
        '+mid',
        ' c',
        ' d',
    ]);

    assert.equal(aplicar()[0].status, 'aplicado');
    assert.equal(ler(ALVO_BASICO).toString('utf8'), 'a\nb\nmid\nc\nd\n');

    assert.equal(aplicar()[0].status, 'ja-aplicado');
    assert.equal(ler(ALVO_BASICO).toString('utf8'), 'a\nb\nmid\nc\nd\n');
});

// Hunk misto (inserção no topo e remoção) cujo bloco novo já está no ponto do cabeçalho: é reconhecido como
// já aplicado e nada é gravado. A linha 'b' fica depois do hunk e não é verificada.
test('hunk misto com o bloco novo no ponto do cabeçalho é reconhecido como já aplicado, sem gravar', () => {
    const original = 'z\na\nb\n';
    escrever(ALVO_BASICO, original);
    patch('0001-misto.patch', [
        '--- a/node_modules/pkg/mod.js',
        '+++ b/node_modules/pkg/mod.js',
        '@@ -1,2 +1,2 @@',
        '+z',
        ' a',
        '-b',
    ]);

    assert.equal(aplicar()[0].status, 'ja-aplicado');
    assert.equal(ler(ALVO_BASICO).toString('utf8'), original);
});

// O .patch é lido como UTF-8 estrito, como o alvo: byte inválido vira erro, e não U+FFFD copiado para o alvo.
test('patch que não é UTF-8 válido é recusado antes de gravar qualquer arquivo', () => {
    escrever('node_modules/pkg/a.js', 'um\ndois\n');
    const antes = ler('node_modules/pkg/a.js');
    const trecho = '--- a/node_modules/pkg/a.js\n+++ b/node_modules/pkg/a.js\n@@ -1,2 +1,3 @@\n um\n+// a';
    fs.writeFileSync(
        path.join(dirPatches, '0001-latin1.patch'),
        Buffer.concat([Buffer.from(trecho, 'utf8'), Buffer.from([0xe7, 0xe3]), Buffer.from('o\n-dois\n+DOIS\n', 'utf8')]),
    );

    assert.throws(
        () => aplicar(),
        (e) => e instanceof ErroPatch && /UTF-8/.test(e.message) && /0001-latin1\.patch/.test(e.message),
    );
    assert.deepEqual(ler('node_modules/pkg/a.js'), antes);
});

test('o mesmo alvo em duas seções do mesmo patch é recusado', () => {
    escrever('node_modules/pkg/a.js', 'um\ndois\ntres\n');
    patch('0001-repetido.patch', [
        '--- a/node_modules/pkg/a.js',
        '+++ b/node_modules/pkg/a.js',
        '@@ -1,2 +1,2 @@',
        ' um',
        '-dois',
        '+DOIS',
        '--- a/node_modules/pkg/a.js',
        '+++ b/node_modules/pkg/a.js',
        '@@ -2,2 +2,2 @@',
        ' dois',
        '-tres',
        '+TRES',
    ]);
    const antes = ler('node_modules/pkg/a.js');

    assert.throws(() => aplicar(), (e) => e instanceof ErroPatch && /alvo repetido/.test(e.message));
    assert.deepEqual(ler('node_modules/pkg/a.js'), antes);
});

// NTFS não diferencia maiúsculas: mod.js e MOD.js são o mesmo arquivo. A alteração de um deles não pode sumir.
test('caminhos que diferem só na caixa editam o mesmo arquivo no NTFS: recusados antes de gravar', () => {
    escrever('node_modules/pkg/mod.js', 'linha 1\nlinha 2\nlinha 3\nlinha 4\n');
    patch('0001-minusculo.patch', [
        '--- a/node_modules/pkg/mod.js',
        '+++ b/node_modules/pkg/mod.js',
        '@@ -1,2 +1,2 @@',
        ' linha 1',
        '-linha 2',
        '+LINHA DOIS',
    ]);
    patch('0002-maiusculo.patch', [
        '--- a/node_modules/pkg/MOD.js',
        '+++ b/node_modules/pkg/MOD.js',
        '@@ -3,2 +3,2 @@',
        ' linha 3',
        '-linha 4',
        '+LINHA QUATRO',
    ]);
    const antes = ler('node_modules/pkg/mod.js');

    assert.throws(
        () => aplicar(),
        (e) => e instanceof ErroPatch && /alvo repetido/.test(e.message) && /0002-maiusculo\.patch/.test(e.message),
    );
    assert.deepEqual(ler('node_modules/pkg/mod.js'), antes);
});

test('estado misto entre hunks do mesmo arquivo (um aplicado, outro não) é erro, sem gravar', () => {
    escrever('node_modules/pkg/a.js', 'a\nB\nc\nd\n');
    patch('0001-misto-hunks.patch', [
        '--- a/node_modules/pkg/a.js',
        '+++ b/node_modules/pkg/a.js',
        '@@ -1,2 +1,2 @@',
        ' a',
        '-b',
        '+B',
        '@@ -3,2 +3,2 @@',
        ' c',
        '-d',
        '+D',
    ]);
    const antes = ler('node_modules/pkg/a.js');

    assert.throws(() => aplicar(), (e) => e instanceof ErroPatch && /estado misto/.test(e.message));
    assert.deepEqual(ler('node_modules/pkg/a.js'), antes);
});

test('EOL misto no alvo (CRLF e LF no mesmo arquivo) é recusado sem gravar', () => {
    escrever('node_modules/pkg/a.js', 'um\r\ndois\ntres\r\n');
    patch('0001-eol.patch', [
        '--- a/node_modules/pkg/a.js',
        '+++ b/node_modules/pkg/a.js',
        '@@ -1,2 +1,2 @@',
        ' um',
        '-dois',
        '+DOIS',
    ]);
    const antes = ler('node_modules/pkg/a.js');

    assert.throws(
        () => aplicar(),
        (e) => e instanceof ErroPatch && /EOL misto/.test(e.message) && /0001-eol\.patch/.test(e.message),
    );
    assert.deepEqual(ler('node_modules/pkg/a.js'), antes);
});

test('cabeçalhos --- e +++ com caminhos diferentes (renomeação) são recusados', () => {
    const texto = [
        '--- a/node_modules/pkg/a.js',
        '+++ b/node_modules/pkg/b.js',
        '@@ -1,2 +1,2 @@',
        ' um',
        '-dois',
        '+DOIS',
    ].join('\n');

    assert.throws(
        () => analisarPatch(texto, 'renomeia.patch'),
        (e) => e instanceof ErroPatch && /apontam para arquivos diferentes/.test(e.message),
    );
});

test('cabeçalho @@ cujo início não bate com o hunk (+c inconsistente) é recusado', () => {
    const texto = ['--- a/node_modules/pkg/a.js', '+++ b/node_modules/pkg/a.js', '@@ -1,2 +2,2 @@', ' um', '-dois', '+DOIS'].join('\n');

    assert.throws(
        () => analisarPatch(texto, 'inconsistente.patch'),
        (e) => e instanceof ErroPatch && /cabeçalho inconsistente/.test(e.message),
    );
});

// Falha de gravação: a substituição (rename) é bloqueada por somente leitura no Windows. Entre arquivos não há
// atomicidade, então a.js (já gravado) fica como está; o alvo bloqueado não muda e nenhum .tmp sobra.
// A reexecução, com o alvo liberado, completa o trabalho.
test('falha ao gravar um alvo: o alvo bloqueado fica intacto, nenhum .tmp sobra e a reexecução completa', {
    skip: process.platform === 'win32' ? false : 'somente leitura bloqueia a substituição apenas no Windows',
}, () => {
    escrever('node_modules/pkg/a.js', 'um\ndois\n');
    escrever('node_modules/pkg/b.js', 'x\ny\n');
    const bloqueado = path.join(raiz, 'node_modules', 'pkg', 'b.js');
    patch('0001-a.patch', ['--- a/node_modules/pkg/a.js', '+++ b/node_modules/pkg/a.js', '@@ -1,2 +1,2 @@', ' um', '-dois', '+DOIS']);
    patch('0002-b.patch', ['--- a/node_modules/pkg/b.js', '+++ b/node_modules/pkg/b.js', '@@ -1,2 +1,2 @@', ' x', '-y', '+Y']);

    fs.chmodSync(bloqueado, 0o444);
    try {
        assert.throws(() => aplicar(), (e) => e instanceof ErroPatch && /não foi possível gravar/.test(e.message));
        assert.equal(ler('node_modules/pkg/b.js').toString('utf8'), 'x\ny\n');
        assert.deepEqual(fs.readdirSync(path.join(raiz, 'node_modules', 'pkg')).filter((n) => n.endsWith('.tmp')), []);
    } finally {
        fs.chmodSync(bloqueado, 0o666);
    }

    assert.deepEqual(aplicar().map((r) => [r.caminho, r.status]), [
        ['node_modules/pkg/a.js', 'ja-aplicado'],
        ['node_modules/pkg/b.js', 'aplicado'],
    ]);
    assert.equal(ler('node_modules/pkg/b.js').toString('utf8'), 'x\nY\n');
});

// Regressão: inserção de linha igual à linha de contexto vizinha. A reexecução tem de reconhecer o hunk aplicado,
// e não dar 'estado ambíguo' por o bloco antigo casar uma posição abaixo.
test('inserção de linha igual à de contexto vizinha: a reexecução reconhece o hunk aplicado', () => {
    escrever(ALVO_BASICO, 'alpha\nbeta\ngamma\n');
    patch('0001-beta.patch', [
        '--- a/node_modules/pkg/mod.js',
        '+++ b/node_modules/pkg/mod.js',
        '@@ -2,2 +2,3 @@',
        ' beta',
        '+beta',
        ' gamma',
    ]);

    assert.equal(aplicar()[0].status, 'aplicado');
    assert.equal(ler(ALVO_BASICO).toString('utf8'), 'alpha\nbeta\nbeta\ngamma\n');

    assert.equal(aplicar()[0].status, 'ja-aplicado');
    assert.equal(ler(ALVO_BASICO).toString('utf8'), 'alpha\nbeta\nbeta\ngamma\n');
});

// Propriedade, para cada cenário fixo: aplicar duas vezes dá 'aplicado' e depois 'ja-aplicado', com o arquivo
// idêntico byte a byte; o patch reverso (troca de '+' e '-', com os inícios recalculados) aplicado ao resultado
// devolve o original byte a byte. Cada hunk é { inicio, linhas }: inicio é a linha (1-based) da primeira linha
// antiga do hunk.
function montarPatch(caminho, hunks) {
    const partes = [`--- a/${caminho}`, `+++ b/${caminho}`];
    let deslocamento = 0;
    for (const { inicio, linhas } of hunks) {
        const antigo = linhas.filter((l) => l[0] !== '+').length;
        const novo = linhas.filter((l) => l[0] !== '-').length;
        partes.push(`@@ -${inicio},${antigo} +${inicio + deslocamento},${novo} @@`, ...linhas);
        deslocamento += novo - antigo;
    }
    return partes;
}

function inverterHunks(hunks) {
    const trocar = (l) => (l[0] === '+' ? `-${l.slice(1)}` : l[0] === '-' ? `+${l.slice(1)}` : l);
    let deslocamento = 0;
    return hunks.map(({ inicio, linhas }) => {
        const antigo = linhas.filter((l) => l[0] !== '+').length;
        const novo = linhas.filter((l) => l[0] !== '-').length;
        const invertido = { inicio: inicio + deslocamento, linhas: linhas.map(trocar) };
        deslocamento += novo - antigo;
        return invertido;
    });
}

const CENARIOS_PROPRIEDADE = [
    { nome: 'inserção no topo', original: 'a\nb\nc\n', hunks: [{ inicio: 1, linhas: ['+z', ' a', ' b'] }], esperado: 'z\na\nb\nc\n' },
    { nome: 'inserção no meio, entre contexto', original: 'a\nb\nc\nd\n', hunks: [{ inicio: 2, linhas: [' b', '+mid', ' c'] }], esperado: 'a\nb\nmid\nc\nd\n' },
    { nome: 'inserção no meio, antes do contexto', original: 'a\nb\nc\nd\n', hunks: [{ inicio: 3, linhas: ['+mid', ' c', ' d'] }], esperado: 'a\nb\nmid\nc\nd\n' },
    { nome: 'inserção no fim', original: 'x\ny\n', hunks: [{ inicio: 1, linhas: [' x', ' y', '+z'] }], esperado: 'x\ny\nz\n' },
    { nome: 'remoção no meio', original: 'a\nb\nc\nd\n', hunks: [{ inicio: 2, linhas: [' b', '-c', ' d'] }], esperado: 'a\nb\nd\n' },
    { nome: 'remoção no fim', original: 'a\nb\na\n', hunks: [{ inicio: 1, linhas: [' a', ' b', '-a'] }], esperado: 'a\nb\n' },
    { nome: 'substituição', original: 'um\ndois\ntres\n', hunks: [{ inicio: 2, linhas: [' dois', '-tres', '+TRES'] }], esperado: 'um\ndois\nTRES\n' },
    { nome: 'vários hunks', original: 'a\nb\nc\nd\ne\nf\n', hunks: [{ inicio: 1, linhas: [' a', ' b', '+x'] }, { inicio: 4, linhas: [' d', '-e', '+E'] }], esperado: 'a\nb\nx\nc\nd\nE\nf\n' },
    { nome: 'vários hunks, inserção no topo e remoção', original: 'a\nb\nc\nd\n', hunks: [{ inicio: 1, linhas: ['+z', ' a', ' b'] }, { inicio: 3, linhas: ['-c', ' d'] }], esperado: 'z\na\nb\nd\n' },
    { nome: 'CRLF com substituição', original: 'um\r\ndois\r\ntres\r\n', hunks: [{ inicio: 2, linhas: [' dois', '-tres', '+TRES'] }], esperado: 'um\r\ndois\r\nTRES\r\n' },
    { nome: 'CRLF com inserção no topo', original: 'a\r\nb\r\nc\r\n', hunks: [{ inicio: 1, linhas: ['+z', ' a', ' b'] }], esperado: 'z\r\na\r\nb\r\nc\r\n' },
    { nome: 'CRLF sem quebra final com inserção no fim', original: 'a\r\nb\r\nc', hunks: [{ inicio: 1, linhas: [' a', ' b', ' c', '+d'] }], esperado: 'a\r\nb\r\nc\r\nd' },
    { nome: 'BOM com contexto sem BOM', original: '\uFEFFum\ndois\ntres\n', hunks: [{ inicio: 1, linhas: [' um', '-dois', '+DOIS'] }], esperado: '\uFEFFum\nDOIS\ntres\n' },
    { nome: 'BOM com contexto copiado pelo git', original: '\uFEFFum\ndois\ntres\n', hunks: [{ inicio: 1, linhas: [' \uFEFFum', '-dois', '+DOIS'] }], esperado: '\uFEFFum\nDOIS\ntres\n' },
    { nome: 'BOM com inserção no topo', original: '\uFEFFa\nb\n', hunks: [{ inicio: 1, linhas: ['+z', ' a', ' b'] }], esperado: '\uFEFFz\na\nb\n' },
];

for (const cenario of CENARIOS_PROPRIEDADE) {
    test(`propriedade: ${cenario.nome}`, () => {
        escrever(ALVO_BASICO, cenario.original);
        const nome = '0001-propriedade.patch';
        patch(nome, montarPatch(ALVO_BASICO, cenario.hunks));

        assert.equal(aplicar()[0].status, 'aplicado');
        assert.equal(ler(ALVO_BASICO).toString('utf8'), cenario.esperado);
        const aplicado = ler(ALVO_BASICO);

        assert.equal(aplicar()[0].status, 'ja-aplicado');
        assert.deepEqual(ler(ALVO_BASICO), aplicado);

        patch(nome, montarPatch(ALVO_BASICO, inverterHunks(cenario.hunks)));
        assert.equal(aplicar()[0].status, 'aplicado');
        assert.deepEqual(ler(ALVO_BASICO), Buffer.from(cenario.original, 'utf8'));
    });
}

test('alvo UTF-8 com BOM mantém o BOM ao ser regravado', () => {
    fs.writeFileSync(
        path.join(raiz, 'node_modules', 'pkg', 'a.js'),
        Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), Buffer.from('um\ndois\ntres\n', 'utf8')]),
    );
    patch('0001-bom.patch', [
        '--- a/node_modules/pkg/a.js',
        '+++ b/node_modules/pkg/a.js',
        '@@ -2,2 +2,2 @@',
        ' dois',
        '-tres',
        '+TRES',
    ]);

    assert.equal(aplicar()[0].status, 'aplicado');
    assert.deepEqual(ler('node_modules/pkg/a.js'), Buffer.from('\uFEFFum\ndois\nTRES\n', 'utf8'));
});
