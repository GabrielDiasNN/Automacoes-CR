# Agente de Revisão de Código (Declarativo)

Este diretório contém a especificação formal do **Agente de Revisão de Código** no Hub de Automações.

## Estrutura da Pasta
* **`agent.json`**: Metadados declarativos, regras inegociáveis, filtros estruturados e prompt de sistema do agente para consumo programático por orquestradores de IA.
* **`README.md`**: Este guia explicativo rápido de uso e referência técnica.

---

## 🎯 Filosofia de Operação (V.A.L.E.G.)

O agente opera sob o rigor estrito do **Protocolo V.A.L.E.G.** (Validação, Arquitetura, Logging, Escala e Governança), focando em:
1. **Encoding Estrito**: scripts PowerShell (`.ps1`/`.psm1`) em `UTF-8 com BOM` e os demais em `UTF-8 sem BOM`.
2. **Formato de Datas**: padrão brasileiro `DD/MM/YYYY` em exibições, logs ativos e documentações.
3. **Zero-Trust**: proibição absoluta de segredos, tokens ou caminhos rígidos locais do Windows.
4. **Catálogo Versionado**: validação de `automation.manifest.json` e runbooks operacionais.

---

## 💻 Como Executar a Revisão Local

Para rodar a auditoria estática rápida com velocidade DX antes de realizar um commit, execute o utilitário na raiz do repositório:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Review-Code.ps1
```

O script lerá a lista de arquivos alterados (*staged files*), aplicará as checagens estáticas do orquestrador e emitirá o veredicto estruturado conforme as definições contidas no `agent.json`.
