# Security Governance: Automacoes Hub

## Repository Security Philosophy
Este projeto opera sob uma politica de **Confianca Zero Local** e **Isolamento de Credenciais**. O objetivo e garantir que dados sensiveis da Costa Rica Malhas nunca vazem atraves de logs, codigo fonte ou artefatos de manutencao.

---

## 1. Zero-Secrets Policy
**Regra de Ouro:** E terminantemente proibido o hardcode de senhas, tokens ou chaves de API em qualquer arquivo `.ps1`, `.py`, `.vbs`, `.js`, `.bas` ou `.cls`.

### Como gerenciar segredos:
- **Desenvolvimento:** Utilize o arquivo `.env` (ja listado no `.gitignore`).
- **Producao:** Utilize as Variaveis de Ambiente de Sistema ou o Windows Credential Manager.
- **VBA:** Segredos devem ser injetados via ambiente pelo orquestrador PowerShell, nunca salvos em planilhas ou constantes de codigo.

---

## 2. Auto-Masking (Logging Hardening)
A biblioteca central `lib/Lib-Logging.psm1` implementa a redacao automatica de PII (Personally Identifiable Information).

- **E-mails:** Sao mascarados automaticamente (ex: `g***@domain.com`).
- **Segredos:** Padroes como `password=`, `token:`, `key:` sao detectados via regex e substituidos por `[REDACTED]`.
- **Infraestrutura:** Strings de conexao Oracle tem o Host ocultado automaticamente nos logs.

---

## 3. Data Integrity & Base64 Bridge
Para garantir que logs tecnicos e dados corporativos (que contem acentos e cedilhas) nao sejam corrompidos, utilizamos o **Base64 Bridge Protocol** (`B64:...`) entre camadas. Isso blinda o Portugues Brasileiro contra as falhas de encoding do Windows.

Para grandes volumes de dados (JSON), utilizamos o **Secure File-Payload Protocol**, trafegando informacoes via arquivos temporarios protegidos e excluidos imediatamente apos o uso, evitando a corrupcao do buffer de memoria do terminal.

---

## 4. Auditoria e Conformidade
Todas as alteracoes de codigo sao filtradas pelo `pre-commit` hook, que impede:
1.  Vazamento de caracteres nao-ASCII em modulos VBA e scripts (ASCII-Safe Core).
2.  Sincronismo inconsistente entre Git e XLSM (Drift Check).
3.  Logs fora do padrao canonico ou com datas em formato nao-BR.
4.  Ausencia de cabecalhos de contexto AI-Native e arquivos `CONTEXT.md`.

---

## 5. Reportando Vulnerabilidades
Se voce identificar uma falha de seguranca em qualquer automacao, notifique imediatamente a gestao de TI e abra um ticket de **Soberania de Dados** para correcao cirurgica por IA.
