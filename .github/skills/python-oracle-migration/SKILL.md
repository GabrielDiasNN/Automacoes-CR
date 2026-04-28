---
name: python-oracle-migration
description: Use when migrating legacy VBA/M logic to Python and extracting or processing data from Oracle.
---

# 1. Purpose
Orientar a reescrita de lógicas legadas (VBA, Power Query, VBScript) para Python, com foco agressivo em performance, vetorização de dados e otimização de consultas Oracle.

# 2. When to Use
- Ao substituir fluxos de processamento em planilhas por processamento em lote em Python.
- Na construção de queries SQL contra o banco de dados Oracle.

# 3. Do Not Use When
- Em automações focadas exclusivamente em interface gráfica de sistemas locais.

# 4. Related Skills
- enterprise-orchestration-contract

# 5. Non-Negotiable Rules
- **Complexidade de Algoritmo (O(n))**: Priorizar a complexidade O(n) ou melhor. Loops iterativos manuais (como `for`/`while`) para processamento de dados massivo são proibidos.
- **Vetorização Obrigatória**: O processamento de dados deve obrigatoriamente utilizar as operações vetorizadas de bibliotecas como `pandas` ou `polars`/`numpy`.
- **Tipagem Estrita**: O uso de Type Hints é obrigatório em todas as funções Python (ex: `def processar_dados(a: int) -> str:`).
- **SQL Otimizado**: Exige-se o uso de *bind variables* (evitando hard parse). Consultas com `SELECT *` são expressamente proibidas. Focar sempre no plano de execução e no custo (Cost) da consulta.
- **Tratamento de Exceções**: Blocos de exceções (`try/except/finally`) devem ser nominais e específicos; é proibida a captura genérica de erros.
## Purpose
- Conforme diretrizes globais.

## When to Use
- Conforme diretrizes globais.

## Do Not Use When
- Conforme diretrizes globais.

## Related Skills
- Conforme diretrizes globais.

## Non-Negotiable Rules
- Conforme diretrizes globais.

## Repo-Specific Constraints
- Conforme diretrizes globais.

## Validation
- Conforme diretrizes globais.

## Troubleshooting
- Conforme diretrizes globais.

## Pre-Delivery Checklist
- Conforme diretrizes globais.

