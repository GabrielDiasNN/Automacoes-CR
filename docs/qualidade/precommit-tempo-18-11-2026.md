# Tempo do pre-commit: medição e plano de redução (18/11/2026)

## Resumo

- Um commit levou 304 s, e 302 s deles foram da etapa `governanca_nativa`. A medição isolada mostra que **só a varredura completa** explica esse número. Ela acontece quando o commit inclui qualquer arquivo crítico (`lib\`, `Tools\`, `AGENTS.md`, `.github\workflows\`, `.github\skills\` etc.), que promove o hook a `full_scan`. Num commit comum, direcionado, a etapa leva cerca de 15 s.
- Na varredura completa, **o pylint sozinho custa cerca de 231 s** (73% do total). Depois vêm o PSScriptAnalyzer (~34 s, e ele **não bloqueia nada**: só emite avisos) e o mypy (~23 s com cache quente, ~66 s com cache frio).
- O CI (`governanca-agregada`) **já roda a mesma varredura completa e bloqueante** em todo push e PR, mypy `--strict` e pylint incluídos. A afirmação da skill `ci-gates` de que "o mypy bloqueante não é do CI" está desatualizada. Por isso, restringir o pylint do hook ao diff não tira nenhum gate do pipeline.
- **Achado de integridade, que vale mais que o tempo:** os 33 `.py` de `Produção Beneficimento/` **não passam por mypy nem pylint no CI**. O `pwsh` decodifica a saída do git com a página de código do console (`ibm850`). O nome `Produção` chega corrompido, o `Test-Path` falha e o `continue` descarta o arquivo em silêncio. O log do CI do run 44168117220 mostra 240 arquivos verificados de 273 rastreados. No hook local, o resultado depende do console herdado. A perda foi reproduzida chamando `pwsh -File` direto, mas não nas execuções do hook pela bancada (seção "Resultado da implementação").

## Método

- Worktree limpo no commit `a127710` (o mesmo HEAD do `main`). O índice não foi tocado: o modo direcionado foi reproduzido passando `-Paths` diretamente, que é exatamente o que `ValidarAutomacoes.ps1` faz depois de classificar o staged. O modo completo foi reproduzido chamando cada checagem sem `-Paths`, como acontece com `GovernancePaths` vazio após a promoção.
- Cada checagem foi chamada in-process (`& $script -RootPath ... [-Paths ...]`), igual ao orquestrador, em `pwsh` 7.6.3. O hook prefere `pwsh` quando ele existe. Foram 3 rodadas por cenário, e a tabela reporta a mediana.
- Alvos do modo direcionado: `OBs Paradas Fase\format_message.py`, `Orchestrator\app\services\automation_preflight.py` e `OBs Paradas Fase\run.ps1`.
- O mypy e o pylint foram medidos à parte, com os mesmos argumentos e variáveis de ambiente de `Test-PythonGovernance.ps1`. O PSScriptAnalyzer foi medido em **processo novo**, porque é assim no hook: cada commit abre um `pwsh` novo, e o import do módulo entra na conta. A suíte Node de `lib/` foi medida no `lib\` do checkout principal, porque o worktree não tem `lib\node_modules` e o gate a pula com `[SKIP]`.
- Máquina: 4 núcleos lógicos, com o Orchestrator de produção rodando ao mesmo tempo. Os números têm ruído de alguns por cento.

## Tabela por etapa

| Etapa | Mediana direcionada | Mediana completa | Escopo real | O que protege |
| --- | --- | --- | --- | --- |
| `Test-PythonGovernance.ps1` (total) | 10,4 s | **317,2 s** | Respeita `-Paths` (filtra `.py`). Completo = `git ls-files "*.py"`, com 240 de 273 efetivamente verificados (ver achado) | mypy `--strict` + pylint + veto a `pylint: disable=all` fora do baseline |
| ↳ pylint (22 grupos por diretório) | — | **231,0 s** | Idem | Qualidade de código; erros E* de import/atributo |
| ↳ mypy, cache quente | — | 23,0 s | Idem | Tipagem estrita, inclusive entre módulos |
| ↳ mypy, cache frio | — | 65,5 s (1 rodada) | Idem | Idem |
| `Test-PowerShellGovernance.ps1` (processo novo) | 3,1 s | **33,6 s** | Respeita `-Paths`. Completo = todos os `.ps1/.psm1` rastreados (102) | PSScriptAnalyzer (**só aviso, não bloqueia**) + regex de `catch {}` genérico (bloqueia) |
| `Test-NodeCommunications.ps1` | 0,7 s + 3,4 s (`lib`) | 0,9 s + 3,4 s (`lib`) | **Ignora `-Paths`**: sempre roda `npm test` em `Receitas Bloqueadas` e em `lib` | Contrato offline de WhatsApp + cobertura ≥ 90% de `WhatsApp-Core.js` |
| `Test-ZeroTrust.ps1` | 0,03 s | 4,2 s | Respeita `-Paths` | Credencial hardcoded |
| `Test-PortablePaths.ps1` | 0,02 s | 3,8 s | Respeita `-Paths` | Caminho absoluto |
| `Test-SourceEncoding.ps1` | 0,01 s | 0,7 s | Respeita `-Paths` | BOM/UTF-8 por extensão |
| `Test-SqlPerformance.ps1` | 0,01 s | 0,6 s | Respeita `-Paths` | Anti-padrões de SQL |
| `Test-LogEventSchema.ps1` | 0,25 s | 0,31 s | Respeita `-Paths` (sobe um Python fixo para as amostras) | Schema do envelope de log |
| `Test-ArchitectureStandard.ps1` | 0,07 s | 0,20 s | Respeita `-Paths` | Camadas (Oracle, `session_scope`, subprocess) |
| `Test-JsonConfig.ps1` | 0,01 s | 0,16 s | Respeita `-Paths` | JSON válido |
| `Test-PowerShellApprovedVerbs.ps1` | 0,03 s | 0,11 s | Respeita `-Paths` | Verbos aprovados |
| `Test-AutomationCatalog.ps1` | 0,04 s | 0,10 s | Filtra os manifestos por `-Paths` | Manifesto de automação |
| `Test-SemanticGovernance.ps1` | 0,08 s | 0,09 s | Ignora `-Paths` (sempre global, barato) | Mapa de criticidade × manifestos |
| `Test-DateConformidade.ps1` | 0,02 s | 0,09 s | Respeita `-Paths`. Sem `-Paths`, cai em `-StagedOnly` (não em `-All`) | Formato de data em código e Markdown |
| `Test-PlaywrightEvidence.ps1` | 0,03 s | 0,01 s | Ignora `-Paths` (sempre global, barato) | Evidência E2E |
| **Soma `governanca_nativa`** | **≈ 15 s** | **≈ 370 s** | | |

A soma completa passa dos 302 s observados no commit real por dois motivos. Primeiro, o PSScriptAnalyzer foi contado em processo novo. Segundo, a rodada 3 do Python levou 277 s, contra uma mediana de 317 s, o que mostra a faixa de ruído. A ordem de grandeza confere: o commit de 304 s foi uma varredura completa.

Fora da `governanca_nativa`, o CI registrou `governanca_skills` em 4,2 s e `governanca_dashboard_template` em 0,4 s. O `pwsh` vazio custa 0,5 s por processo.

### Custo do pylint por grupo (varredura completa)

`Orchestrator\tests` (115 arquivos) 66 s · `Orchestrator\app\services` 28 s · `Orchestrator\app` 25 s · `Orchestrator\app\routers` 19 s · `Receitas Bloqueadas` (1 arquivo) 17 s · `Tools\oracle` 14 s · `Orchestrator` (`worker.py`) 11 s · os 15 grupos restantes juntos ≈ 77 s. Grupos pequenos custam 2 a 5 s só de startup e inferência do astroid.

Paralelismo interno do pylint **não ajuda**: no grupo `Orchestrator\tests`, `-j 4` levou 60,8 s, contra 61,9 s em série.

## Cobertura do CI (o que pode sair do hook)

- O job `governanca-agregada` (`windows-latest`, sem `if:`) roda `ValidarAutomacoes.ps1 -OnlyGovernance` **sem `-StagedOnly`**, ou seja, a varredura completa das 15 checagens, em todo push para `main`/`escalar/**` e em todo PR. Ele instala `requirements-dev.txt` + `requirements-test.txt` e faz `npm ci --prefix lib`. Falha nele derruba o `Resumo final`. No run 44168117220 (17/11/2026), o Python levou 168 s e a etapa inteira, 194 s.
- Ressalva: **o `main` não tem branch protection** (`gh api .../branches/main/protection` → 404). O CI bloqueia o merge por disciplina do fluxo PR→CI→merge, não por regra do GitHub. Um push direto no `main` só descobre a falha depois.
- O que **não pode** sair do hook, porque o CI não cobre ou cobre tarde demais:
  - **Push direto no `main`.** Sem proteção de branch, o hook é a única barreira antes do commit chegar ao remoto. Ou o hook continua completo para o que é crítico, ou o `governanca-agregada` vira check obrigatório.
  - **`Test-LogConformidade.ps1`** só roda no CI quando `has_log_targets`, e o CI usa o mesmo `-Paths`. Não há ganho em mexer nele: custa milissegundos.
  - **Checagens de milissegundos** (encoding, JSON, data, verbos, arquitetura, catálogo, semântica, Playwright, SQL). Não há motivo para tirá-las do hook.
  - **O veto a `pylint: disable=all` fora do baseline.** É barato, lê só as 3 primeiras linhas, e deve continuar global.

## Plano, por ordem de ganho

Os ganhos abaixo são para o commit **com caminho crítico** (o caso de 304 s). O commit direcionado já fica em ~15 s e ganha pouco em termos absolutos.

0. **Fechar o buraco de encoding antes de qualquer otimização (integridade, não tempo).** Forçar UTF-8 na leitura da saída do git. Por exemplo, `[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)` no início de `ValidarAutomacoes.ps1` e nos scripts que chamam `git ls-files`/`git diff` (ou `$OutputEncoding` + `git -c core.quotepath=false`). Depois disso, os 33 `.py` de `Produção Beneficimento/` passam a ser verificados. Medido em 18/11/2026: passam limpos hoje (mypy 6,4 s, pylint 19,4 s), então a correção não quebra o build, mas **custa cerca de 26 s na varredura completa**. O mesmo defeito afeta qualquer arquivo staged com acento no nome no modo direcionado, para todas as checagens que fazem `Test-Path`. Vale também verificar se o `catch {}` e o ZeroTrust já deixaram passar algo nesses arquivos.
1. **Pylint só no diff, mesmo com promoção a `full_scan` (≈ −220 s).** Na varredura completa, rodar o pylint apenas sobre os `.py` staged, mais os arquivos do repositório que importam módulos staged (dependentes diretos, achados por grep de `import`/`from`). Esses dependentes cobrem o caso E0611/E1101 de um nome removido. O pylint completo continua no CI, bloqueante. Custo estimado: 5 a 15 s, conforme o diretório. Não enfraquece o gate porque o CI roda o pylint completo e a regra do pylint é essencialmente local ao arquivo.
2. **PSScriptAnalyzer só no diff (≈ −31 s).** Ele só emite `[AVISO]` e não muda o código de saída. Na varredura completa, rodá-lo só nos `.ps1/.psm1` staged, mantendo a regex bloqueante de `catch {}` em todos os arquivos (milissegundos). **Não enfraquece nada**, porque a parte que bloqueia continua global. Quando o diff não tiver PowerShell, pular também o import do módulo (~3 s de custo fixo).
3. **Mypy completo, mas sempre com cache quente (≈ −40 s no caso frio).** O mypy completo é a rede contra quebras entre módulos e custa só 23 s quente, então deve ficar no hook. Hoje o cache esfria em dois casos: (a) `AplicarPoliticaRetencao.ps1` apaga `.mypy_cache`, chamado pelo `ValidarAutomacoes.ps1` sem `-OnlyGovernance`; (b) cada worktree novo começa sem cache (66 s no primeiro commit). Proposta: tirar `.mypy_cache` da lista da política de retenção, ou pelo menos preservar o cache do mypy. Para worktrees, opcionalmente aquecer o cache na criação (o `cache_dir` compartilhado entre worktrees não é seguro, porque os caminhos absolutos diferem).
4. **Paralelizar os blocos independentes (≈ −10 a −30 s).** Rodar o mypy, o pylint do diff, o bloco PowerShell e o bloco Node em processos separados (`Start-Job`/`Start-Process`, coletando o código de saída e o log de cada um) e as checagens de milissegundos em série. Com 4 núcleos e o pylint já reduzido, o tempo de parede passa a ser o do mypy (~23 s). Atenção à regra de `Test-PythonGovernance.ps1` sobre arrays em `pwsh -File`: o paralelismo tem que passar os caminhos por arquivo ou por `-Command`, nunca por `-File` com array.
5. **Node só quando o diff toca JS/`lib`/`Receitas Bloqueadas` (≈ −4 s).** Hoje `Test-NodeCommunications.ps1` ignora `-Paths`. O CI já roda as duas suítes. Ganho pequeno; fica por último.

### Projeção

| Cenário | Hoje | Após 0+1+2+3 (em série) | Após 0–4 (paralelo) |
| --- | --- | --- | --- |
| Commit com caminho crítico, cache quente | ≈ 302 s | ≈ 60 s | **≈ 30 s** |
| Commit com caminho crítico, worktree novo | ≈ 345 s | ≈ 100 s | ≈ 70 s (cair abaixo de 1 min exige aquecer o cache, item 3) |
| Commit direcionado (1 `.py` + 1 `.ps1`) | ≈ 15 s | ≈ 15 s | ≈ 12 s |

### Decisões que são do usuário

- Tornar o `governanca-agregada` check obrigatório no `main` (branch protection). É o que transforma o item 1 de "seguro pelo fluxo" em "seguro por regra".
- Aceitar os +26 s do item 0. É cobertura que hoje falta, não regressão.
- Corrigir a skill `ci-gates` (e o `CLAUDE.md`, que repete a frase): o CI **roda** mypy `--strict` bloqueante, no `governanca-agregada`. O que muda é que o hook pega o erro antes, no commit.

## Resultado da implementação (18/11/2026)

Os itens 0 a 4 foram implementados, mas não o 5 (Node segue rodando sempre). A bancada usou dois worktrees temporários no mesmo commit: "antes" com o código do `main` e "depois" com os `Tools` alterados. Os dois receberam os mesmos arquivos staged e foram executados exatamente como o hook faz (`pwsh -File Tools\ValidarAutomacoes.ps1 -BasePath <raiz> -OnlyGovernance -StagedOnly`). Cada cenário teve 3 rodadas intercaladas, depois de uma rodada de aquecimento do cache do mypy.

| Cenário | Antes (mediana) | Depois (mediana) |
| --- | --- | --- |
| Caminho crítico: `Tools\Get-GovernanceTargetSummary.ps1` + 1 `.py` + 1 `.ps1` staged | 314,9 s (291–326) | **35,8 s** (34–40) |
| Direcionado: 1 `.py` + 1 `.ps1` staged | 12,4 s (10–13) | **8,8 s** (8–9) |
| Primeiro commit no worktree, sem cache do mypy (1 rodada) | 368,5 s | 75,5 s |

Nos worktrees temporários, a suíte Node de `lib/` foi pulada nos dois lados, porque falta `node_modules`. No checkout principal ela soma cerca de 3 s, que no "depois" correm em paralelo.

### Prova de que os gates continuam reprovando

Cada caso injetou uma violação, colocou o arquivo em staged e rodou o hook real. Em todos, o arquivo foi restaurado em seguida.

| Caso | Modo | Resultado |
| --- | --- | --- |
| Erro de tipo em `.py` staged | full_scan | exit 1, `Falha de Tipagem Estrita (Mypy)` |
| Variável não usada em `.py` staged (só pylint) | full_scan | exit 1, `Falha de Qualidade de Codigo (Pylint)` |
| Função renomeada em `lib/python/oracle_session.py` (quebra quem importa) | full_scan | exit 1; pylint incluiu 11 arquivos (alterado + dependentes) e reprovou em 4 grupos |
| `catch` genérico em `.ps1` staged | full_scan | exit 1 |
| `catch` genérico em `.ps1` staged | direcionado | exit 1 |
| Atribuição de chave de API com valor literal em `.py` staged | full_scan | exit 1 (ZeroTrust) |
| `process.exit(1)` no teste Node de `Receitas Bloqueadas` | direcionado | exit 1, falha propagada pelo job paralelo |
| Erro de tipo em `Produção Beneficimento/.../health.py` | direcionado e full_scan | exit 1 no depois. O antes também reprovou quando rodado pelo hook, ver abaixo |

Sobre o item 0: chamado pela bancada, o `ValidarAutomacoes.ps1` antigo listou os 33 arquivos de `Produção`. Já o mesmo `Test-PythonGovernance.ps1` antigo, chamado direto por `pwsh -File`, resolveu só 240 de 273, e o CI também verificou 240. A causa exata dessa diferença de contexto não foi isolada. A correção força UTF-8 nos dois caminhos e elimina a dependência do console. O CI deste PR é a confirmação que falta: o `governanca-agregada` deve listar 273 arquivos.

Também foram rodados `pytest` (1871 aprovados, 8 pulados) e Pester 5.7.1 sobre `lib\tests` (367 de 367).

## Observações laterais

- O hook prefere `pwsh` 7 quando ele está instalado, enquanto o runtime de produção usa `powershell.exe` 5.1 de propósito. Não afeta o tempo medido, mas o gate testa os `.ps1` num runtime diferente do de produção.
- O Stop hook do Claude (`Assert-StopQualityGate.ps1`) já usa `-NoCriticalPromotion`. O estouro de 240 s dele não vem da promoção, e precisa de medição própria. Os itens 1 e 3 provavelmente também o beneficiam.
