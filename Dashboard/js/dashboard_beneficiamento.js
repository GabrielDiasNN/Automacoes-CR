/**
 * dashboard_beneficiamento.js - Cockpit PCP & OEE Têxtil v6.5.0
 * Módulo analítico integrado com o SQLite histórico real de 2026 (81.354 registros).
 */

export function createBeneficiamentoModule(ctx) {
    const {
        api,
        showToast,
        escapeHtml,
        bindActionElements,
    } = ctx;

    // Instâncias locais dos gráficos do ApexCharts
    const charts = {
        comparison: null, // OEE por Máquina
        ratios: null,     // Setup vs Processo (Stacked)
        turns: null,      // Distribuição por Turno
    };

    // Estado reativo local do cockpit
    const state = {
        analytics: null, // Armazena a resposta de /api/beneficiamento/historico/analytics
        filters: {
            search: "",
            machine: "",
            phase: "",
            turn: "",
            dt_inicio: "2026-01-01",
            dt_fim: "2026-12-31"
        }
    };

    // Lista de IDs dos KPIs para animação de CountUp
    const kpiIds = [
        "benef-kpi-lines",
        "benef-insight-turnos",
        "benef-kpi-kg",
        "benef-insight-mt",
        "benef-kpi-rendimento",
        "benef-kpi-efic",
        "benef-insight-desvio",
        "benef-insight-qualidade"
    ];

    // Formatadores numéricos padrão pt-BR
    const fmtInt = new Intl.NumberFormat("pt-BR");
    const fmt1 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    const fmt2 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

    function formatNumber(val, decimals = 2) {
        if (val === undefined || val === null || isNaN(Number(val))) return "-";
        return decimals === 0 ? fmtInt.format(Math.round(val)) : (decimals === 1 ? fmt1.format(val) : fmt2.format(val));
    }

    function formatPercent(val) {
        if (val === undefined || val === null || isNaN(Number(val))) return "-";
        return `${fmt1.format(val)}%`;
    }

    function formatToDateBr(isoString) {
        if (!isoString) return "-";
        try {
            const parts = isoString.split("T");
            const dateParts = parts[0].split("-");
            if (dateParts.length !== 3) return isoString;
            const [year, month, day] = dateParts;
            const dateBr = `${day}/${month}/${year}`;
            
            if (parts.length > 1) {
                const timeParts = parts[1].split(":");
                if (timeParts.length >= 2) {
                    return `${dateBr} ${timeParts[0]}:${timeParts[1]}`;
                }
            }
            return dateBr;
        } catch (e) {
            return isoString;
        }
    }

    /**
     * Carga dos dados analíticos de produção diretamente do SQLite histórico
     */
    async function loadBeneficiamento() {
        try {
            setBannerState("info", "Processando analíticos complexos de OEE e PCP no SQLite de 2026...");

            const dtInicioInput = document.getElementById("benef-filter-dt-inicio");
            const dtFimInput = document.getElementById("benef-filter-dt-fim");

            const dt_inicio = dtInicioInput ? dtInicioInput.value : state.filters.dt_inicio;
            const dt_fim = dtFimInput ? dtFimInput.value : state.filters.dt_fim;

            state.filters.dt_inicio = dt_inicio;
            state.filters.dt_fim = dt_fim;

            const queryParams = new URLSearchParams();
            if (dt_inicio) queryParams.append("dt_inicio", dt_inicio);
            if (dt_fim) queryParams.append("dt_fim", dt_fim);

            // Chamada FastAPI analítica ultra veloz indexada
            const data = await api(`/api/beneficiamento/historico/analytics?${queryParams.toString()}`);
            if (!data || !data.geral) {
                renderUnavailable();
                return;
            }

            state.analytics = data;

            // Renderização reativa de toda a tela
            render();
            setBannerState("success", "Cockpit PCP & OEE sincronizado com SQLite histórico!");
        } catch (error) {
            console.error("Erro ao carregar cockpit:", error);
            renderUnavailable();
            setBannerState("danger", "Falha ao processar analíticos de OEE no banco SQLite.");
            if (showToast) {
                showToast("Erro ao carregar cockpit analítico do SQLite.", "danger");
            }
        }
    }

    /**
     * Limpa os inputs de filtro
     */
    function resetFilterInputs() {
        state.filters.search = "";
        state.filters.machine = "";
        state.filters.phase = "";
        state.filters.turn = "";
        state.filters.dt_inicio = "2026-01-01";
        state.filters.dt_fim = "2026-12-31";

        const dtInicio = document.getElementById("benef-filter-dt-inicio");
        const dtFim = document.getElementById("benef-filter-dt-fim");
        const searchInput = document.getElementById("benef-filter-search");
        const machineSelect = document.getElementById("benef-filter-machine");
        const phaseSelect = document.getElementById("benef-filter-phase");
        const turnSelect = document.getElementById("benef-filter-turn");

        if (dtInicio) dtInicio.value = "2026-01-01";
        if (dtFim) dtFim.value = "2026-12-31";
        if (searchInput) searchInput.value = "";
        if (machineSelect) machineSelect.value = "";
        if (phaseSelect) phaseSelect.value = "";
        if (turnSelect) turnSelect.value = "";
    }

    /**
     * Vincula listeners dos filtros principais do cockpit
     */
    function setupFilters(root) {
        if (root.dataset.filtersBound) return;
        root.dataset.filtersBound = "true";

        const dtInicioInput = document.getElementById("benef-filter-dt-inicio");
        const dtFimInput = document.getElementById("benef-filter-dt-fim");
        const searchInput = document.getElementById("benef-filter-search");
        const machineSelect = document.getElementById("benef-filter-machine");
        const phaseSelect = document.getElementById("benef-filter-phase");
        const turnSelect = document.getElementById("benef-filter-turn");
        const clearBtn = document.getElementById("benef-filter-clear");

        const onDateChange = () => {
            // Alterações de data disparam nova consulta ao SQLite analítico
            loadBeneficiamento();
        };

        const onInteractiveFilterChange = () => {
            // Filtros textuais e de máquina/turno são aplicados em tempo real na tela
            state.filters.search = (searchInput?.value || "").trim().toLowerCase();
            state.filters.machine = machineSelect?.value || "";
            state.filters.phase = phaseSelect?.value || "";
            state.filters.turn = turnSelect?.value || "";
            applyInteractiveFilters();
        };

        dtInicioInput?.addEventListener("change", onDateChange);
        dtFimInput?.addEventListener("change", onDateChange);

        searchInput?.addEventListener("input", onInteractiveFilterChange);
        machineSelect?.addEventListener("change", onInteractiveFilterChange);
        phaseSelect?.addEventListener("change", onInteractiveFilterChange);
        turnSelect?.addEventListener("change", onInteractiveFilterChange);

        clearBtn?.addEventListener("click", () => {
            resetFilterInputs();
            loadBeneficiamento();
        });
    }

    /**
     * Popula opções dos filtros cruzados com os dados agregados recebidos
     */
    function populateFilterOptions() {
        if (!state.analytics) return;

        // Extrair máquinas
        const machineSelect = document.getElementById("benef-filter-machine");
        if (machineSelect) {
            const currentVal = machineSelect.value;
            let html = '<option value="">Todas as máquinas</option>';
            const sortedMaqs = [...state.analytics.maquinas].sort((a, b) => a.maquina.localeCompare(b.maquina));
            sortedMaqs.forEach(m => {
                html += `<option value="${escapeHtml(m.maquina)}">${escapeHtml(m.maquina)}</option>`;
            });
            machineSelect.innerHTML = html;
            machineSelect.value = currentVal;
        }

        // Fases comuns de tingimento têxtil estáticas para excelente performance de usabilidade
        const phaseSelect = document.getElementById("benef-filter-phase");
        if (phaseSelect) {
            const currentVal = phaseSelect.value;
            const fasesComuns = ["TINGIMENTO", "PREPARACAO", "LAVAGEM", "ACABAMENTO", "SECAR", "EXPEDICAO"];
            let html = '<option value="">Todas as fases</option>';
            fasesComuns.forEach(f => {
                html += `<option value="${f}">${f}</option>`;
            });
            phaseSelect.innerHTML = html;
            phaseSelect.value = currentVal;
        }

        // Popular turnos dinamicamente
        const turnSelect = document.getElementById("benef-filter-turn");
        if (turnSelect) {
            const currentVal = turnSelect.value;
            let html = '<option value="">Todos os turnos</option>';
            const sortedTurns = [...state.analytics.turnos].sort((a, b) => a.turno.localeCompare(b.turno));
            sortedTurns.forEach(t => {
                html += `<option value="${escapeHtml(t.turno)}">${escapeHtml(t.turno)}</option>`;
            });
            turnSelect.innerHTML = html;
            turnSelect.value = currentVal;
        }
    }

    /**
     * Aplica filtros interativos em memória sobre o payload já carregado do SQLite
     */
    function applyInteractiveFilters() {
        if (!state.analytics) return;

        const geral = state.analytics.geral;
        const produtos = state.analytics.produtos || [];
        const maquinas = state.analytics.maquinas || [];
        const operadores = state.analytics.operadores || [];
        const turnos = state.analytics.turnos || [];

        // 1. Filtrar Produtos
        const filteredProdutos = produtos.filter(p => {
            const matchSearch = !state.filters.search || 
                (p.reduz || "").toLowerCase().includes(state.filters.search) ||
                (p.produto || "").toLowerCase().includes(state.filters.search) ||
                (p.artigo || "").toLowerCase().includes(state.filters.search);
            return matchSearch;
        });

        // 2. Filtrar Máquinas
        const filteredMaquinas = maquinas.filter(m => {
            const matchMachine = !state.filters.machine || m.maquina === state.filters.machine;
            return matchMachine;
        });

        // 3. Filtrar Operadores
        const filteredOperadores = operadores.filter(op => {
            const matchSearch = !state.filters.search || op.operador.toLowerCase().includes(state.filters.search);
            return matchSearch;
        });

        // 4. Renderizar KPIs Superiores Vivos baseados no consolidado ou filtrado
        renderKPIs(geral, filteredProdutos, filteredMaquinas);

        // 5. Renderizar Tabelas e Gráficos Atualizados
        renderProdutosTable(filteredProdutos);
        renderOperadoresPodio(filteredOperadores);
        renderOeeChart(filteredMaquinas);
        renderSetupChart(filteredMaquinas);
        renderTurnChart(turnos);
    }

    /**
     * Atualiza os KPIs superiores com contagem animada
     */
    function renderKPIs(geral, filteredProds = null, filteredMaqs = null) {
        if (!geral) return;

        // Se houver filtros, ajustamos os volumes baseados no recorte
        let kg = geral.kg_total;
        let mt = geral.mt_total;
        let obs = geral.ob_distintas;
        let fases = geral.total_fases;
        let reprocesso = geral.taxa_reprocesso;
        let oee = geral.efic_tempo_media;
        let desvio = geral.desvio_min_total;
        let operadores = geral.total_operadores;

        if (state.filters.search || state.filters.machine || state.filters.phase || state.filters.turn) {
            // KPIs locais estimados do recorte em memória para interatividade
            if (filteredProds && filteredProds.length > 0) {
                kg = filteredProds.reduce((sum, p) => sum + p.kg_total, 0);
                mt = filteredProds.reduce((sum, p) => sum + p.mt_total, 0);
                reprocesso = filteredProds.reduce((sum, p) => sum + p.taxa_reprocesso, 0) / filteredProds.length;
            }
            if (filteredMaqs && filteredMaqs.length > 0) {
                oee = filteredMaqs.reduce((sum, m) => sum + ((m.min_prev / m.min_real) * 100), 0) / filteredMaqs.length;
                if (isNaN(oee) || !isFinite(oee)) oee = geral.efic_tempo_media;
                desvio = filteredMaqs.reduce((sum, m) => sum + (m.min_real - m.min_prev), 0);
            }
        }

        setText("benef-kpi-lines", formatNumber(obs, 0));
        setText("benef-insight-turnos", formatNumber(fases, 0));
        setText("benef-kpi-kg", formatNumber(kg, 0));
        setText("benef-insight-mt", formatNumber(mt, 0));
        
        // Reprocesso com badge de porcentagem
        setText("benef-kpi-rendimento", formatPercent(reprocesso));
        const rendSub = document.getElementById("benef-kpi-rendimento-sub");
        if (rendSub) {
            rendSub.innerHTML = reprocesso > 12 
                ? '<span class="badge badge-danger">Reprocesso Alto</span>' 
                : '<span class="badge badge-success">Meta OK</span>';
        }

        // Eficiência OEE
        setText("benef-kpi-efic", formatPercent(oee));
        const eficSub = document.getElementById("benef-kpi-efic-sub");
        if (eficSub) {
            eficSub.innerHTML = oee >= 80 
                ? '<span class="badge badge-success">Eficiência Ótima</span>' 
                : '<span class="badge badge-warning">Eficiência Regular</span>';
        }

        // Desvio de tempo
        setText("benef-insight-desvio", `${formatNumber(desvio, 0)} min`);
        setText("benef-insight-qualidade", formatNumber(operadores, 0));
    }

    /**
     * Gráfico OEE por Máquina
     */
    function renderOeeChart(maquinas) {
        const container = getElement("benef-comparison-chart");
        if (!container) return;

        if (!maquinas || maquinas.length === 0 || typeof ApexCharts === "undefined") {
            container.innerHTML = '<div class="empty-chart">Sem dados de OEE de máquinas.</div>';
            destroyChart("comparison");
            return;
        }

        // Limitar às 8 máquinas mais produtivas para ótima visualização
        const topMaqs = maquinas.slice(0, 8);
        const categories = topMaqs.map(m => m.maquina);
        const values = topMaqs.map(m => {
            const val = (m.min_prev / m.min_real) * 100;
            return isNaN(val) || !isFinite(val) ? 100.0 : roundTo(val, 1);
        });

        const options = {
            chart: {
                type: "bar",
                height: 280,
                toolbar: { show: false },
                animations: { enabled: true, speed: 600 }
            },
            series: [{ name: "Eficiência OEE %", data: values }],
            plotOptions: {
                bar: {
                    columnWidth: "45%",
                    borderRadius: 4,
                    borderRadiusApplication: "end"
                }
            },
            colors: ["#10b981"],
            fill: {
                type: "gradient",
                gradient: {
                    shade: "dark",
                    type: "vertical",
                    shadeIntensity: 0.2,
                    gradientToColors: ["#34d399"],
                    inverseColors: false,
                    opacityFrom: 0.85,
                    opacityTo: 0.85
                }
            },
            xaxis: { categories },
            yaxis: { max: 120, labels: { formatter: v => `${v}%` } },
            dataLabels: { enabled: false },
            tooltip: { theme: "dark", y: { formatter: v => `${v}%` } },
            grid: { borderColor: "rgba(148,163,184,0.06)" }
        };

        destroyChart("comparison");
        charts.comparison = new ApexCharts(container, options);
        charts.comparison.render();
    }

    /**
     * Gráfico de Tempo Setup vs Processamento (Barras Empilhadas Stacked)
     */
    function renderSetupChart(maquinas) {
        const container = getElement("benef-ratio-chart");
        if (!container) return;

        if (!maquinas || maquinas.length === 0 || typeof ApexCharts === "undefined") {
            container.innerHTML = '<div class="empty-chart">Sem dados de setup de máquinas.</div>';
            destroyChart("ratios");
            return;
        }

        const topMaqs = maquinas.slice(0, 8);
        const categories = topMaqs.map(m => m.maquina);
        const processing = topMaqs.map(m => roundTo(m.min_processo, 0));
        const setups = topMaqs.map(m => roundTo(m.min_setup, 0));

        const options = {
            chart: {
                type: "bar",
                stacked: true,
                height: 280,
                toolbar: { show: false },
                animations: { enabled: true, speed: 600 }
            },
            series: [
                { name: "Tempo Processo (min)", data: processing },
                { name: "Tempo Setup (min)", data: setups }
            ],
            plotOptions: {
                bar: {
                    columnWidth: "45%",
                    borderRadius: 4
                }
            },
            colors: ["#3b82f6", "#f59e0b"],
            xaxis: { categories },
            yaxis: { labels: { formatter: v => `${formatNumber(v, 0)} min` } },
            dataLabels: { enabled: false },
            tooltip: { theme: "dark", y: { formatter: v => `${v} min` } },
            grid: { borderColor: "rgba(148,163,184,0.06)" },
            legend: { position: "top", labels: { colors: "#aab7c7" } }
        };

        destroyChart("ratios");
        charts.ratios = new ApexCharts(container, options);
        charts.ratios.render();
    }

    /**
     * Gráfico de Distribuição por Turno
     */
    function renderTurnChart(turnos) {
        const container = getElement("benef-turn-chart");
        if (!container) return;

        if (!turnos || turnos.length === 0 || typeof ApexCharts === "undefined") {
            container.innerHTML = '<div class="empty-chart">Sem dados de turnos.</div>';
            destroyChart("turns");
            return;
        }

        const categories = turnos.map(t => t.turno);
        const values = turnos.map(t => roundTo(t.kg_total, 0));

        const options = {
            chart: {
                type: "bar",
                height: 280,
                toolbar: { show: false },
                animations: { enabled: true, speed: 600 }
            },
            series: [{ name: "Volume (KG)", data: values }],
            plotOptions: {
                bar: {
                    columnWidth: "40%",
                    borderRadius: 4,
                    borderRadiusApplication: "end"
                }
            },
            colors: ["#a855f7"],
            fill: {
                type: "gradient",
                gradient: {
                    shade: "dark",
                    type: "vertical",
                    shadeIntensity: 0.2,
                    gradientToColors: ["#c084fc"],
                    inverseColors: false,
                    opacityFrom: 0.85,
                    opacityTo: 0.85
                }
            },
            xaxis: { categories },
            yaxis: { labels: { formatter: v => `${formatNumber(v, 0)} kg` } },
            dataLabels: { enabled: false },
            tooltip: { theme: "dark", y: { formatter: v => `${formatNumber(v, 0)} kg` } },
            grid: { borderColor: "rgba(148,163,184,0.06)" }
        };

        destroyChart("turns");
        charts.turns = new ApexCharts(container, options);
        charts.turns.render();
    }

    /**
     * Renderiza o ranking prêmio dos operadores (Pódio)
     */
    function renderOperadoresPodio(operadores) {
        const container = document.getElementById("benef-operadores-podio");
        if (!container) return;

        if (!operadores || operadores.length === 0) {
            container.innerHTML = '<div style="color: var(--text-muted); font-style: italic; padding: var(--space-3);">Sem operadores no período.</div>';
            return;
        }

        // Ordenar os operadores por KG produzido e limitar aos 5 melhores
        const topOperadores = [...operadores].sort((a, b) => b.kg_total - a.kg_total).slice(0, 5);

        container.innerHTML = topOperadores.map((op, index) => {
            let medal = `<strong>${index + 1}º</strong>`;
            let medalStyle = 'background: rgba(148, 163, 184, 0.1); color: var(--text-secondary); width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700;';
            if (index === 0) {
                medal = '🥇';
                medalStyle = 'font-size: 1.4rem; width: 28px; text-align: center;';
            } else if (index === 1) {
                medal = '🥈';
                medalStyle = 'font-size: 1.2rem; width: 28px; text-align: center;';
            } else if (index === 2) {
                medal = '🥉';
                medalStyle = 'font-size: 1.1rem; width: 28px; text-align: center;';
            }

            const oeeClass = op.efic_tempo >= 85 ? "badge-success" : op.efic_tempo >= 70 ? "badge-warning" : "badge-danger";

            return `
                <div style="background: rgba(15, 23, 42, 0.35); border: 1px solid rgba(148, 163, 184, 0.08); padding: var(--space-3); border-radius: var(--radius-md); display: flex; align-items: center; justify-content: space-between; gap: var(--space-3);">
                    <div style="display: flex; align-items: center; gap: var(--space-3);">
                        <div style="${medalStyle}">${medal}</div>
                        <div>
                            <strong style="color: var(--text-primary); font-size: 0.9rem; font-weight: 700;">${escapeHtml(op.operador)}</strong>
                            <span style="font-size: 0.72rem; color: var(--text-muted); display: block;">${op.total_fases} fases concluídas</span>
                        </div>
                    </div>
                    <div style="text-align: right; display: flex; flex-direction: column; align-items: flex-end;">
                        <strong style="color: var(--accent-cyan); font-size: 0.95rem;">${formatNumber(op.kg_total, 0)} kg</strong>
                        <span class="badge ${oeeClass}" style="font-size: 0.65rem; font-weight: 700; margin-top: 3px;">OEE: ${op.efic_tempo}%</span>
                    </div>
                </div>
            `;
        }).join("");
    }

    /**
     * Preenche a tabela dinâmica de produtos enriquecida
     */
    function renderProdutosTable(produtos) {
        const tbody = document.getElementById("benef-product-tbody");
        const countBadge = document.getElementById("benef-product-count-badge");
        if (!tbody) return;

        if (!produtos || produtos.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: var(--space-4);">Nenhum produto atende aos filtros de busca.</td></tr>';
            if (countBadge) countBadge.textContent = "0 produtos";
            return;
        }

        if (countBadge) countBadge.textContent = `${produtos.length} produtos`;

        // Exibir até 40 produtos mais produzidos
        tbody.innerHTML = produtos.slice(0, 40).map(p => {
            const reduz = escapeHtml(p.reduz || "");
            const desc = escapeHtml(p.produto || "Sem descrição");
            const artigo = escapeHtml(p.artigo || "Sem artigo");
            const kg = formatNumber(p.kg_total, 0);
            const mt = formatNumber(p.mt_total, 0);
            const reprocessoVal = p.taxa_reprocesso;
            const prodVal = p.produtividade_kgh;

            let repClass = "badge-success";
            if (reprocessoVal > 15) repClass = "badge-danger";
            else if (reprocessoVal > 6) repClass = "badge-warning";

            return `
                <tr>
                    <td style="font-weight: 700; color: var(--accent-cyan);">${reduz}</td>
                    <td style="font-weight: 500; font-size: 0.85rem; max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${desc}">${desc}</td>
                    <td style="color: var(--text-secondary); font-size: 0.8rem;">${artigo}</td>
                    <td style="text-align: right; font-weight: 600;">${kg} kg</td>
                    <td style="text-align: right; color: var(--text-muted);">${mt} m</td>
                    <td style="text-align: right;">
                        <span class="badge ${repClass}" style="font-size: 0.72rem; font-weight: 700; padding: 2px 6px;">${formatPercent(reprocessoVal)}</span>
                    </td>
                    <td style="text-align: right; font-weight: 600; color: var(--accent-green);">${formatNumber(prodVal, 1)} kg/h</td>
                </tr>
            `;
        }).join("");
    }

    /**
     * Rastreabilidade e pesquisa histórica SQLite
     */
    async function pesquisarHistorico() {
        const obInput = document.getElementById("benef-hist-ob");
        const altInput = document.getElementById("benef-hist-alt");
        const inicioInput = document.getElementById("benef-hist-inicio");
        const fimInput = document.getElementById("benef-hist-fim");
        
        const ob = obInput ? obInput.value.trim() : "";
        const alternativo = altInput ? altInput.value.trim() : "";
        const dt_inicio = inicioInput ? inicioInput.value : "";
        const dt_fim = fimInput ? fimInput.value : "";
        
        if (!ob && !alternativo && !dt_inicio && !dt_fim) {
            if (showToast) showToast("Por favor, preencha pelo menos um filtro de pesquisa.", "info");
            return;
        }
        
        try {
            const queryParams = new URLSearchParams();
            if (ob) queryParams.append("ob", ob);
            if (alternativo) queryParams.append("alternativo", alternativo);
            if (dt_inicio) queryParams.append("dt_inicio", dt_inicio);
            if (dt_fim) queryParams.append("dt_fim", dt_fim);
            
            const data = await api(`/api/beneficiamento/historico?${queryParams.toString()}`);
            if (!data || !data.records) {
                renderHistoricoResultados([]);
                return;
            }
            
            renderHistoricoResultados(data.records, ob);
        } catch (error) {
            console.error("Erro ao buscar histórico no SQLite:", error);
            if (showToast) showToast("Erro ao buscar histórico de beneficiamento.", "danger");
        }
    }

    function renderHistoricoResultados(records, obPesquisada) {
        const resultsPanel = document.getElementById("benef-hist-results-panel");
        const emptyState = document.getElementById("benef-hist-empty-state");
        const countBadge = document.getElementById("benef-hist-count-badge");
        
        if (!records || records.length === 0) {
            if (resultsPanel) resultsPanel.style.display = "none";
            if (emptyState) {
                emptyState.style.display = "block";
                emptyState.innerHTML = `
                    <i data-lucide="database" style="margin: 0 auto var(--space-2) auto; color: rgba(148, 163, 184, 0.3); width: 36px; height: 36px; display: block;"></i>
                    <p style="font-size: 0.9rem;">Nenhum registro histórico encontrado para os filtros informados.</p>
                `;
            }
            if (typeof lucide !== "undefined") lucide.createIcons();
            return;
        }
        
        if (emptyState) emptyState.style.display = "none";
        if (resultsPanel) resultsPanel.style.display = "flex";
        
        const totalFases = records.length;
        let totalKg = 0;
        let totalMt = 0;
        let totalMinutos = 0;
        
        const obsUnicas = new Set();
        
        records.forEach(r => {
            totalKg += Number(r.QT_KG || 0);
            totalMt += Number(r.QT_MT || 0);
            totalMinutos += Number(r.MIN_REAL || 0);
            if (r.NUMERO_OB) {
                obsUnicas.add(r.NUMERO_OB);
            }
        });
        
        const kpiFases = document.getElementById("benef-hist-kpi-fases");
        const kpiKg = document.getElementById("benef-hist-kpi-kg");
        const kpiMt = document.getElementById("benef-hist-kpi-mt");
        const kpiTempo = document.getElementById("benef-hist-kpi-tempo");
        
        if (kpiFases) kpiFases.textContent = formatNumber(totalFases, 0);
        if (kpiKg) kpiKg.textContent = formatNumber(totalKg, 0);
        if (kpiMt) kpiMt.textContent = formatNumber(totalMt, 0);
        if (kpiTempo) kpiTempo.textContent = `${formatNumber(totalMinutos, 0)} min`;
        
        if (countBadge) countBadge.textContent = `${totalFases} registros`;
        
        const tbody = document.getElementById("benef-hist-tbody");
        if (tbody) {
            tbody.innerHTML = records.map(r => {
                const obNum = escapeHtml(r.NUMERO_OB || "");
                const fase = escapeHtml(r.CD_DS_FASE || "Fase Indefinida");
                const maq = escapeHtml(r.NOME_MAQUINA || "Sem máquina");
                const kg = formatNumber(r.QT_KG, 0);
                const min = formatNumber(r.MIN_REAL, 0);
                const oper = escapeHtml(r.OPERADOR_FINAL || r.NOME_OPERADOR_FINAL || "N/A");
                
                return `
                    <tr style="cursor: pointer;" onclick="document.getElementById('benef-hist-ob').value = '${obNum}'; document.getElementById('benef-hist-search-btn').click();">
                        <td style="font-weight: 700; color: var(--accent-cyan);">${obNum}</td>
                        <td style="font-weight: 500;">${fase}</td>
                        <td style="color: var(--text-muted); font-size: 0.8rem;">${maq}</td>
                        <td style="text-align: right; font-weight: 600;">${kg} kg</td>
                        <td style="text-align: right; color: var(--text-muted);">${min} min</td>
                        <td style="font-size: 0.8rem;">${oper}</td>
                    </tr>
                `;
            }).join("");
        }
        
        const timelineContainer = document.getElementById("benef-hist-timeline");
        if (timelineContainer) {
            const isSingleOb = obsUnicas.size === 1;
            
            if (isSingleOb) {
                const targetOb = Array.from(obsUnicas)[0];
                const obRecords = records.filter(r => r.NUMERO_OB === targetOb)
                                         .sort((a, b) => Number(a.SEQ || 0) - Number(b.SEQ || 0));
                                         
                timelineContainer.innerHTML = obRecords.map((r, index) => {
                    const faseNome = escapeHtml(r.CD_DS_FASE || "Processamento");
                    const maq = escapeHtml(r.NOME_MAQUINA || "Sem Máquina");
                    const oper = escapeHtml(r.OPERADOR_FINAL || "Indefinido");
                    const kg = formatNumber(r.QT_KG, 0);
                    const mt = formatNumber(r.QT_MT, 0);
                    const minReal = Number(r.MIN_REAL || 0);
                    const minPrev = Number(r.MIN_PREV || 0);
                    const desvio = Number(r.DESVIO_MIN || 0);
                    
                    let desvioClass = "badge-success";
                    let desvioLabel = "No prazo";
                    if (desvio > 15) {
                        desvioClass = "badge-danger";
                        desvioLabel = `+${formatNumber(desvio, 0)} min (atraso)`;
                    } else if (desvio < -15) {
                        desvioClass = "badge-success";
                        desvioLabel = `${formatNumber(desvio, 0)} min (adiantado)`;
                    }
                    
                    const dataFimStr = r.DATA_FIM ? formatToDateBr(r.DATA_FIM) : "Data não registrada";
                    
                    return `
                        <div style="position: relative; padding-left: 15px;">
                            <div style="position: absolute; left: -26px; top: 6px; width: 10px; height: 10px; border-radius: 50%; background: var(--accent-cyan); border: 2px solid var(--bg-surface); box-shadow: 0 0 6px var(--accent-cyan);"></div>
                            
                            <div style="display: flex; flex-direction: column; gap: 4px;">
                                <div style="display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); flex-wrap: wrap;">
                                    <h5 style="margin: 0; font-size: 0.85rem; font-weight: 700; color: var(--text-primary);">${faseNome}</h5>
                                    <span style="font-size: 0.7rem; color: var(--text-muted); font-weight: 500;">${dataFimStr}</span>
                                </div>
                                <div style="font-size: 0.76rem; color: var(--text-muted);">
                                    Máquina: <strong style="color: var(--text-secondary); font-weight: 500;">${maq}</strong> | Operador: <strong style="color: var(--text-secondary); font-weight: 500;">${oper}</strong>
                                </div>
                                <div style="display: flex; gap: var(--space-2); align-items: center; font-size: 0.74rem; margin-top: 2px; flex-wrap: wrap;">
                                    <span style="background: rgba(148,163,184,0.06); padding: 1px 5px; border-radius: 4px; font-weight: 600;"><i data-lucide="scale" style="width:10px; height:10px; display:inline; vertical-align:middle; margin-right:3px;"></i>${kg} kg</span>
                                    <span style="background: rgba(148,163,184,0.06); padding: 1px 5px; border-radius: 4px; font-weight: 600;"><i data-lucide="clock" style="width:10px; height:10px; display:inline; vertical-align:middle; margin-right:3px;"></i>Real: ${formatNumber(minReal, 0)} min (Prev: ${formatNumber(minPrev, 0)} min)</span>
                                    <span class="badge ${desvioClass}" style="font-size: 0.64rem; font-weight: 700; padding: 1px 4px;">${desvioLabel}</span>
                                </div>
                            </div>
                        </div>
                    `;
                }).join("");
            } else {
                timelineContainer.innerHTML = `
                    <div style="color: var(--text-muted); font-style: italic; padding: var(--space-3); text-align: center; border: 1px dashed rgba(148, 163, 184, 0.08); border-radius: var(--radius-sm); width: 100%; font-size: 0.8rem;">
                        <i data-lucide="info" style="width: 16px; height: 16px; margin: 0 auto 6px auto; display: block; color: rgba(148, 163, 184, 0.4);"></i>
                        Múltiplas OBs encontradas (${obsUnicas.size} OBs). Clique em uma linha de OB na tabela à direita para rastrear sua timeline de fases individual.
                    </div>
                `;
            }
        }
        
        if (typeof lucide !== "undefined") lucide.createIcons();
    }

    function setupHistorico(root) {
        if (root.dataset.historicoBound) return;
        root.dataset.historicoBound = "true";
        
        const searchBtn = document.getElementById("benef-hist-search-btn");
        const clearBtn = document.getElementById("benef-hist-clear-btn");
        const obInput = document.getElementById("benef-hist-ob");
        const altInput = document.getElementById("benef-hist-alt");
        
        searchBtn?.addEventListener("click", pesquisarHistorico);
        clearBtn?.addEventListener("click", () => {
            if (obInput) obInput.value = "";
            if (altInput) altInput.value = "";
            const inicioInput = document.getElementById("benef-hist-inicio");
            const fimInput = document.getElementById("benef-hist-fim");
            if (inicioInput) inicioInput.value = "";
            if (fimInput) fimInput.value = "";
            
            const resultsPanel = document.getElementById("benef-hist-results-panel");
            const emptyState = document.getElementById("benef-hist-empty-state");
            if (resultsPanel) resultsPanel.style.display = "none";
            if (emptyState) {
                emptyState.style.display = "block";
                emptyState.innerHTML = `
                    <i data-lucide="database" style="margin: 0 auto var(--space-2) auto; color: rgba(148, 163, 184, 0.3); width: 36px; height: 36px; display: block;"></i>
                    <p style="font-size: 0.9rem;">Nenhuma busca realizada. Informe uma OB ou filtros para carregar a rastreabilidade histórica.</p>
                `;
            }
            if (typeof lucide !== "undefined") lucide.createIcons();
        });
        
        const onEnter = (e) => {
            if (e.key === "Enter") {
                pesquisarHistorico();
            }
        };
        obInput?.addEventListener("keypress", onEnter);
        altInput?.addEventListener("keypress", onEnter);
    }

    /**
     * Ciclo de renderização principal do Cockpit
     */
    function render() {
        const root = document.getElementById("view-beneficiamento");
        if (!root) return;

        // Listeners e filtros
        setupFilters(root);
        setupHistorico(root);

        // Popular opções dinâmicas nos filtros
        populateFilterOptions();

        // Aplicar filtros e carregar tabelas/gráficos reativos
        applyInteractiveFilters();

        bindActionElements(root);
        if (typeof lucide !== "undefined") lucide.createIcons();
    }

    /**
     * Renderização em caso de falha de conexão
     */
    function renderUnavailable() {
        destroyCharts();
        setBannerState("warning", "O banco SQLite histórico de Beneficiamento não está respondendo.");
        setText("benef-selected-meta", "Verifique as conexões de persistência local.");
        
        const tbody = document.getElementById("benef-product-tbody");
        if (tbody) tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">Dados indisponíveis.</td></tr>';
        
        const podio = document.getElementById("benef-operadores-podio");
        if (podio) podio.innerHTML = '<div style="color: var(--text-muted); font-style: italic;">Dados de operadores indisponíveis.</div>';
        
        kpiIds.forEach(id => setText(id, "-"));
    }

    /**
     * Auxiliares utilitários
     */
    function getElement(id) {
        return document.getElementById(id);
    }

    function setText(id, value) {
        const el = getElement(id);
        if (!el) return;
        if (kpiIds.includes(id)) {
            animateCountUp(el, value);
        } else {
            el.textContent = value;
        }
    }

    function setBannerState(stateClass, message) {
        const banner = getElement("benef-banner");
        if (!banner) return;
        banner.className = `state-banner ${stateClass}`;
        banner.textContent = message;
        banner.style.display = "block";
    }

    function roundTo(val, decimals = 2) {
        if (val === undefined || val === null || isNaN(Number(val))) return 0;
        const factor = Math.pow(10, decimals);
        return Math.round(Number(val) * factor) / factor;
    }

    function animateCountUp(el, targetValue, duration = 800) {
        if (!el) return;
        if (el.dataset.countAnim) {
            cancelAnimationFrame(parseInt(el.dataset.countAnim, 10));
        }
        
        const rawString = String(targetValue || "").trim();
        if (rawString === "-" || rawString === "") {
            el.textContent = "-";
            return;
        }
        
        const hasPercent = rawString.includes("%");
        let cleanStr = rawString.replace(/[^\d,-]/g, "");
        cleanStr = cleanStr.replace(",", ".");
        const parsedVal = parseFloat(cleanStr);
        
        if (isNaN(parsedVal)) {
            el.textContent = targetValue;
            return;
        }
        
        const startVal = 0;
        const startTime = performance.now();
        
        const decimalParts = cleanStr.split(".");
        const decimalPlaces = decimalParts.length > 1 ? decimalParts[1].length : 0;
        
        function update(currentTime) {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            
            const easeProgress = progress * (2 - progress);
            const currentVal = startVal + (parsedVal - startVal) * easeProgress;
            
            let formatted = currentVal.toFixed(decimalPlaces).replace(".", ",");
            // Formatar milhares para inteiros grandes sem decimais
            if (decimalPlaces === 0 && currentVal > 999) {
                formatted = fmtInt.format(Math.round(currentVal));
            }
            
            el.textContent = hasPercent ? `${formatted}%` : formatted;
            
            if (progress < 1) {
                el.dataset.countAnim = requestAnimationFrame(update);
            } else {
                el.textContent = targetValue;
                delete el.dataset.countAnim;
            }
        }
        
        el.dataset.countAnim = requestAnimationFrame(update);
    }

    function destroyCharts() {
        for (const k in charts) {
            destroyChart(k);
        }
    }

    function destroyChart(key) {
        if (charts[key]) {
            try {
                charts[key].destroy();
            } catch (e) {
                // Silencioso
            }
            charts[key] = null;
        }
    }

    return {
        loadBeneficiamento,
        selectPeriod: () => {}, // Mantido por compatibilidade
    };
}
