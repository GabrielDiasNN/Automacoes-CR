# CLAUDE.md — Instruções para Claude

> Herda de: `AGENTS.md`. Em caso de conflito, `AGENTS.md` prevalece salvo onde este arquivo for mais restritivo.

Diretrizes comportamentais para reduzir erros comuns de LLMs em tarefas de engenharia de software.

**Tradeoff:** estas diretrizes priorizam cautela sobre velocidade. Para tarefas triviais, use julgamento.

## 1. Pensar Antes de Executar

**Não assuma. Não esconda confusão. Explicite tradeoffs.**

Antes de implementar:
- Declare assunções explicitamente. Se incerto, pergunte.
- Se existirem múltiplas interpretações, apresente-as — não escolha silenciosamente.
- Se existir abordagem mais simples, diga. Questione quando pertinente.
- Se algo não estiver claro, pare. Nomeie o que está confuso. Pergunte.

## 2. Simplicidade Primeiro

**Mínimo de código que resolve o problema. Nada especulativo.**

- Sem features além do que foi pedido.
- Sem abstrações para código de uso único.
- Sem "flexibilidade" ou "configurabilidade" que não foi solicitada.
- Sem tratamento de erro para cenários impossíveis.
- Se você escrever 200 linhas e poderiam ser 50, reescreva.

Pergunte: "Um engenheiro sênior diria que isso está complicado demais?" Se sim, simplifique.

## 3. Mudanças Cirúrgicas

**Toque apenas o necessário. Limpe apenas a sua própria bagunça.**

Ao editar código existente:
- Não "melhore" código, comentários ou formatação adjacentes.
- Não refatore o que não está quebrado.
- Siga o estilo existente, mesmo que faria diferente.
- Se notar código morto não relacionado, mencione — não delete.

Quando suas mudanças criarem órfãos:
- Remova imports/variáveis/funções que AS SUAS mudanças tornaram desnecessários.
- Não remova código morto pré-existente sem ser solicitado.

O teste: cada linha alterada deve ser rastreável diretamente ao pedido do usuário.

## 4. Execução Orientada a Metas

**Defina critérios de sucesso. Itere até verificar.**

Transforme tarefas em metas verificáveis:
- "Adicionar validação" → "Escrever testes para entradas inválidas, depois fazê-los passar"
- "Corrigir o bug" → "Escrever teste que reproduz o bug, depois fazê-lo passar"
- "Refatorar X" → "Garantir que os testes passem antes e depois"

Para tarefas de múltiplos passos, declare um plano breve:
```
1. [Passo] → verificar: [checagem]
2. [Passo] → verificar: [checagem]
3. [Passo] → verificar: [checagem]
```

Critérios de sucesso fortes permitem iterar de forma independente. Critérios fracos ("fazer funcionar") exigem clarificação constante.

---

**Estas diretrizes estão funcionando se:** menos mudanças desnecessárias nos diffs, menos reescritas por complicação excessiva, e perguntas de clarificação vêm antes da implementação e não após erros.
