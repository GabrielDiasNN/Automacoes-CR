# extract-zip (fork vendorizado)

Fork do [extract-zip](https://github.com/maxogden/extract-zip) 2.0.1 mantido em `lib/vendor/extract-zip/` pelo Automações, com correções de segurança para symlinks e caminhos de entrada.

## Por que existe

- O pacote upstream está abandonado desde 2021; a última versão publicada é a 2.0.1.
- Duas vulnerabilidades da faixa `<= 2.0.1`, sem versão corrigida publicada:
  - CVE-2026-19693 (GHSA-7pqw-9j4j-h8q3): escrita arbitrária de arquivos por entradas de symlink.
  - CVE-2026-56876 (GHSA-jmr9-qjv8-65gv): path traversal por symlink sem validação.
- Quem usa: `@puppeteer/browsers` (função `unpackArchive`, nas builds `cjs` e `esm`), que usa o extract-zip só para descompactar o Chrome baixado. A chamada é `extractZip.default(archivePath, { dir: folderPath })`, com `folderPath` absoluto.

## Versão

`2.0.2-automacoes.1` é um prerelease de 2.0.2, portanto fora da faixa vulnerável `<= 2.0.1`.

Atenção à integração: pela regra do semver, essa versão **não satisfaz** `^2.0.1`, que é o range declarado pelo `@puppeteer/browsers`. Para que o puppeteer use este fork, o `lib/package.json` precisa de `overrides` (ou de dependência `file:`).

## O que mudou em `index.js`

1. **Alvo de symlink validado antes de criar o link.** O alvo é resolvido como o sistema operacional faria, a partir do diretório real onde o link será criado. São rejeitados:
   - alvo absoluto ou com unidade (`C:...`);
   - alvo que, resolvido, sai do diretório de extração;
   - `..` logo após um componente que não é diretório existente, ou seja, que ainda não existe ou é arquivo (o resultado não é verificável);
   - cadeia de links com mais de 40 saltos, contados no total da resolução (não só na profundidade), como o MAXSYMLINKS do Linux.

   Um componente que já é symlink é seguido, então cadeias que ficam dentro do destino continuam válidas (é o caso de `Versions/Current` em bundles macOS).
2. **Nenhuma entrada grava sobre um symlink existente.** Antes de criar arquivo, diretório ou link, o destino final é verificado com `lstat`. Isso cobre o ataque de duas entradas com o mesmo nome (um symlink seguido de um arquivo regular).
3. **Contenção comparada por separador.** A checagem usa `path.relative`, aplicada ao diretório pai e também ao caminho final. Assim, `/dest-evil` não passa como se estivesse dentro de `/dest`.
4. **Nome com `..` é checado antes de qualquer `mkdir`.** Observação: o yauzl 2.10.0 já recusa esses nomes com `invalid relative path`, então esta checagem é defesa em profundidade.
5. **Ancestral existente verificado antes de qualquer `mkdir`.** O ancestral existente mais próximo do diretório de criação é resolvido com `realpath` e precisa ficar dentro do destino. Sem essa checagem, o `mkdir` recursivo seguiria uma junção ou symlink pré-existente para fora e criaria diretórios lá, antes da rejeição.

Preservado: a API pública (`extract(zipPath, { dir, onEntry, defaultDirMode, defaultFileMode })`, com `dir` absoluto) e o comportamento para zips legítimos. A mensagem do erro de contenção do diretório pai continua a do upstream, em inglês.

## Limites conhecidos

- Criar symlink no Windows exige Modo de Desenvolvedor ou administrador. Sem isso, os casos de symlink real dos testes são pulados.
- Symlink de diretório criado sem tipo (`fs.symlink` sem tipo) no Windows recebe o tipo `dir` quando o alvo já existe na criação, e `file` quando não existe. Nesse segundo caso o link de diretório fica como arquivo. É limitação herdada do upstream, não introduzida pelo fork.
- Symlinks e junções que já existiam no destino antes da extração são seguidos na resolução. Se apontarem para fora, a entrada que passa por eles é rejeitada antes de qualquer `mkdir` que sairia do destino. Se o alvo deles for absoluto, um symlink do zip cujo alvo passa por eles é rejeitado, mesmo que o alvo esteja dentro do destino, porque o fork não resolve caminho absoluto vindo do disco. Essa regra vale só para o alvo: entradas de arquivo e de diretório que passam por eles são aceitas quando o caminho real fica dentro do destino, e um symlink do zip cujo caminho (e não o alvo) passa por eles é tratado como os demais, com o alvo validado a partir do caminho real. O fork não os remove.
- Concorrência: outro processo que altere o diretório durante a extração não é coberto.

## Licença

BSD-2-Clause, Copyright (c) 2014 Max Ogden and other contributors. O arquivo `LICENSE` é a cópia sem alteração do pacote npm 2.0.1. As modificações deste fork são do Automações e não alteram a licença original.

## Testes

Arquivo: `lib/tests/extract-zip-vendor.test.js` (node:test, offline, sem dependência nova).

```
cd lib
node --test tests/extract-zip-vendor.test.js
```

- Os zips de fixture são montados em memória. O caso de cadeia longa usa links virtuais (lstat e readlink simulados), então roda sem privilégio de symlink.
- Os casos com symlink real são pulados com motivo explícito quando o sistema não permite criar symlink (Windows sem Modo de Desenvolvedor). Com a variável `CI` definida, esses casos **reprovam** em vez de pular: o CI nunca pula verificação de segurança em silêncio.
- Se o módulo não carregar (dependência ausente, erro de sintaxe, caminho errado), cada caso **reprova** com o erro. Para pular a suíte de propósito, defina `EXTRACT_ZIP_PULAR_SEM_MODULO=1`.
- Prova de sensibilidade: `EXTRACT_ZIP_MODULO=<caminho do index.js do extract-zip 2.0.1 original> node --test tests/extract-zip-vendor.test.js`, a partir de `lib/` e com a variável `CI` não definida. O original é o do npm, sem as correções do fork: confira que o arquivo não contém `resolverAlvoSymlink`. Os casos de ataque devem falhar contra o original, com uma exceção: o caso de nome com `..` também passa contra ele, porque o yauzl 2.10.0 recusa esse nome antes do fork (ver item 4 de "O que mudou"). A checagem própria do fork para esse nome é defesa em profundidade, e nenhum caso a alcança: o yauzl troca `\` por `/` e recusa nomes com segmento `..` ou caminho absoluto, de modo que nenhum nome que sairia do destino chega ao fork.
- Como ler a prova: uma falha contra o original só conta como detecção quando mostra o comportamento do original, como `Missing expected rejection` (o original aceitou a entrada) ou `diretório criado fora do destino pelo mkdir`. Se o `Input:` da falha contém `EPERM: operation not permitted, symlink`, o original falhou ao criar o link, antes da asserção de rejeição, e esse caso não prova nada. Sem privilégio de symlink (Windows sem Modo de Desenvolvedor), os casos marcados como symlink real ficam pulados e vários casos de ataque falham com `EPERM` contra o original; nesse ambiente, só a falha de `ancestral pré-existente que é junção para fora` prova sensibilidade, porque a junção não exige privilégio. A prova completa exige Linux, macOS ou Windows com Modo de Desenvolvedor ou administrador.
- `NODE_PATH` só é necessário quando o original fica fora de `lib/` (por exemplo, numa cópia): aí `NODE_PATH=<caminho absoluto de lib/node_modules>` permite achar `debug`, `yauzl` e `get-stream`; sem isso, todos os casos reprovam por falha de carregamento. Dentro de `lib/node_modules/extract-zip/`, a resolução funciona sem ele.
- `yauzl`, `debug` e `get-stream` são resolvidos a partir de `lib/node_modules`. Para rodar isolado, copie esta pasta com o teste e rode `npm install` na cópia (nunca dentro de `lib/`).

## Manutenção

Toda mudança de código precisa de caso de teste, incluindo o caso legítimo que ela não pode quebrar. Atualizar o upstream exige reavaliar cada correção listada acima.
