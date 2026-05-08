# Log de Incidentes e Resoluções

Este documento registra falhas críticas e as correções estruturais aplicadas para evitar recorrência.

---

## [2026-05-08] Incidente DPY-3015: Falha de Autenticação Oracle (Receitas Emitidas)

### Descrição
O incidente das 07:05 ocorreu porque o Python tentou logar no banco sem o client local (`oci.dll`), forçando o _Thin Mode_ (que não aceita a senha criptografada tipo `0x939`).

### Correções Aplicadas
1.  **Configuração de Ambiente**: O `.env` agora possui o `ORACLE_CLIENT_LIB_DIR` explicitamente configurado.
2.  **Pre-Flight Robusto**: O `run.ps1` agora verifica ativamente se a `oci.dll` existe localmente no boot. Se falhar, aciona a fila de retry.
3.  **Thick Mode Obrigatório**: O `extract_oracle.py` aborta a conexão se não conseguir ativar o modo Thick.

---

*Nota: Este arquivo é mantido como histórico técnico para auditoria.*
