/**
 * Painel de revisão do modal de automação.
 * Lê o estado compartilhado (state) e funções de ctx para renderizar
 * as quatro seções do tab de revisão.
 */

export function createReviewModule(ctx, state) {
    const { escapeHtml, translateStatus, getValue } = ctx;

    function clearReviewPanel() {
        ["automation-review-summary", "automation-review-preview", "automation-review-impact"].forEach((id) => {
            const el = document.getElementById(id);
            if (el) el.innerHTML = '<div class="empty-state">Preencha os campos para gerar o conteúdo desta etapa.</div>';
        });
        const governance = document.getElementById("automation-review-governance");
        if (governance) governance.innerHTML = '<div class="empty-state">A validação governada será exibida antes do save.</div>';
    }

    function refreshReviewPanel() {
        renderReviewSummary();
        renderReviewPreview();
        renderReviewImpact();
        renderReviewGovernance();
    }

    function renderReviewSummary() {
        const container = document.getElementById("automation-review-summary");
        if (!container) return;
        const name = getValue("f-name") || "Automação sem nome";
        const path = getValue("f-path") || "Caminho ainda não informado";
        const queueGroup = getValue("f-queue-group") || "Sem grupo operacional";
        const mode = document.getElementById("f-test")?.checked ? "Modo teste" : "Modo produtivo";
        const enabled = document.getElementById("f-enabled")?.checked ? "Ativa" : "Pausada";
        const lastContext = state.currentAutomationContext?.last_execution_started_at
            ? `<small>Última execução: ${escapeHtml(state.currentAutomationContext.last_execution_started_at)}${state.currentAutomationContext.last_status ? ` · ${escapeHtml(translateStatus(state.currentAutomationContext.last_status))}` : ""}</small>`
            : "<small>Sem histórico carregado para esta automação.</small>";

        container.innerHTML = `
            <div class="review-item">
                <strong>${escapeHtml(name)}</strong>
                <p>${escapeHtml(path)}</p>
                <small>Fila: ${escapeHtml(queueGroup)} · ${escapeHtml(mode)} · ${escapeHtml(enabled)}</small>
                ${lastContext}
            </div>
            <div class="review-item">
                <strong>Resiliência e canais</strong>
                <p>Timeout ${escapeHtml(getValue("f-max-runtime") || "30")} min · Retry ${escapeHtml(getValue("f-max-retries") || "0")} · Cooldown ${escapeHtml(getValue("f-cooldown") || "0")} min</p>
                <small>Canais: ${escapeHtml(getValue("f-notification-channels") || "não informados")}</small>
            </div>
        `;
    }

    function renderReviewPreview() {
        const container = document.getElementById("automation-review-preview");
        if (!container) return;
        const preview = state.latestSchedulePreview;
        const summaryLabel = preview?.schedule_summary || document.getElementById("schedule-summary")?.innerText || "Agenda ainda não validada.";
        const nextRuns = Array.isArray(preview?.next_runs_preview) ? preview.next_runs_preview : [];
        container.innerHTML = `
            <div class="review-item">
                <strong>${escapeHtml(summaryLabel)}</strong>
                <p>${nextRuns.length ? escapeHtml(nextRuns.join(" | ")) : "Sem execução futura ou sem agenda configurada."}</p>
                <small>Tipo: ${escapeHtml((preview?.schedule_type || state.scheduleType || "manual").toUpperCase())}</small>
            </div>
        `;
    }

    function renderReviewImpact() {
        const container = document.getElementById("automation-review-impact");
        if (!container) return;
        const retries = Number(getValue("f-max-retries") || 0);
        const cooldown = Number(getValue("f-cooldown") || 0);
        const queueGroup = getValue("f-queue-group") || "sem grupo";
        const mode = document.getElementById("f-test")?.checked ? "O fluxo será executado em modo teste." : "O fluxo poderá atuar em ambiente produtivo.";
        const retryNote = retries > 0
            ? `Permitirá ${retries} tentativa(s) automática(s) com cooldown de ${cooldown} minuto(s).`
            : "Não haverá retry automático; a recuperação dependerá de ação operacional.";
        container.innerHTML = `
            <div class="review-item">
                <strong>Impacto operacional</strong>
                <p>${escapeHtml(mode)}</p>
                <small>Grupo operacional: ${escapeHtml(queueGroup)}. ${escapeHtml(retryNote)}</small>
            </div>
            <div class="review-item">
                <strong>Validação antes do save</strong>
                <p>A agenda foi validada pelo backend e a prévia de próximas execuções foi recalculada.</p>
                <small>Se a configuração estiver incorreta, o save permanece bloqueado.</small>
            </div>
        `;
    }

    function renderReviewGovernance() {
        const container = document.getElementById("automation-review-governance");
        if (!container) return;
        const preflight = state.latestAutomationPreflight;
        if (!preflight) {
            container.innerHTML = '<div class="empty-state">A pré-validação governada aparecerá após a revisão da agenda.</div>';
            return;
        }

        const governance = preflight.governance || {};
        const blockingIssues = Array.isArray(governance.blocking_issues) ? governance.blocking_issues : [];
        const warnings = Array.isArray(governance.warnings) ? governance.warnings : [];
        const status = String(governance.status || "healthy").toLowerCase();

        if (status === "incident") {
            container.innerHTML = `
                <div class="review-item danger">
                    <strong>Save bloqueado pelo manifesto governado</strong>
                    <p>${escapeHtml(governance.top_issue || "Há inconsistências entre cadastro e manifesto.")}</p>
                    <small>${escapeHtml(blockingIssues[0]?.message || governance.recommended_action || "Alinhe o automation.manifest.json antes de salvar.")}</small>
                </div>
            `;
            return;
        }

        if (status === "attention") {
            container.innerHTML = `
                <div class="review-item warning">
                    <strong>Governança em atenção</strong>
                    <p>${escapeHtml(governance.top_issue || "Há avisos operacionais para esta automação.")}</p>
                    <small>${escapeHtml(warnings[0]?.message || governance.recommended_action || "Revise os avisos antes da promoção.")}</small>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="review-item success">
                <strong>Governança validada</strong>
                <p>${escapeHtml(governance.top_issue || "Cadastro alinhado ao manifesto governado.")}</p>
                <small>${escapeHtml(governance.catalog_id ? `Catálogo ${governance.catalog_id}` : "Manifesto validado.")}</small>
            </div>
        `;
    }

    return { clearReviewPanel, refreshReviewPanel, renderReviewGovernance };
}
