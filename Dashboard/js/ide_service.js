/**
 * ide_service.js - Central de Automações v6.2.0
 * Gestão de .env, Editores JSON e Web IDE.
 */

import { api, showToast } from './api.js';

export async function loadEnv() {
    const data = await api("/api/system/env");
    if (data && data.content !== undefined) {
        document.getElementById("env-editor").value = data.content;
    } else {
        showToast("Erro ao carregar o arquivo .env", "error");
    }
}

export async function saveEnv() {
    if (!confirm("Tem certeza que deseja salvar o Ambiente Global? Algumas variáveis podem exigir reinício.")) return;
    const content = document.getElementById("env-editor").value;
    const res = await api("/api/system/env", "PUT", { content });
    if (res) showToast(res.message || "Ambiente Global salvo!", "success");
}

let currentJsonConfigs = [];

export async function openJsonModal(autoId, autoName) {
    document.getElementById("json-modal-title").innerText = `Regras: ${autoName}`;
    document.getElementById("json-auto-id").value = autoId;
    const selector = document.getElementById("json-file-selector");
    const editor = document.getElementById("json-editor");
    selector.innerHTML = "<option>Carregando...</option>";
    editor.value = "";
    document.getElementById("modal-json").showModal();
    const configs = await api(`/api/automations/${autoId}/configs`);
    if (configs && configs.length > 0) {
        currentJsonConfigs = configs;
        selector.innerHTML = configs.map(c => `<option value="${c.filename}">${c.filename}</option>`).join("");
        loadSelectedJsonFile();
    } else {
        selector.innerHTML = "<option value=''>Nenhum JSON encontrado</option>";
        editor.value = "Sem arquivos configuráveis.";
        editor.disabled = true;
    }
}

export function loadSelectedJsonFile() {
    const filename = document.getElementById("json-file-selector").value;
    const editor = document.getElementById("json-editor");
    if (!filename) return;
    const config = currentJsonConfigs.find(c => c.filename === filename);
    if (config) {
        editor.disabled = false;
        editor.value = config.content;
    }
}

export async function saveJsonFile() {
    const autoId = document.getElementById("json-auto-id").value;
    const filename = document.getElementById("json-file-selector").value;
    const content = document.getElementById("json-editor").value;
    try { JSON.parse(content); } catch (e) { return showToast("JSON inválido: " + e.message, "error"); }
    const res = await api(`/api/automations/${autoId}/configs/${filename}`, "PUT", { content });
    if (res) {
        showToast("JSON salvo!", "success");
        document.getElementById("modal-json").close();
    }
}

let currentIdeScripts = [];

export async function openIdeModal(autoId, autoName) {
    document.getElementById("ide-modal-title").innerText = `IDE: ${autoName}`;
    document.getElementById("ide-auto-id").value = autoId;
    const selector = document.getElementById("ide-file-selector");
    const editor = document.getElementById("ide-editor");
    selector.innerHTML = "<option>Carregando...</option>";
    editor.value = "";
    document.getElementById("modal-ide").showModal();
    const scripts = await api(`/api/automations/${autoId}/scripts`);
    if (scripts && scripts.length > 0) {
        currentIdeScripts = scripts;
        selector.innerHTML = scripts.map(s => `<option value="${s.filename}">${s.filename}</option>`).join("");
        loadSelectedIdeFile();
    } else {
        selector.innerHTML = "<option value=''>Nenhum script encontrado</option>";
        editor.value = "Nenhum arquivo .ps1, .py ou .sql encontrado.";
        editor.disabled = true;
    }
}

export function loadSelectedIdeFile() {
    const filename = document.getElementById("ide-file-selector").value;
    const editor = document.getElementById("ide-editor");
    if (!filename) return;
    const script = currentIdeScripts.find(s => s.filename === filename);
    if (script) {
        editor.disabled = false;
        editor.value = script.content;
    }
}

export async function saveIdeFile() {
    const autoId = document.getElementById("ide-auto-id").value;
    const filename = document.getElementById("ide-file-selector").value;
    const content = document.getElementById("ide-editor").value;
    if (!confirm(`Salvar alterações em ${filename}?`)) return;
    const res = await api(`/api/automations/${autoId}/scripts/${filename}`, "PUT", { content });
    if (res) {
        showToast("Código salvo!", "success");
        document.getElementById("modal-ide").close();
    }
}
