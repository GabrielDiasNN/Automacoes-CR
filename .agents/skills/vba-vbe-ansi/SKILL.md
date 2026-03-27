---
name: vba-vbe-ansi
description: Padrao obrigatorio para gerar, revisar e refatorar codigo VBA compativel com o VBE, evitando problemas de codificacao com ANSI/Windows-1252.
---

# Skill: VBA/VBE ANSI

## Objetivo

Garantir que todo codigo VBA gerado, revisado ou refatorado seja compativel com o Visual Basic Editor (VBE), evitando corrupcao de caracteres causada por diferencas entre UTF-8 e ANSI/Windows-1252.

## Regra principal

Considere que o ecossistema interno do VBA/VBE deve usar apenas caracteres ASCII simples sempre que houver risco de o texto residir, ser exibido ou ser editado dentro do VBE.

## Aplicacao obrigatoria

Aplique normalizacao ASCII nestes elementos:

- Nomes de variaveis
- Nomes de constantes
- Nomes de funcoes
- Nomes de subs
- Nomes de modulos
- Nomes de formularios e controles, quando relevante
- Comentarios
- Literais exibidos via `MsgBox`
- Literais exibidos via `Debug.Print`
- Textos internos usados apenas no VBA/VBE

## Exemplo de normalizacao

Use:
- `dataUltima`
- `ProcessarRelatorio`
- `' Verifica se a data e valida`
- `Debug.Print "Erro ao carregar configuracao"`
- `MsgBox "Operacao concluida com sucesso"`

Evite:
- `dataÚltima`
- `ProcessarRelatório`
- `' Verifica se a data é válida`
- `Debug.Print "configuração"`
- `MsgBox "Operação concluída"`

## Excecoes permitidas

Mantenha acentuacao somente quando a string for destinada a um ambiente externo que suporte UTF-8, Unicode ou renderizacao correta fora do VBE.

Casos comuns:
- `MailItem.HTMLBody`
- `MailItem.Subject`
- SQL enviado ao banco
- Conteudo HTML
- JSON para APIs
- Arquivos texto externos com codificacao definida
- Dados exibidos fora do editor VBA

## Regra de prioridade

Se houver duvida entre manter acentuacao ou garantir compatibilidade no VBE, priorize compatibilidade no VBE.

## Tratamento de texto corrompido

Se o prompt trouxer texto com mojibake ou caracteres corrompidos, corrija para a versao ASCII segura.

Exemplos:
- `InformaÃ§Ã£o` -> `Informacao`
- `AtenÃ§Ã£o` -> `Atencao`
- `UsuÃ¡rio` -> `Usuario`
- `ConfiguraÃ§Ã£o` -> `Configuracao`

## Comportamento esperado do agente

Ao gerar ou refatorar codigo VBA:
1. Remova acentos de todos os identificadores e textos internos do VBE.
2. Preserve acentos apenas em strings claramente externas.
3. Se o contexto nao estiver claro, use ASCII.
4. Ao revisar codigo legado, normalize o que puder causar problema de codificacao.
5. Nunca entregue codigo VBA com nomes acentuados.

## Checklist final

Antes de responder, valide:
- Ha acentos em nomes de variaveis, funcoes, subs ou constantes?
- Ha comentarios com caracteres especiais desnecessarios?
- Ha `MsgBox` ou `Debug.Print` com acentuacao?
- Strings externas foram preservadas apenas quando fizer sentido?
- O codigo pode ser colado no VBE sem risco de corrupcao visual?

## Observacao final

O objetivo nao e "proibir Unicode em qualquer contexto", e sim evitar problemas no que pertence ao ambiente interno do VBA/VBE.