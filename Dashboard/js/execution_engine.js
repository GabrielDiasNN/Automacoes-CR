/**
 * execution_engine.js - Central de Automações v6.2.0
 * Gestão de Execuções, Logs e Telemetria.
 */

import { api, showToast, LogStream, decodeLogLine } from './api.js';

let currentLogStream = null;

export async function stopExec(execId) {
    if (!confirm("Deseja realmente parar esta execução?")) return;
    const res = await api(`/api/executions/${execId}/stop`, "POST");
    if (res) {
        showToast("Execução interrompida.", "warning");
        return true;
    }
    return false;
}

export async function runAuto(id) {
    const res = await api(`/api/automations/${id}/start`, "POST");
    if (res) {
        showToast("Automação disparada com sucesso!", "success");
        return res.exec_id;
    } else {
        showToast("Falha ao disparar. Verifique se já não existe execução ativa.", "error");
        return null;
    }
}

export function parseLogFormat(rawText) {
    if (!rawText) return "";
    return rawText.split('\n').map(line => {
        if (!line.trim()) return '';
        let type = 'info';
        if (line.includes('ERROR') || line.includes('[ERRO]')) type = 'error';
        if (line.includes('WARN') || line.includes('[AVISO]')) type = 'warn';
        return `<span class="log-line ${type}">${line}</span>`;
    }).join('');
}

export async function openLogModal(execId) {
    const modal = document.getElementById("modal-logs");
    const output = document.getElementById("modal-log-body");
    const title = document.getElementById("log-modal-title");

    title.innerText = `Console: ${execId}`;
    output.innerHTML = "<i>Carregando logs...</i>";
    modal.showModal();

    const data = await api(`/api/executions/${execId}`);
    if (data && data.logs) {
        output.innerHTML = parseLogFormat(decodeLogLine(data.logs));
    } else {
        output.innerHTML = "(Sem logs disponíveis)";
    }

    if (data && (data.status === "RUNNING" || data.status === "PENDING")) {
        if (currentLogStream) currentLogStream.disconnect();
        currentLogStream = new LogStream(execId);
        currentLogStream.onMessage = (msg) => {
            const div = document.createElement("div");
            div.innerHTML = parseLogFormat(decodeLogLine(msg));
            output.appendChild(div);
            output.scrollTop = output.scrollHeight;
        };
        currentLogStream.onClose = () => {
            output.innerHTML += "<br/><i>--- Stream encerrado ---</i>";
        };
        currentLogStream.connect();
    }
    output.scrollTop = output.scrollHeight;
}

export function closeLogModal() {
    if (currentLogStream) {
        currentLogStream.disconnect();
        currentLogStream = null;
    }
    document.getElementById("modal-logs").close();
}
