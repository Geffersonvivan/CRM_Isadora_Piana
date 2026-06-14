// Mapa SVG de Santa Catarina com D3.js
class SCMap {
    constructor(containerId) {
        this.containerId = containerId;
        this.container = document.getElementById(containerId);
        this.svg = null;
        this.g = null;
        this._tip = null;
        this.currentLevel = 'state';
        this.currentSlug = null;
        this.onRegionClick = null;
        this.onCityClick = null;
        this.mapMode = 'regioes';
        this.width = 900;
        this.height = 550;
        this.heatmapEnabled = false;
        this.demandsEnabled = false;
        this.demandLayer = 'status';
        this.demandTipo = '';
        this._demandsCities = null;
        this._demandsFull = null;
        this._promessasData = null;
        this.itinerariesEnabled = false;
        this.strategicEnabled = false;
        this.plNetworkEnabled = false;
        this.zoneRankingEnabled = false;
        this.voteTransferEnabled = false;
        this.neighborDeputiesEnabled = false;
        this.elections2022Enabled = false;
        this.doacoesEnabled = false;
        this.visitUrgencyEnabled = false;
        this._visitUrgencyData = null;
        this.victoryEnabled = false;
        this._victoryData = null;
        this.heatLayer = 'penetracao';
        this._heatLayersData = null;
        this._heatMax = {};
        this.onCityAction = null;
        this._demandsData = null;
        this._itinerariesData = null;
        this._strategicData = null;
        this._plNetworkData = null;
        this._zoneRankingData = null;
        this._voteTransferData = null;
        this._neighborDeputiesData = null;
        this._elections2022Data = null;
        this._doacoesData = null;
        this._doacoesMaxRegion = 0;
        this._doacoesMaxCity = 0;
        this._stateGeojson = null;
        this._regionGeojson = null;
        this._itineraryColors = ['#3b82f6', '#f97316', '#8b5cf6', '#ec4899', '#14b8a6', '#f59e0b', '#06b6d4', '#ef4444'];
    }

    _urgencyColor(nivel) {
        return ['#d1d5db', '#86efac', '#eab308', '#f97316', '#dc2626'][nivel] || '#d1d5db';
    }

    // ── Vitória 2026: cor pela lacuna de votos disponíveis ──
    _victoryColor(nivel) {
        return ['#e2e8f0', '#bbf7d0', '#fde68a', '#fdba74', '#f87171'][nivel] || '#e2e8f0';
    }

    _quadLabel(q) {
        return { celeiro: '🛡️ Celeiro', fortaleza: '✅ Fortaleza', mina_ouro: '💰 Mina de ouro', marginal: '⚪ Marginal' }[q] || q;
    }

    async setVictory(enabled) {
        this.victoryEnabled = enabled;
        if (enabled) {
            this.heatmapEnabled = false;
            this.demandsEnabled = false;
            this.itinerariesEnabled = false;
            this.strategicEnabled = false;
            this.plNetworkEnabled = false;
            this.zoneRankingEnabled = false;
            this.voteTransferEnabled = false;
            this.neighborDeputiesEnabled = false;
            this.elections2022Enabled = false;
            this.doacoesEnabled = false;
            this.visitUrgencyEnabled = false;
            this._resetToNeutral();
            if (!this._victoryData) {
                try { this._victoryData = await API.maps.victory(); }
                catch (e) { this._victoryData = null; }
            }
        }
        if (this.currentLevel === 'state' && this._stateGeojson) {
            this._applyStateColors(true);
        } else if (this.currentLevel === 'region' && this._regionGeojson) {
            this._applyRegionColors(true);
        }
    }

    _victoryCityTipHtml(p) {
        const c = (this._victoryData?.cities || {})[p.slug];
        let html = `<div class="tooltip-title">${p.name}</div>`;
        if (!c) return html + '<div class="tooltip-row"><span style="color:#9ca3af">Sem dados</span></div>';
        html += `<div class="tooltip-row"><span class="tooltip-label">Classificação:</span> <span class="tooltip-value" style="font-weight:700">${this._quadLabel(c.quadrante)}</span></div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Votos 2022:</span> <span class="tooltip-value">${(c.votos_2022||0).toLocaleString('pt-BR')}</span></div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Potencial:</span> <span class="tooltip-value">${(c.meta||0).toLocaleString('pt-BR')}</span></div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Votos disponíveis:</span> <span class="tooltip-value" style="color:${this._victoryColor(c.nivel)};font-weight:800">+${(c.gap||0).toLocaleString('pt-BR')}</span></div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Penetração 2022:</span> <span class="tooltip-value">${c.penetracao}%</span></div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Estrutura CRM:</span> <span class="tooltip-value">${c.estrutura} contato(s)${c.vencidos ? ', ' + c.vencidos + ' vencidos' : ''}</span></div>`;
        if (c.alerta === 'orfa') html += `<div class="tooltip-row"><span class="tooltip-value" style="color:#dc2626;font-weight:700">🚨 Oportunidade órfã (sem estrutura)</span></div>`;
        if (c.alerta === 'esfriando') html += `<div class="tooltip-row"><span class="tooltip-value" style="color:#ea580c;font-weight:700">⚠️ Base esfriando</span></div>`;
        html += '<div class="tooltip-row"><span class="tooltip-label" style="color:#9ca3af">Clique para o painel de ação</span></div>';
        return html;
    }

    _victoryRegionTipHtml(p) {
        const r = (this._victoryData?.regions || {})[p.slug];
        let html = `<div class="tooltip-title">${p.name}</div>`;
        if (!r) return html + '<div class="tooltip-row"><span style="color:#9ca3af">Sem dados</span></div>';
        html += `<div class="tooltip-row"><span class="tooltip-label">Votos disponíveis:</span> <span class="tooltip-value" style="color:${this._victoryColor(r.nivel)};font-weight:800">+${(r.gap||0).toLocaleString('pt-BR')}</span></div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Votos 2022:</span> <span class="tooltip-value">${(r.votos_2022||0).toLocaleString('pt-BR')}</span></div>`;
        if (r.orfas) html += `<div class="tooltip-row"><span class="tooltip-label">Oportunidades órfãs:</span> <span class="tooltip-value" style="color:#dc2626;font-weight:700">${r.orfas}</span></div>`;
        if (r.pior) html += `<div class="tooltip-row"><span class="tooltip-label">Maior lacuna:</span> <span class="tooltip-value">${r.pior}</span></div>`;
        html += '<div class="tooltip-row"><span class="tooltip-label" style="color:#9ca3af">Clique para ver as cidades</span></div>';
        return html;
    }

    async setVisitUrgency(enabled) {
        // Não chama _resetToNeutral: convive com as linhas dos roteiros.
        this.visitUrgencyEnabled = enabled;
        if (enabled && !this._visitUrgencyData) {
            try {
                this._visitUrgencyData = await API.roteiros.urgency();
            } catch (e) {
                this._visitUrgencyData = null;
            }
        }
        if (this.currentLevel === 'state' && this._stateGeojson) {
            this._applyStateColors(true);
        } else if (this.currentLevel === 'region' && this._regionGeojson) {
            this._applyRegionColors(true);
        }
    }

    _urgencyCityTipHtml(p) {
        const c = (this._visitUrgencyData?.cities || {})[p.slug];
        let html = `<div class="tooltip-title">${p.name}</div>`;
        if (!c) return html + '<div class="tooltip-row"><span style="color:#9ca3af">Sem dados</span></div>';
        html += `<div class="tooltip-row"><span class="tooltip-label">Contatos vencidos:</span> <span class="tooltip-value" style="color:${this._urgencyColor(c.nivel)};font-weight:700">${c.vencidos}</span></div>`;
        if (c.nunca) html += `<div class="tooltip-row"><span class="tooltip-label">Nunca contatados:</span> <span class="tooltip-value">${c.nunca}</span></div>`;
        if (c.alta) html += `<div class="tooltip-row"><span class="tooltip-label">Prioridade alta:</span> <span class="tooltip-value" style="color:#dc2626;font-weight:700">${c.alta} ⭐</span></div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Última visita:</span> <span class="tooltip-value">${c.dias_visita === null ? 'nunca' : 'há ' + c.dias_visita + 'd'}</span></div>`;
        if (c.proximos) html += `<div class="tooltip-row"><span class="tooltip-label">Compromissos futuros:</span> <span class="tooltip-value">${c.proximos}</span></div>`;
        html += '<div class="tooltip-row"><span class="tooltip-label" style="color:#9ca3af">Clique para o painel de ação</span></div>';
        return html;
    }

    _urgencyRegionTipHtml(p) {
        const r = (this._visitUrgencyData?.regions || {})[p.slug];
        let html = `<div class="tooltip-title">${p.name}</div>`;
        if (!r) return html + '<div class="tooltip-row"><span style="color:#9ca3af">Sem dados</span></div>';
        html += `<div class="tooltip-row"><span class="tooltip-label">Contatos vencidos:</span> <span class="tooltip-value" style="color:${this._urgencyColor(r.nivel)};font-weight:700">${r.vencidos}</span></div>`;
        if (r.pior) html += `<div class="tooltip-row"><span class="tooltip-label">Cidade mais crítica:</span> <span class="tooltip-value">${r.pior}</span></div>`;
        html += '<div class="tooltip-row"><span class="tooltip-label" style="color:#9ca3af">Clique para ver as cidades</span></div>';
        return html;
    }

    // ── Construtor visual de roteiro (paradas numeradas no mapa) ──
    setBuilderStops(stops) {
        this.g.selectAll('.builder-marker,.builder-line').remove();
        if (!stops || !stops.length) return;
        const self = this;
        const pontos = [];
        for (const stop of stops) {
            const node = this.g.selectAll('path.city')
                .filter(d => d.properties.slug === stop.slug).node();
            if (!node) continue;
            const b = node.getBBox();
            pontos.push({ x: b.x + b.width / 2, y: b.y + b.height / 2, ordem: stop.ordem });
        }
        if (pontos.length > 1) {
            this.g.append('polyline')
                .attr('class', 'builder-line')
                .attr('points', pontos.map(pt => `${pt.x},${pt.y}`).join(' '))
                .attr('fill', 'none')
                .attr('stroke', '#002776')
                .attr('stroke-width', 2)
                .attr('stroke-dasharray', '6,4')
                .attr('opacity', 0.85);
        }
        for (const pt of pontos) {
            const grp = this.g.append('g').attr('class', 'builder-marker');
            grp.append('circle')
                .attr('cx', pt.x).attr('cy', pt.y).attr('r', 11)
                .attr('fill', '#002776').attr('stroke', '#fff').attr('stroke-width', 2.5);
            grp.append('text')
                .attr('x', pt.x).attr('y', pt.y)
                .attr('text-anchor', 'middle').attr('dy', '0.35em')
                .attr('font-size', '11px').attr('font-weight', '800')
                .attr('fill', '#fff').attr('pointer-events', 'none')
                .text(pt.ordem);
        }
    }

    _strategicColor(classification) {
        const map = {
            maquina_voto: '#15803d',
            aliado_ativar: '#f59e0b',
            construir: '#f97316',
            disputa: '#7c3aed',
            hostil: '#dc2626',
            neutro: '#9ca3af',
        };
        return map[classification] || '#d1d5db';
    }

    _plNetworkColor(score) {
        // Gradiente: cinza (0) → azul claro (30) → azul médio (60) → azul escuro (100)
        if (score === 0) return '#d1d5db';
        return d3.scaleLinear()
            .domain([1, 35, 60, 100])
            .range(['#bfdbfe', '#60a5fa', '#2563eb', '#1e3a8a'])
            .clamp(true)(score);
    }

    _plNetworkLevelColor(level) {
        const map = { forte: '#1e3a8a', moderada: '#2563eb', fraca: '#93c5fd', ausente: '#d1d5db' };
        return map[level] || '#d1d5db';
    }

    _plNetworkLevelLabel(level) {
        const map = { forte: 'Forte', moderada: 'Moderada', fraca: 'Fraca', ausente: 'Ausente' };
        return map[level] || level;
    }

    _transferLevelColor(level) {
        const map = { polo: '#15803d', acima: '#86efac', abaixo: '#fbbf24', zero: '#d1d5db' };
        return map[level] || '#d1d5db';
    }

    _transferLevelLabel(level) {
        const map = { polo: 'Polo (≥1.5x média)', acima: 'Acima da média', abaixo: 'Abaixo da média', zero: 'Sem votos' };
        return map[level] || level;
    }

    _transferPriorityColor(pri) {
        const map = { alta: '#dc2626', media: '#f97316', baixa: '#9ca3af' };
        return map[pri] || '#9ca3af';
    }

    _transferOppColor(opp_class) {
        const map = {
            palanque_conjunto: '#7c3aed',   // 2+ aliados fortes — palanque conjunto
            reduto_aliado: '#f59e0b',       // 1 aliado forte
            polo_ls: '#15803d',             // LS já forte
            sem_carona: '#d1d5db',
        };
        return map[opp_class] || '#d1d5db';
    }

    _transferOppLabel(opp_class) {
        const map = {
            palanque_conjunto: '🎤 Palanque conjunto',
            reduto_aliado: '🤝 Reduto de aliado',
            polo_ls: '🏠 Polo do LS',
            sem_carona: '⚪ Sem carona',
        };
        return map[opp_class] || opp_class;
    }

    _deputyClassColor(cls) {
        const map = {
            ponte_forte: '#f59e0b',
            base_conjunta: '#15803d',
            territorio_dep: '#2563eb',
            territorio_ls: '#86efac',
            sem_presenca: '#d1d5db',
        };
        return map[cls] || '#d1d5db';
    }

    _deputyClassLabel(cls) {
        const map = {
            ponte_forte: 'Ponte Forte',
            base_conjunta: 'Base Conjunta',
            territorio_dep: 'Território Dep.',
            territorio_ls: 'Território LS',
            sem_presenca: 'Sem Presença',
        };
        return map[cls] || cls;
    }

    _zonePerformanceColor(perf) {
        const map = { lider: '#15803d', competitivo: '#22c55e', medio: '#eab308', baixo: '#f97316', ausente: '#d1d5db' };
        return map[perf] || '#d1d5db';
    }

    _zonePerformanceLabel(perf) {
        const map = { lider: '1º Lugar', competitivo: 'Top 3', medio: 'Top 5', baixo: '6º+', ausente: 'Sem dados' };
        return map[perf] || perf;
    }

    _doacoesColor(valor, maxValor) {
        if (!valor || valor === 0) return '#e2e8f0';
        return d3.scaleLinear()
            .domain([0, maxValor * 0.25, maxValor * 0.5, maxValor])
            .range(['#dbeafe', '#60a5fa', '#2563eb', '#1e3a8a'])
            .clamp(true)(valor);
    }

    _demandColor(status) {
        const map = {
            overdue: '#ef4444',
            near_due: '#eab308',
            ok: '#22c55e',
            empty: '#d1d5db',
        };
        return map[status] || '#d1d5db';
    }

    // Escala de cores: vermelho (0%) -> amarelo (2%) -> verde (5%+)
    _heatScale() {
        return d3.scaleLinear()
            .domain([0, 2, 5])
            .range(['#ef4444', '#eab308', '#22c55e'])
            .clamp(true);
    }

    _penetracao(votes, voters) {
        if (!voters || voters === 0) return 0;
        return (votes / voters) * 100;
    }

    // ── Mapa de calor multi-camada ──
    static get HEAT_LAYERS() {
        return {
            penetracao:  { label: 'Penetração 2022', short: '%', type: 'good', dom: [0, 2, 5], fmt: v => v.toFixed(2) + '%' },
            densidade:   { label: 'Densidade de apoiadores', short: '/mil elei.', type: 'good', dom: [0, 1, 5], fmt: v => v.toFixed(2) },
            lacuna:      { label: 'Lacuna de votos (oportunidade)', short: 'votos', type: 'opportunity', dyn: true, fmt: v => '+' + Math.round(v).toLocaleString('pt-BR') },
            absoluto:    { label: 'Votos absolutos 2022 (massa)', short: 'votos', type: 'mass', dyn: true, fmt: v => Math.round(v).toLocaleString('pt-BR') },
            fronteira:   { label: 'Fronteira de expansão', short: 'score', type: 'frontier', dom: [0, 50, 100], fmt: v => Math.round(v) },
            esforco:     { label: 'Esforço de campo (visitas)', short: 'visitas', type: 'good', dyn: true, fmt: v => Math.round(v) },
            forca_politica: { label: 'Força política (prefeitos/vereadores)', short: 'pts', type: 'good', dyn: true, fmt: v => Math.round(v) },
            divergencia: { label: '2022 × Estrutura hoje', short: '', type: 'diverging', dom: [-100, 0, 100], fmt: v => (v > 0 ? '+' : '') + Math.round(v) },
        };
    }

    _heatColor(layer, value) {
        const cfg = SCMap.HEAT_LAYERS[layer] || SCMap.HEAT_LAYERS.penetracao;
        if (value === null || value === undefined) return '#e2e8f0';
        const max = cfg.dyn ? (this._heatMax[layer] || 1) : null;
        let scale;
        if (cfg.type === 'good') {
            const dom = cfg.dyn ? [0, max / 4, max] : cfg.dom;
            scale = d3.scaleLinear().domain(dom).range(['#ef4444', '#eab308', '#22c55e']).clamp(true);
        } else if (cfg.type === 'opportunity') {
            scale = d3.scaleLinear().domain([0, max / 2, max]).range(['#dcfce7', '#fdba74', '#dc2626']).clamp(true);
        } else if (cfg.type === 'mass') {
            scale = d3.scaleLinear().domain([0, max / 3, max]).range(['#eff6ff', '#60a5fa', '#1e3a8a']).clamp(true);
        } else if (cfg.type === 'frontier') {
            scale = d3.scaleLinear().domain([0, 40, 90]).range(['#f1f5f9', '#c4b5fd', '#6d28d9']).clamp(true);
        } else if (cfg.type === 'diverging') {
            scale = d3.scaleLinear().domain([-60, 0, 60]).range(['#dc2626', '#f1f5f9', '#2563eb']).clamp(true);
        }
        return scale(value);
    }

    _computeHeatMax() {
        this._heatMax = {};
        const cities = Object.values(this._heatLayersData?.cities || {});
        for (const layer of ['lacuna', 'absoluto', 'esforco', 'doacoes']) {
            this._heatMax[layer] = Math.max(1, ...cities.map(c => c[layer] || 0));
        }
    }

    async setHeatLayer(layer) {
        this.heatLayer = layer;
        if (this.currentLevel === 'state' && this._stateGeojson) this._applyStateColors(false);
        else if (this.currentLevel === 'region' && this._regionGeojson) this._applyRegionColors(false);
    }

    _heatVal(slug, level) {
        const src = level === 'region' ? this._heatLayersData?.regions : this._heatLayersData?.cities;
        const o = (src || {})[slug];
        return o ? o[this.heatLayer] : null;
    }

    _heatTipHtml(p, level) {
        const cfg = SCMap.HEAT_LAYERS[this.heatLayer];
        const src = level === 'region' ? this._heatLayersData?.regions : this._heatLayersData?.cities;
        const o = (src || {})[p.slug];
        let html = `<div class="tooltip-title">${p.name}</div>`;
        if (!o) return html + '<div class="tooltip-row"><span style="color:#9ca3af">Sem dados</span></div>';
        const val = o[this.heatLayer];
        html += `<div class="tooltip-row"><span class="tooltip-label">${cfg.label}:</span> <span class="tooltip-value" style="color:${this._heatColor(this.heatLayer, val)};font-weight:800">${cfg.fmt(val || 0)}</span></div>`;
        if (this.heatLayer === 'forca_politica') {
            const partes = [];
            if (o.pol_prefeito) partes.push(o.pol_prefeito + ' prefeito');
            if (o.pol_vereador) partes.push(o.pol_vereador + ' vereador(es)');
            if (o.pol_presidente) partes.push(o.pol_presidente + ' diretório');
            html += `<div class="tooltip-row"><span class="tooltip-label">Aliados:</span> <span class="tooltip-value">${partes.join(', ') || 'nenhum'}</span></div>`;
            if (o.votos_maquina) html += `<div class="tooltip-row"><span class="tooltip-label">Votos de máquina:</span> <span class="tooltip-value">${o.votos_maquina.toLocaleString('pt-BR')}</span></div>`;
        }
        if (o.penetracao !== undefined && this.heatLayer !== 'penetracao') html += `<div class="tooltip-row"><span class="tooltip-label">Penetração 2022:</span> <span class="tooltip-value">${o.penetracao}%</span></div>`;
        if (o.votos_2022 !== undefined) html += `<div class="tooltip-row"><span class="tooltip-label">Votos 2022:</span> <span class="tooltip-value">${(o.votos_2022||0).toLocaleString('pt-BR')}</span></div>`;
        if (o.apoiadores !== undefined) html += `<div class="tooltip-row"><span class="tooltip-label">Apoiadores:</span> <span class="tooltip-value">${o.apoiadores||0}</span></div>`;
        if (level !== 'region') html += '<div class="tooltip-row"><span class="tooltip-label" style="color:#9ca3af">Clique para o painel de ação</span></div>';
        return html;
    }

    init() {
        // Limpar SVG existente
        d3.select(`#${this.containerId}`).select('svg').remove();

        this.svg = d3.select(`#${this.containerId}`)
            .append('svg')
            .attr('viewBox', `0 0 ${this.width} ${this.height}`)
            .attr('preserveAspectRatio', 'xMidYMid meet')
            .style('width', '100%')
            .style('height', '100%')
            .style('background', '#f8fafc')
            .style('border-radius', '8px');

        this.g = this.svg.append('g');

        // Tooltip nativo (DOM direto, sem D3 selection)
        if (!this._tip) {
            const tip = document.createElement('div');
            tip.className = 'map-tooltip';
            document.body.appendChild(tip);
            this._tip = tip;
        }

        // Zoom com botões +/−
        this.zoom = d3.zoom()
            .scaleExtent([1, 8])
            .on('zoom', (event) => {
                this.g.attr('transform', event.transform);
            });
        this.svg.call(this.zoom);
        // Desabilitar zoom por scroll/duplo-clique (só botões)
        this.svg.on('wheel.zoom', null);
        this.svg.on('dblclick.zoom', null);

        // Criar botões de zoom
        this._createZoomControls();

        return this;
    }

    _createZoomControls() {
        const container = document.getElementById(this.containerId);
        // Remover controles anteriores se existirem
        const old = container.querySelector('.zoom-controls');
        if (old) old.remove();

        const div = document.createElement('div');
        div.className = 'zoom-controls';
        div.style.cssText = 'position:absolute;bottom:14px;right:14px;display:flex;flex-direction:column;gap:4px;z-index:400;';

        const btnStyle = 'width:34px;height:34px;border:1px solid #cbd5e1;border-radius:6px;background:rgba(255,255,255,.95);color:#334155;font-size:1.2rem;font-weight:700;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 6px rgba(0,0,0,.1);transition:background .15s;';

        const btnPlus = document.createElement('button');
        btnPlus.innerHTML = '+';
        btnPlus.title = 'Aproximar';
        btnPlus.style.cssText = btnStyle;
        btnPlus.onmouseenter = () => btnPlus.style.background = '#e2e8f0';
        btnPlus.onmouseleave = () => btnPlus.style.background = 'rgba(255,255,255,.95)';
        btnPlus.onclick = () => this.svg.transition().duration(300).call(this.zoom.scaleBy, 1.5);

        const btnMinus = document.createElement('button');
        btnMinus.innerHTML = '−';
        btnMinus.title = 'Afastar';
        btnMinus.style.cssText = btnStyle;
        btnMinus.onmouseenter = () => btnMinus.style.background = '#e2e8f0';
        btnMinus.onmouseleave = () => btnMinus.style.background = 'rgba(255,255,255,.95)';
        btnMinus.onclick = () => this.svg.transition().duration(300).call(this.zoom.scaleBy, 1 / 1.5);

        const btnReset = document.createElement('button');
        btnReset.innerHTML = '⟲';
        btnReset.title = 'Resetar zoom';
        btnReset.style.cssText = btnStyle + 'font-size:1rem;margin-top:2px;';
        btnReset.onmouseenter = () => btnReset.style.background = '#e2e8f0';
        btnReset.onmouseleave = () => btnReset.style.background = 'rgba(255,255,255,.95)';
        btnReset.onclick = () => this.svg.transition().duration(400).call(this.zoom.transform, d3.zoomIdentity);

        div.appendChild(btnPlus);
        div.appendChild(btnMinus);
        div.appendChild(btnReset);
        container.appendChild(div);
    }

    _showTip(html, x, y) {
        const t = this._tip;
        t.innerHTML = html;
        t.style.transform = `translate3d(${x + 14}px, ${y - 14}px, 0)`;
        t.style.opacity = '1';
    }

    _moveTip(x, y) {
        this._tip.style.transform = `translate3d(${x + 14}px, ${y - 14}px, 0)`;
    }

    _hideTip() {
        this._tip.style.opacity = '0';
    }

    _stateTipHtml(p) {
        if (this.itinerariesEnabled) {
            // No modo roteiros, mostrar apenas nome da regiao com info minima
            return `<div class="tooltip-title">${p.name}</div><div class="tooltip-row"><span class="tooltip-label" style="color:#9ca3af">Clique para ver cidades</span></div>`;
        }
        let html = `<div class="tooltip-title">${p.name}</div><div class="tooltip-row"><span class="tooltip-label">Região:</span> <span class="tooltip-value">${p.full_name || p.name}</span></div><div class="tooltip-row"><span class="tooltip-label">População:</span> <span class="tooltip-value">${fmt.number(p.population)}</span></div><div class="tooltip-row"><span class="tooltip-label">Apoiadores:</span> <span class="tooltip-value">${p.total_apoiadores || 0}</span></div><div class="tooltip-row"><span class="tooltip-label">Votos LS 2022:</span> <span class="tooltip-value">${fmt.number(p.total_votes_2022)}</span></div>`;
        if (this.heatmapEnabled) {
            const pct = this._penetracao(p.total_votes_2022, p.registered_voters);
            html += `<div class="tooltip-row"><span class="tooltip-label">Penetração:</span> <span class="tooltip-value" style="color:${this._heatScale()(pct)};font-weight:700">${pct.toFixed(2)}%</span></div>`;
        }
        if (this.demandsEnabled) {
            const dd = (this._demandsData || {})[p.slug];
            if (dd) {
                html += `<div class="tooltip-row"><span class="tooltip-label">Demandas:</span> <span class="tooltip-value">${dd.active} ativas</span></div>`;
                if (dd.overdue > 0) html += `<div class="tooltip-row"><span class="tooltip-label">Em atraso:</span> <span class="tooltip-value" style="color:#ef4444;font-weight:700">${dd.overdue}</span></div>`;
            } else {
                html += `<div class="tooltip-row"><span class="tooltip-label">Demandas:</span> <span class="tooltip-value" style="color:#9ca3af">Nenhuma</span></div>`;
            }
        }
        return html;
    }

    _stopTipHtml(stop, itinerary) {
        let html = `<div class="tooltip-title">${stop.city_name}</div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Roteiro:</span> <span class="tooltip-value">${itinerary.name}</span></div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Data:</span> <span class="tooltip-value">${stop.date.split('-').reverse().join('/')}</span></div>`;
        if (stop.time) html += `<div class="tooltip-row"><span class="tooltip-label">Horário:</span> <span class="tooltip-value">${stop.time.substring(0, 5)}</span></div>`;
        if (stop.task_title) html += `<div class="tooltip-row"><span class="tooltip-label">Demanda:</span> <span class="tooltip-value">${stop.task_title}</span></div>`;
        if (stop.is_overnight) html += `<div class="tooltip-row"><span class="tooltip-value" style="color:#7c3aed;font-weight:600">Pernoite</span></div>`;
        return html;
    }

    _cityTipHtml(p) {
        let html = `<div class="tooltip-title">${p.name}</div><div class="tooltip-row"><span class="tooltip-label">População:</span> <span class="tooltip-value">${fmt.number(p.population)}</span></div><div class="tooltip-row"><span class="tooltip-label">Votos LS 2022:</span> <span class="tooltip-value">${fmt.number(p.votes_2022)}</span></div><div class="tooltip-row"><span class="tooltip-label">Apoiadores:</span> <span class="tooltip-value">${p.total_apoiadores || 0}</span></div>`;
        if (this.heatmapEnabled) {
            const pct = this._penetracao(p.votes_2022, p.registered_voters);
            html += `<div class="tooltip-row"><span class="tooltip-label">Penetração:</span> <span class="tooltip-value" style="color:${this._heatScale()(pct)};font-weight:700">${pct.toFixed(2)}%</span></div>`;
        }
        return html;
    }

    // ── Perfil Ideológico: índice socioeconômico × eleitoral ──────────
    async setPerfilIdeologico(enabled) {
        this.perfilIdeologicoEnabled = enabled;
        if (enabled) {
            this.heatmapEnabled = false;
            this.demandsEnabled = false;
            this.itinerariesEnabled = false;
            this.strategicEnabled = false;
            this.plNetworkEnabled = false;
            this.zoneRankingEnabled = false;
            this.voteTransferEnabled = false;
            this.neighborDeputiesEnabled = false;
            this.elections2022Enabled = false;
            this.doacoesEnabled = false;
            this.concorrenciaEnabled = false;
            this._resetToNeutral();
            this.g.selectAll('path.region').style('display', 'none');
            this.g.selectAll('text').style('display', 'none');

            if (!this._allCitiesGeojson) {
                try { this._allCitiesGeojson = await API.maps.stateCities(); }
                catch (e) { this._allCitiesGeojson = null; }
            }
        }
        if (!enabled) {
            this._perfilScores = null;
            this._perfilRawData = null;
            this._perfilActiveEl = [];
            this._perfilActiveSo = [];
            this._resetToNeutral();
        }
        if (enabled && this._allCitiesGeojson) {
            this._renderPerfilIdeologicoCityMap();
        }
    }

    _perfilColor(score) {
        // 0 = esquerda (vermelho), 0.5 = centro (amarelo), 1 = direita (azul)
        return d3.scaleLinear()
            .domain([0, 0.25, 0.5, 0.75, 1])
            .range(['#E53935', '#FF7043', '#FFD54F', '#66BB6A', '#1565C0'])
            .clamp(true)(score);
    }

    _oppColor(score) {
        // Camada de oportunidade (gap): cinza claro → amarelo → laranja → vermelho.
        // 0 = baixa prioridade (já forte / pouco eleitorado), 1 = alvo prioritário.
        return d3.scaleLinear()
            .domain([0, 0.33, 0.66, 1])
            .range(['#f1f5f9', '#fde68a', '#fb923c', '#b91c1c'])
            .clamp(true)(score);
    }

    _perfilTipHtml(d) {
        const slug = d.properties.slug;
        const c = this._perfilRawData?.[slug];
        let html = `<div class="tooltip-title">${d.properties.name}</div>`;
        if (!c) {
            html += `<div class="tooltip-row"><span style="color:#9ca3af">Sem dados</span></div>`;
            return html;
        }

        // Score normalizado dinâmico com barra visual
        const sn = this._perfilScores?.[slug];
        if (sn !== undefined) {
            const scoreLabel = sn <= 0.20 ? 'Menos conservador' : sn <= 0.40 ? 'Moderado' : sn <= 0.60 ? 'Conservador' : sn <= 0.80 ? 'Muito conservador' : 'Ultra conservador';
            const scoreColor = this._perfilColor(sn);
            const pct = (sn * 100).toFixed(0);
            html += `<div class="tooltip-row" style="margin-bottom:4px"><span class="tooltip-label">Perfil</span> <span class="tooltip-value" style="color:${scoreColor};font-weight:bold">${scoreLabel} (${pct})</span></div>`;
            html += `<div style="height:6px;background:#e2e8f0;border-radius:3px;margin-bottom:6px;overflow:hidden"><div style="width:${pct}%;height:100%;background:${scoreColor};border-radius:3px;transition:width .3s"></div></div>`;
        }

        // Oportunidade (modo gap): conservadorismo × eleitorado × déficit de presença
        const on = this._perfilOpp?.[slug];
        if (this._perfilOppActive && on !== undefined) {
            const oppPct = (on * 100).toFixed(0);
            const oppColor = this._oppColor(on);
            const oppLabel = on >= 0.66 ? 'Alvo prioritário' : on >= 0.33 ? 'Boa oportunidade' : on >= 0.10 ? 'Moderada' : 'Baixa / já forte';
            html += `<div class="tooltip-row" style="margin-bottom:4px"><span class="tooltip-label">Oportunidade</span> <span class="tooltip-value" style="color:${oppColor};font-weight:bold">${oppLabel} (${oppPct})</span></div>`;
            html += `<div style="height:6px;background:#e2e8f0;border-radius:3px;margin-bottom:4px;overflow:hidden"><div style="width:${oppPct}%;height:100%;background:${oppColor};border-radius:3px;transition:width .3s"></div></div>`;
            const penTxt = c.penetration !== undefined ? `${c.penetration.toFixed(1)}%` : '—';
            html += `<div class="tooltip-row" style="margin-bottom:6px;font-size:.62rem;color:#94a3b8"><span class="tooltip-label" style="color:#94a3b8">Penetração 2022</span> <span class="tooltip-value" style="color:#94a3b8">${penTxt} · ${(c.apoiadores || 0).toLocaleString('pt-BR')} apoiadores</span></div>`;
        }

        const LABELS = {
            governador_1t: 'Gov. 1T', governador_2t: 'Gov. 2T', senador_1t: 'Senador',
            pib: 'PIB p/c', renda: 'Renda p/c', bf: 'Bolsa Fam.', meis: 'MEIs',
            pop_urbana_pct: '% Urbana', idosos_pct: '% Idosos', jovens_pct: '% Jovens',
            escolaridade: 'Alfabetiz.',
        };

        // Dados eleitorais selecionados
        const elKeys = this._perfilActiveEl || [];
        if (elKeys.length) {
            html += `<div style="font-size:.6rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin:4px 0 2px">Eleitoral</div>`;
            for (const key of elKeys) {
                if (c[key] === undefined) continue;
                const dir = c[key + '_dir'] || 0;
                const esq = c[key + '_esq'] || 0;
                const total = c[key + '_total'] || 1;
                const dirPct = ((dir / total) * 100).toFixed(1);
                html += `<div class="tooltip-row"><span class="tooltip-label">${LABELS[key] || key}</span> <span class="tooltip-value"><span style="color:#1565C0">${dirPct}%D</span> <span style="color:#9ca3af">(${dir.toLocaleString('pt-BR')}×${esq.toLocaleString('pt-BR')})</span></span></div>`;
            }
        }

        // Dados socioeconômicos selecionados
        const soKeys = this._perfilActiveSo || [];
        if (soKeys.length) {
            html += `<div style="font-size:.6rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin:4px 0 2px">Socioeconômico</div>`;
            for (const key of soKeys) {
                if (c[key] === undefined) continue;
                let val = '';
                if (key === 'pib') val = 'R$ ' + (c.pib_raw || 0).toLocaleString('pt-BR', {maximumFractionDigits: 0});
                else if (key === 'renda') val = 'R$ ' + (c.renda_raw || 0).toLocaleString('pt-BR', {maximumFractionDigits: 0});
                else if (key === 'bf') val = (c.bf_raw || 0).toLocaleString('pt-BR') + ' fam.';
                else if (key === 'meis') val = (c.meis_raw || 0).toLocaleString('pt-BR');
                else if (key === 'pop_urbana_pct') val = (c.pop_urbana_pct_raw || 0).toFixed(1) + '%';
                else if (key === 'idosos_pct') val = (c.idosos_pct_raw || 0).toFixed(1) + '%';
                else if (key === 'jovens_pct') val = (c.jovens_pct_raw || 0).toFixed(1) + '%';
                else if (key === 'escolaridade') val = (c.escolaridade_raw || 0).toFixed(1) + '% alfabetiz.';
                else val = (c[key] * 100).toFixed(1) + '%';
                html += `<div class="tooltip-row"><span class="tooltip-label">${LABELS[key] || key}</span> <span class="tooltip-value">${val}</span></div>`;
            }
        }

        // Dados CRM
        if (c.apoiadores !== undefined || c.demandas !== undefined) {
            html += `<div style="font-size:.6rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin:4px 0 2px">CRM</div>`;
            if (c.apoiadores !== undefined) html += `<div class="tooltip-row"><span class="tooltip-label">Apoiadores</span> <span class="tooltip-value">${(c.apoiadores || 0).toLocaleString('pt-BR')}</span></div>`;
            if (c.demandas !== undefined) html += `<div class="tooltip-row"><span class="tooltip-label">Demandas</span> <span class="tooltip-value">${(c.demandas || 0).toLocaleString('pt-BR')}</span></div>`;
        }

        if (c.pop) {
            html += `<div class="tooltip-row" style="margin-top:3px;border-top:1px solid #f1f5f9;padding-top:3px"><span class="tooltip-label" style="color:#9ca3af">Pop.</span> <span class="tooltip-value" style="color:#9ca3af">${c.pop.toLocaleString('pt-BR')}</span></div>`;
        }

        return html;
    }

    _renderPerfilIdeologicoCityMap() {
        if (!this._allCitiesGeojson) return;
        const geojson = this._allCitiesGeojson;
        const self = this;

        if (!this._concProjection || this._concW !== this.width || this._concH !== this.height) {
            this._concProjection = d3.geoMercator()
                .fitExtent([[20, 10], [this.width - 20, this.height - 10]], geojson);
            this._concPath = d3.geoPath().projection(this._concProjection);
            this._concW = this.width;
            this._concH = this.height;
        }
        const path = this._concPath;

        const paths = this.g.selectAll('path.perfil-city')
            .data(geojson.features, d => d.properties.slug);

        const enter = paths.enter()
            .append('path')
            .attr('class', 'perfil-city')
            .attr('d', path)
            .attr('fill-opacity', 0.88)
            .attr('stroke', '#94a3b8')
            .attr('stroke-width', 0.6)
            .attr('stroke-linejoin', 'round')
            .attr('cursor', 'pointer')
            .on('mouseenter', (event, d) => {
                self.g.selectAll('path.perfil-city').attr('stroke', '#94a3b8').attr('stroke-width', 0.6);
                d3.select(event.currentTarget).attr('stroke', '#475569').attr('stroke-width', 1.4);
                self._showTip(self._perfilTipHtml(d), event.pageX, event.pageY);
            })
            .on('mousemove', (event) => { self._moveTip(event.pageX, event.pageY); })
            .on('mouseleave', () => {
                self.g.selectAll('path.perfil-city').attr('stroke', '#94a3b8').attr('stroke-width', 0.6);
                self._hideTip();
            })
            .on('click', (event, d) => {
                self._hideTip();
                if (typeof addToCompare === 'function') {
                    addToCompare(d.properties.slug);
                }
            });

        // Começa cinza — a coloração é controlada por recalcPerfilMap() no index.html
        enter.merge(paths)
            .attr('fill', '#e2e8f0');
    }

    // ── Concorrência (MVP): área de atuação de um candidato ──────────
    async setConcorrencia(enabled) {
        this.concorrenciaEnabled = enabled;
        if (enabled) {
            this.heatmapEnabled = false;
            this.demandsEnabled = false;
            this.itinerariesEnabled = false;
            this.strategicEnabled = false;
            this.plNetworkEnabled = false;
            this.zoneRankingEnabled = false;
            this.voteTransferEnabled = false;
            this.perfilIdeologicoEnabled = false;
            this.neighborDeputiesEnabled = false;
            this.elections2022Enabled = false;
            this.doacoesEnabled = false;
            this._resetToNeutral();
            // Hide base map immediately, then load geojson
            this.g.selectAll('path.region').style('display', 'none');
            this.g.selectAll('text').style('display', 'none');
            if (!this._allCitiesGeojson) {
                try { this._allCitiesGeojson = await API.maps.stateCities(); }
                catch (e) { this._allCitiesGeojson = null; }
            }
        }
        if (!enabled) {
            this._concProjection = null;
            this._concPath = null;
            this._concCandidates = [];
            this._resetToNeutral();
        }
        if (enabled && this._allCitiesGeojson) {
            this._renderConcorrenciaCityMap();
        }
    }

    // Paletas de cores por candidato (até 8 candidatos simultâneos)
    static CONC_PALETTES = [
        { dark: '#14532d', shades: ['#14532d','#16a34a','#22c55e','#86efac','#dcfce7'] },  // verde
        { dark: '#1e3a8a', shades: ['#1e3a8a','#2563eb','#3b82f6','#93c5fd','#dbeafe'] },  // azul
        { dark: '#991b1b', shades: ['#991b1b','#dc2626','#ef4444','#fca5a5','#fee2e2'] },  // vermelho
        { dark: '#92400e', shades: ['#92400e','#d97706','#f59e0b','#fcd34d','#fef3c7'] },  // amarelo/laranja
        { dark: '#581c87', shades: ['#581c87','#7c3aed','#a78bfa','#c4b5fd','#ede9fe'] },  // roxo
        { dark: '#155e75', shades: ['#155e75','#0891b2','#22d3ee','#67e8f9','#cffafe'] },  // ciano
        { dark: '#9f1239', shades: ['#9f1239','#e11d48','#fb7185','#fda4af','#ffe4e6'] },  // rosa
        { dark: '#3f6212', shades: ['#3f6212','#65a30d','#a3e635','#d9f99d','#f7fee7'] },  // lima
    ];

    _initConcorrenciaState() {
        if (!this._concCandidates) {
            this._concCandidates = [];   // [{key, data, paletteIdx}]
        }
    }

    async addConcorrenciaCandidate(candKey) {
        this._initConcorrenciaState();
        if (this._concCandidates.find(c => c.key === candKey)) return;
        if (this._concCandidates.length >= 8) return;

        if (!this._allCitiesGeojson) {
            try { this._allCitiesGeojson = await API.maps.stateCities(); }
            catch (e) { this._allCitiesGeojson = null; }
        }

        let data;
        try { data = await API.competicao.cidades(candKey); }
        catch (e) { return; }

        const usedIdx = new Set(this._concCandidates.map(c => c.paletteIdx));
        let idx = 0;
        while (usedIdx.has(idx)) idx++;

        this._concCandidates.push({ key: candKey, data, paletteIdx: idx });
        if (this._allCitiesGeojson) this._renderConcorrenciaCityMap();
    }

    removeConcorrenciaCandidate(candKey) {
        this._initConcorrenciaState();
        this._concCandidates = this._concCandidates.filter(c => c.key !== candKey);
        if (this._allCitiesGeojson) this._renderConcorrenciaCityMap();
    }

    clearConcorrenciaCandidates() {
        this._concCandidates = [];
        if (this._allCitiesGeojson) this._renderConcorrenciaCityMap();
    }

    _concorrenciaColorMulti(slug) {
        const candidates = this._concCandidates || [];
        if (!candidates.length) return '#e2e8f0';

        // Find the dominant candidate (most votes) in this city
        let bestVotos = 0, bestIdx = -1;
        for (const cand of candidates) {
            const c = (cand.data.cidades || {})[slug];
            if (c && c.votos > bestVotos) {
                bestVotos = c.votos;
                bestIdx = cand.paletteIdx;
            }
        }
        if (bestIdx < 0) return '#e2e8f0';

        // Use the dominant candidate's palette, intensity based on their own max
        const domCand = candidates.find(c => c.paletteIdx === bestIdx);
        const maxV = domCand.data.max_votos || 1;
        const t = bestVotos / maxV;
        const shades = SCMap.CONC_PALETTES[bestIdx].shades;
        if (t >= 0.66) return shades[0];
        if (t >= 0.40) return shades[1];
        if (t >= 0.20) return shades[2];
        if (t >= 0.07) return shades[3];
        return shades[4];
    }

    _concorrenciaTipHtml(d) {
        const candidates = this._concCandidates || [];
        const slug = d.properties.slug;
        let html = `<div class="tooltip-title">${d.properties.name}</div>`;
        if (!candidates.length) return html;

        for (const cand of candidates) {
            const palette = SCMap.CONC_PALETTES[cand.paletteIdx];
            const c = (cand.data.cidades || {})[slug];
            const nome = cand.data.candidato;
            html += `<div class="tooltip-row"><span class="tooltip-label"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${palette.dark};margin-right:4px"></span>${nome}</span>`;
            if (c && c.votos > 0) {
                html += ` <span class="tooltip-value" style="color:${palette.dark};font-weight:bold">${c.votos.toLocaleString('pt-BR')}</span> <span style="color:#94a3b8;font-size:.75rem">(${c.pct}%)</span>`;
            } else {
                html += ` <span style="color:#9ca3af;font-size:.78rem">—</span>`;
            }
            html += `</div>`;
        }
        return html;
    }

    _renderConcorrenciaCityMap() {
        if (!this._allCitiesGeojson) return;

        const geojson = this._allCitiesGeojson;
        const self = this;

        // Cache projection and path generator — only recalculate on resize
        if (!this._concProjection || this._concW !== this.width || this._concH !== this.height) {
            this._concProjection = d3.geoMercator()
                .fitExtent([[20, 10], [this.width - 20, this.height - 10]], geojson);
            this._concPath = d3.geoPath().projection(this._concProjection);
            this._concW = this.width;
            this._concH = this.height;
        }
        const path = this._concPath;

        // D3 join pattern: reuse existing paths instead of destroy+recreate
        const paths = this.g.selectAll('path.concorrencia-city')
            .data(geojson.features, d => d.properties.slug);

        // Enter: first render only
        const enter = paths.enter()
            .append('path')
            .attr('class', 'concorrencia-city')
            .attr('d', path)
            .attr('fill-opacity', 0.88)
            .attr('stroke', '#94a3b8')
            .attr('stroke-width', 0.6)
            .attr('stroke-linejoin', 'round')
            .attr('cursor', 'pointer')
            .on('mouseenter', (event, d) => {
                self.g.selectAll('path.concorrencia-city').attr('stroke', '#94a3b8').attr('stroke-width', 0.6);
                d3.select(event.currentTarget).attr('stroke', '#475569').attr('stroke-width', 1.4);
                self._showTip(self._concorrenciaTipHtml(d), event.pageX, event.pageY);
            })
            .on('mousemove', (event) => { self._moveTip(event.pageX, event.pageY); })
            .on('mouseleave', () => {
                self.g.selectAll('path.concorrencia-city').attr('stroke', '#94a3b8').attr('stroke-width', 0.6);
                self._hideTip();
            })
            .on('click', (event, d) => {
                self._hideTip();
                if (self.onCityAction) self.onCityAction(d.properties.slug);
                else window.location.href = `/mapa/cidade/${d.properties.slug}/?mapa=${self.mapMode}`;
            });

        // Merge enter + update, animate color transition
        enter.merge(paths)
            .transition().duration(400)
            .attr('fill', d => self._concorrenciaColorMulti(d.properties.slug));
    }

    _resetToNeutral() {
        // Restore base map if hidden by transfer/concorrencia modes
        this.g.selectAll('path.region').style('display', null).attr('fill', '#e2e8f0').attr('fill-opacity', 0.85);
        this.g.selectAll('path.city').style('display', null).attr('fill', '#e2e8f0').attr('fill-opacity', 0.85);
        this.g.selectAll('text').style('display', null);
        // Remove overlay elements from special modes
        this.g.selectAll('.itinerary-line,.itinerary-marker,.transfer-arrow,.transfer-marker,.transfer-city,.concorrencia-city,.perfil-city,.builder-marker,.builder-line').remove();
    }

    async setHeatmap(enabled) {
        this.heatmapEnabled = enabled;
        if (enabled) {
            this.demandsEnabled = false;
            this.itinerariesEnabled = false;
            this.strategicEnabled = false;
            this.plNetworkEnabled = false;
            this.zoneRankingEnabled = false;
            this.voteTransferEnabled = false;
            this.neighborDeputiesEnabled = false;
            this.elections2022Enabled = false;
            this.doacoesEnabled = false;
            this.victoryEnabled = false;
            this.visitUrgencyEnabled = false;
            if (!this._heatLayersData) {
                try { this._heatLayersData = await API.maps.heatLayers(); this._computeHeatMax(); }
                catch (e) { this._heatLayersData = null; }
            }
        }
        this._resetToNeutral();
        if (this.currentLevel === 'state' && this._stateGeojson) {
            this._applyStateColors(true);
        } else if (this.currentLevel === 'region' && this._regionGeojson) {
            this._applyRegionColors(true);
        }
    }

    async setStrategic(enabled) {
        this.strategicEnabled = enabled;
        if (enabled) {
            this.heatmapEnabled = false;
            this.demandsEnabled = false;
            this.itinerariesEnabled = false;
            this.plNetworkEnabled = false;
            this.zoneRankingEnabled = false;
            this.voteTransferEnabled = false;
            this.neighborDeputiesEnabled = false;
            this.elections2022Enabled = false;
            this._resetToNeutral();
            try {
                this._strategicData = await API.dashboard.strategic();
            } catch (e) {
                this._strategicData = null;
            }
        }
        if (this.currentLevel === 'state' && this._stateGeojson) {
            this._applyStateColors(true);
        } else if (this.currentLevel === 'region' && this._regionGeojson) {
            this._applyRegionColors(true);
        }
    }

    async setPLNetwork(enabled) {
        this.plNetworkEnabled = enabled;
        if (enabled) {
            this.heatmapEnabled = false;
            this.demandsEnabled = false;
            this.itinerariesEnabled = false;
            this.strategicEnabled = false;
            this.zoneRankingEnabled = false;
            this.voteTransferEnabled = false;
            this.neighborDeputiesEnabled = false;
            this.elections2022Enabled = false;
            this._resetToNeutral();
            try {
                this._plNetworkData = await API.dashboard.plNetwork();
            } catch (e) {
                this._plNetworkData = null;
            }
        }
        if (this.currentLevel === 'state' && this._stateGeojson) {
            this._applyStateColors(true);
        } else if (this.currentLevel === 'region' && this._regionGeojson) {
            this._applyRegionColors(true);
        }
    }

    async setZoneRanking(enabled) {
        this.zoneRankingEnabled = enabled;
        if (enabled) {
            this.heatmapEnabled = false;
            this.demandsEnabled = false;
            this.itinerariesEnabled = false;
            this.strategicEnabled = false;
            this.plNetworkEnabled = false;
            this.voteTransferEnabled = false;
            this.neighborDeputiesEnabled = false;
            this.elections2022Enabled = false;
            this._resetToNeutral();
            try {
                this._zoneRankingData = await API.dashboard.zoneRanking();
            } catch (e) {
                this._zoneRankingData = null;
            }
        }
        if (this.currentLevel === 'state' && this._stateGeojson) {
            this._applyStateColors(true);
        } else if (this.currentLevel === 'region' && this._regionGeojson) {
            this._applyRegionColors(true);
        }
    }

    async setNeighborDeputies(enabled) {
        this.neighborDeputiesEnabled = enabled;
        if (enabled) {
            this.heatmapEnabled = false;
            this.demandsEnabled = false;
            this.itinerariesEnabled = false;
            this.strategicEnabled = false;
            this.plNetworkEnabled = false;
            this.zoneRankingEnabled = false;
            this.voteTransferEnabled = false;
            this.elections2022Enabled = false;
            this._resetToNeutral();
            try {
                this._neighborDeputiesData = await API.dashboard.neighborDeputies();
            } catch (e) {
                this._neighborDeputiesData = null;
            }
        }
        if (this.currentLevel === 'state' && this._stateGeojson) {
            this._applyStateColors(true);
        } else if (this.currentLevel === 'region' && this._regionGeojson) {
            this._applyRegionColors(true);
        }
    }

    async setElections2022(enabled) {
        this.elections2022Enabled = enabled;
        if (enabled) {
            this.heatmapEnabled = false;
            this.demandsEnabled = false;
            this.itinerariesEnabled = false;
            this.strategicEnabled = false;
            this.plNetworkEnabled = false;
            this.zoneRankingEnabled = false;
            this.voteTransferEnabled = false;
            this.neighborDeputiesEnabled = false;
            this._resetToNeutral();
            try {
                this._elections2022Data = await API.dashboard.elections2022();
            } catch (e) {
                this._elections2022Data = null;
            }
        }
        if (this.currentLevel === 'state' && this._stateGeojson) {
            this._applyStateColors(true);
        }
    }

    async setVoteTransfer(enabled) {
        this.voteTransferEnabled = enabled;
        if (enabled) {
            this.heatmapEnabled = false;
            this.demandsEnabled = false;
            this.itinerariesEnabled = false;
            this.strategicEnabled = false;
            this.plNetworkEnabled = false;
            this.zoneRankingEnabled = false;
            this.neighborDeputiesEnabled = false;
            this.elections2022Enabled = false;
            this._resetToNeutral();
            try {
                const [transferData, citiesGeojson] = await Promise.all([
                    API.dashboard.voteTransfer(),
                    API.maps.stateCities(),
                ]);
                this._voteTransferData = transferData;
                this._allCitiesGeojson = citiesGeojson;
            } catch (e) {
                this._voteTransferData = null;
                this._allCitiesGeojson = null;
            }
        }
        if (enabled && this._allCitiesGeojson) {
            this._renderTransferCityMap();
        }
    }

    _renderTransferCityMap() {
        if (!this._voteTransferData || !this._allCitiesGeojson) return;

        // Hide base map, remove previous transfer elements
        this.g.selectAll('path.region').style('display', 'none');
        this.g.selectAll('text').style('display', 'none');
        this.g.selectAll('.transfer-city,.transfer-arrow,.transfer-marker').remove();

        const geojson = this._allCitiesGeojson;
        const projection = d3.geoMercator()
            .fitExtent([[20, 10], [this.width - 20, this.height - 10]], geojson);
        const path = d3.geoPath().projection(projection);
        const self = this;

        // Mapa slug → dados de transferência
        const cityMap = {};
        for (const c of this._voteTransferData.cities) {
            cityMap[c.slug] = c;
        }

        // Tooltip montado AO VIVO no hover (lê _voteTransferData atual → nunca fica
        // defasado em relação ao painel quando um aliado é adicionado/removido).
        const buildTip = (name, slug) => {
            const city = (self._voteTransferData?.cities || []).find(c => c.slug === slug);
            if (!city) return `<div class="tooltip-title">${name}</div><div class="tooltip-row"><span class="tooltip-label" style="color:#9ca3af">Sem dados</span></div>`;
            let html = `<div class="tooltip-title">${name}</div>`;
            html += `<div class="tooltip-row"><span class="tooltip-label">Classificação</span> <span class="tooltip-value" style="color:${self._transferOppColor(city.opp_class)};font-weight:bold">${self._transferOppLabel(city.opp_class)}</span></div>`;
            html += `<div class="tooltip-row"><span class="tooltip-label">LS Penetração</span> <span class="tooltip-value" style="color:#15803d;font-weight:bold">${city.penetration}% (${(city.votes||0).toLocaleString('pt-BR')})</span></div>`;
            for (const a of (city.aliados || [])) {
                const forte = (city.aliados_fortes || []).includes(a.nome);
                html += `<div class="tooltip-row"><span class="tooltip-label">${a.nome}</span> <span class="tooltip-value" style="color:${a.cor};font-weight:${forte?'700':'400'}">${(a.votes||0).toLocaleString('pt-BR')} (${a.pct||0}%)${forte?' ★':''}</span></div>`;
            }
            if (city.votos_carona) html += `<div class="tooltip-row"><span class="tooltip-label">Votos de carona</span> <span class="tooltip-value" style="color:#7c3aed;font-weight:700">${city.votos_carona.toLocaleString('pt-BR')}</span></div>`;
            if ((city.agenda_aliados||[]).length) html += `<div class="tooltip-row"><span class="tooltip-value" style="color:#dc2626;font-weight:700">📅 Aliado com visita marcada!</span></div>`;
            html += '<div class="tooltip-row"><span class="tooltip-label" style="color:#9ca3af">Clique para agendar com o aliado</span></div>';
            return html;
        };

        // Desenhar polígonos das cidades
        this.g.selectAll('path.transfer-city')
            .data(geojson.features)
            .enter()
            .append('path')
            .attr('class', 'transfer-city')
            .attr('d', path)
            .attr('fill', d => {
                const city = cityMap[d.properties.slug];
                return city ? self._transferOppColor(city.opp_class) : '#d1d5db';
            })
            .attr('fill-opacity', 0.8)
            .attr('stroke', '#fff')
            .attr('stroke-width', 0.4)
            .attr('cursor', 'pointer')
            .on('mouseenter', (event, d) => {
                self._showTip(buildTip(d.properties.name, d.properties.slug), event.pageX, event.pageY);
            })
            .on('mousemove', (event) => { self._moveTip(event.pageX, event.pageY); })
            .on('mouseleave', () => { self._hideTip(); })
            .on('click', (event, d) => {
                self._hideTip();
                if (self.onCityAction) self.onCityAction(d.properties.slug);
                else window.location.href = `/mapa/cidade/${d.properties.slug}/?mapa=${self.mapMode}`;
            });

        // (setas de transferência removidas — o modelo agora é carona de chapa)

        // Reset zoom
        this.svg.transition().duration(300).call(this.zoom.transform, d3.zoomIdentity);
    }

    async setItineraries(enabled, showCompleted = false) {
        this.itinerariesEnabled = enabled;
        if (enabled) {
            this.heatmapEnabled = false;
            this.demandsEnabled = false;
            this.strategicEnabled = false;
            this.plNetworkEnabled = false;
            this.zoneRankingEnabled = false;
            this.voteTransferEnabled = false;
            this.neighborDeputiesEnabled = false;
            this.elections2022Enabled = false;
            this._resetToNeutral();
            try {
                this._itinerariesData = await API.roteiros.mapData(showCompleted);
            } catch (e) {
                this._itinerariesData = [];
            }
        }

        if (enabled && this.currentLevel === 'state' && this._stateGeojson) {
            this._applyStateColors(true);
            this._drawItineraryRoutes();
        }
    }

    _drawItineraryRoutes() {
        if (!this._itinerariesData || !this._stateGeojson) return;
        const projection = d3.geoMercator()
            .fitExtent([[20, 10], [this.width - 20, this.height - 10]], this._stateGeojson);
        const self = this;

        // Definir marcador de seta no SVG (defs)
        let defs = this.svg.select('defs');
        if (defs.empty()) defs = this.svg.append('defs');
        defs.selectAll('marker.arrow-marker').remove();

        this._itinerariesData.forEach((it, itIdx) => {
            if (it.stops.length === 0) return;

            const baseColor = it.status === 'completed' ? '#22c55e' : this._itineraryColors[itIdx % this._itineraryColors.length];
            const isDashed = it.status === 'planned' || it.status === 'confirmed';
            const opacity = it.status === 'completed' ? 0.4 : 1;
            const markerId = `arrow-${itIdx}`;

            // Criar seta para este roteiro
            defs.append('marker')
                .attr('class', 'arrow-marker')
                .attr('id', markerId)
                .attr('viewBox', '0 0 10 6')
                .attr('refX', 10)
                .attr('refY', 3)
                .attr('markerWidth', 8)
                .attr('markerHeight', 5)
                .attr('orient', 'auto')
                .append('path')
                .attr('d', 'M0,0 L10,3 L0,6 Z')
                .attr('fill', baseColor)
                .attr('fill-opacity', opacity);

            // Converter stops para coordenadas de tela
            const validStops = it.stops.filter(s => s.lat && s.lng);
            const points = validStops.map(s => projection([s.lng, s.lat]));

            if (points.length < 2) {
                // Apenas 1 parada — desenhar somente o marcador
                if (points.length === 1) {
                    this._drawStopMarker(points[0], validStops[0], it, baseColor, opacity, 0);
                }
                return;
            }

            const lineGen = d3.line().curve(d3.curveCardinal.tension(0.5));

            // Sombra/glow da linha
            this.g.append('path')
                .attr('class', 'itinerary-line')
                .attr('d', lineGen(points))
                .attr('fill', 'none')
                .attr('stroke', baseColor)
                .attr('stroke-width', 7)
                .attr('stroke-opacity', opacity * 0.15)
                .attr('stroke-linecap', 'round')
                .attr('pointer-events', 'none');

            // Linha principal
            const mainLine = this.g.append('path')
                .attr('class', 'itinerary-line')
                .attr('d', lineGen(points))
                .attr('fill', 'none')
                .attr('stroke', baseColor)
                .attr('stroke-width', 3)
                .attr('stroke-opacity', opacity)
                .attr('stroke-linecap', 'round')
                .attr('stroke-linejoin', 'round')
                .attr('marker-mid', `url(#${markerId})`)
                .attr('pointer-events', 'none');

            if (isDashed) {
                mainLine.attr('stroke-dasharray', '10,5');
                // Animacao dash-offset para rotas planejadas
                const totalLen = mainLine.node().getTotalLength();
                mainLine
                    .attr('stroke-dashoffset', 0)
                    .transition()
                    .duration(0) // Iniciar a animacao via CSS
                    .on('end', function() {
                        d3.select(this).classed('itinerary-animated', true);
                    });
            }

            // Desenhar setas intermediarias nos segmentos
            for (let i = 0; i < points.length - 1; i++) {
                const p1 = points[i], p2 = points[i + 1];
                const mx = (p1[0] + p2[0]) / 2;
                const my = (p1[1] + p2[1]) / 2;
                const angle = Math.atan2(p2[1] - p1[1], p2[0] - p1[0]) * 180 / Math.PI;

                this.g.append('polygon')
                    .attr('class', 'itinerary-marker')
                    .attr('points', '-4,-3 4,0 -4,3')
                    .attr('transform', `translate(${mx},${my}) rotate(${angle})`)
                    .attr('fill', baseColor)
                    .attr('fill-opacity', opacity * 0.8)
                    .attr('pointer-events', 'none');
            }

            // Marcadores nos pontos
            validStops.forEach((stop, i) => {
                if (stop.is_origin) {
                    this._drawOriginMarker(points[i], stop, it, baseColor, opacity);
                } else {
                    // Numerar sem contar a origem
                    const stopNum = stop.is_origin ? 0 : (validStops.slice(0, i).filter(s => !s.is_origin).length);
                    this._drawStopMarker(points[i], stop, it, baseColor, opacity, stopNum);
                }
            });
        });

        // Esconder labels de regiao no modo roteiros para limpar visual
        this.g.selectAll('text.region-label').attr('opacity', 0.3);
        this.g.selectAll('text.region-pop').attr('opacity', 0.15);
    }

    _drawOriginMarker(pt, stop, itinerary, color, opacity) {
        const self = this;

        // Losango (diamante) para diferenciar da parada
        const size = 9;
        const diamond = `M${pt[0]},${pt[1]-size} L${pt[0]+size},${pt[1]} L${pt[0]},${pt[1]+size} L${pt[0]-size},${pt[1]} Z`;

        this.g.append('path')
            .attr('class', 'itinerary-marker')
            .attr('d', diamond)
            .attr('fill', '#fff')
            .attr('stroke', color)
            .attr('stroke-width', 2.5)
            .attr('opacity', opacity)
            .attr('cursor', 'pointer')
            .on('mouseenter', (event) => {
                const html = `<div class="tooltip-title">${stop.city_name}</div><div class="tooltip-row"><span class="tooltip-label">Saída do roteiro</span></div><div class="tooltip-row"><span class="tooltip-label">Roteiro:</span> <span class="tooltip-value">${itinerary.name}</span></div>`;
                self._showTip(html, event.pageX, event.pageY);
            })
            .on('mousemove', (event) => { self._moveTip(event.pageX, event.pageY); })
            .on('mouseleave', () => { self._hideTip(); });

        // Icone estrela/casa dentro — usar texto simples
        this.g.append('text')
            .attr('class', 'itinerary-marker')
            .attr('x', pt[0]).attr('y', pt[1])
            .attr('text-anchor', 'middle')
            .attr('dy', '0.4em')
            .attr('font-size', '8px')
            .attr('fill', color)
            .attr('pointer-events', 'none')
            .text('\u2605'); // estrela

        // Label da cidade
        this.g.append('text')
            .attr('class', 'itinerary-marker')
            .attr('x', pt[0] + 13)
            .attr('y', pt[1])
            .attr('dy', '0.35em')
            .attr('font-size', '7px')
            .attr('font-weight', '600')
            .attr('fill', '#1e293b')
            .attr('paint-order', 'stroke')
            .attr('stroke', '#fff')
            .attr('stroke-width', '2.5px')
            .attr('pointer-events', 'none')
            .text(stop.city_name);
    }

    _drawStopMarker(pt, stop, itinerary, color, opacity, index) {
        const self = this;

        // Circulo com borda
        this.g.append('circle')
            .attr('class', 'itinerary-marker')
            .attr('cx', pt[0]).attr('cy', pt[1])
            .attr('r', 8)
            .attr('fill', color)
            .attr('stroke', '#fff')
            .attr('stroke-width', 2)
            .attr('opacity', opacity)
            .attr('cursor', 'pointer')
            .on('mouseenter', (event) => {
                self._showTip(self._stopTipHtml(stop, itinerary), event.pageX, event.pageY);
            })
            .on('mousemove', (event) => {
                self._moveTip(event.pageX, event.pageY);
            })
            .on('mouseleave', () => {
                self._hideTip();
            });

        // Numero dentro do circulo
        this.g.append('text')
            .attr('class', 'itinerary-marker')
            .attr('x', pt[0]).attr('y', pt[1])
            .attr('text-anchor', 'middle')
            .attr('dy', '0.35em')
            .attr('font-size', '7px')
            .attr('font-weight', '700')
            .attr('fill', '#fff')
            .attr('pointer-events', 'none')
            .text(index + 1);

        // Label com nome da cidade ao lado
        this.g.append('text')
            .attr('class', 'itinerary-marker')
            .attr('x', pt[0] + 12)
            .attr('y', pt[1])
            .attr('dy', '0.35em')
            .attr('font-size', '7px')
            .attr('font-weight', '600')
            .attr('fill', '#1e293b')
            .attr('paint-order', 'stroke')
            .attr('stroke', '#fff')
            .attr('stroke-width', '2.5px')
            .attr('pointer-events', 'none')
            .text(stop.city_name);
    }

    async setDoacoes(enabled) {
        this.doacoesEnabled = enabled;
        if (enabled) {
            this.heatmapEnabled = false;
            this.demandsEnabled = false;
            this.itinerariesEnabled = false;
            this.strategicEnabled = false;
            this.plNetworkEnabled = false;
            this.zoneRankingEnabled = false;
            this.voteTransferEnabled = false;
            this.neighborDeputiesEnabled = false;
            this.elections2022Enabled = false;
            this._resetToNeutral();
            try {
                const rawData = await API.doacoes.mapData();
                const regionsMap = {};
                let maxR = 0;
                for (const d of rawData) {
                    regionsMap[d.slug] = d;
                    if (d.total > maxR) maxR = d.total;
                }
                this._doacoesData = { regions: regionsMap, cities: {} };
                this._doacoesMaxRegion = Math.max(maxR, 1);
                this._doacoesMaxCity = 1;
            } catch (e) {
                this._doacoesData = null;
            }
        }
        if (this.currentLevel === 'state' && this._stateGeojson) {
            this._applyStateColors(true);
        } else if (this.currentLevel === 'region' && this._regionGeojson) {
            this._applyRegionColors(true);
        }
    }

    async setDemands(enabled) {
        this.demandsEnabled = enabled;
        if (enabled) {
            this.heatmapEnabled = false;
            this.itinerariesEnabled = false;
            this.strategicEnabled = false;
            this.plNetworkEnabled = false;
            this.zoneRankingEnabled = false;
            this.voteTransferEnabled = false;
            this.neighborDeputiesEnabled = false;
            this.elections2022Enabled = false;
            this.doacoesEnabled = false;
            this._resetToNeutral();
        }
        if (enabled) {
            try {
                const data = await API.demandas.mapStatus(this.demandTipo);
                this._demandsFull = data;
                this._demandsData = data.regions_map || {};
                this._demandsCities = data.cities || {};
                if (!this._promessasData) {
                    try { this._promessasData = await API.promessas.map(); } catch (e2) { this._promessasData = null; }
                }
            } catch (e) {
                this._demandsData = {}; this._demandsCities = {}; this._demandsFull = null;
            }
        }
        if (this.currentLevel === 'state' && this._stateGeojson) {
            this._applyStateColors(true);
        } else if (this.currentLevel === 'region' && this._regionGeojson) {
            this._applyRegionColors(true);
        }
    }

    setDemandLayer(layer) {
        this.demandLayer = layer;
        if (this.currentLevel === 'state' && this._stateGeojson) this._applyStateColors(false);
        else if (this.currentLevel === 'region' && this._regionGeojson) this._applyRegionColors(false);
    }

    _promessaColor(taxa) {
        if (taxa === null || taxa === undefined) return '#e2e8f0';  // sem promessas
        return d3.scaleLinear().domain([0, 50, 100]).range(['#dc2626', '#eab308', '#16a34a']).clamp(true)(taxa);
    }

    _promessaRegionTaxa(slug) {
        const r = (this._promessasData?.regions || {})[slug];
        if (!r || !r.total) return null;
        return Math.round(r.entregues / r.total * 100);
    }

    _mismatchColor(m) {
        // >0 oportunidade ignorada (vermelho), <0 esforço sobrando (azul)
        if (m === null || m === undefined) return '#e2e8f0';
        const sc = d3.scaleLinear().domain([-50, 0, 50]).range(['#3b82f6', '#f1f5f9', '#dc2626']).clamp(true);
        return sc(m);
    }

    _demandTipHtml(slug, level) {
        const src = level === 'region' ? this._demandsData : this._demandsCities;
        const o = (src || {})[slug];
        const nome = o ? o.name : slug;
        let html = `<div class="tooltip-title">${nome || ''}</div>`;
        if (!o) return html + '<div class="tooltip-row"><span style="color:#9ca3af">Sem dados</span></div>';
        if (this.demandLayer === 'promessas') {
            const pc = (this._promessasData?.cities || {})[slug] || (level==='region' ? null : null);
            const reg = level === 'region' ? (this._promessasData?.regions || {})[slug] : pc;
            const tot = reg ? reg.total : 0, ent = reg ? reg.entregues : 0;
            if (!tot) { html += '<div class="tooltip-row"><span style="color:#9ca3af">Sem promessas registradas</span></div>'; }
            else {
                const taxa = Math.round(ent / tot * 100);
                html += `<div class="tooltip-row"><span class="tooltip-label">Promessas:</span> <span class="tooltip-value">${tot}</span></div>`;
                html += `<div class="tooltip-row"><span class="tooltip-label">Entregues:</span> <span class="tooltip-value" style="color:${this._promessaColor(taxa)};font-weight:800">${ent} (${taxa}%)</span></div>`;
                html += `<div class="tooltip-row"><span class="tooltip-label">Pendentes:</span> <span class="tooltip-value">${tot-ent}</span></div>`;
            }
        } else if (this.demandLayer === 'mismatch') {
            const lbl = o.mismatch > 15 ? 'Oportunidade ignorada' : o.mismatch < -15 ? 'Esforço concentrado' : 'Equilibrado';
            html += `<div class="tooltip-row"><span class="tooltip-label">Esforço × oportunidade:</span> <span class="tooltip-value" style="color:${this._mismatchColor(o.mismatch)};font-weight:800">${lbl}</span></div>`;
            html += `<div class="tooltip-row"><span class="tooltip-label">Votos disponíveis:</span> <span class="tooltip-value">+${(o.gap||0).toLocaleString('pt-BR')}</span></div>`;
            html += `<div class="tooltip-row"><span class="tooltip-label">Tarefas ativas:</span> <span class="tooltip-value">${o.active||0}</span></div>`;
            if (o.alerta === 'negligencia') html += '<div class="tooltip-row"><span class="tooltip-value" style="color:#dc2626;font-weight:700">🚨 Oportunidade negligenciada</span></div>';
            if (o.alerta === 'desperdicio') html += '<div class="tooltip-row"><span class="tooltip-value" style="color:#2563eb;font-weight:700">↩ Esforço onde já temos pouco a ganhar</span></div>';
        } else {
            const lbl = o.status === 'overdue' ? 'Em atraso' : o.status === 'ok' ? 'Em dia' : 'Sem demandas';
            html += `<div class="tooltip-row"><span class="tooltip-label">Status:</span> <span class="tooltip-value" style="color:${this._demandColor(o.status)};font-weight:700">${lbl}</span></div>`;
            html += `<div class="tooltip-row"><span class="tooltip-label">Total / ativas:</span> <span class="tooltip-value">${o.total||0} / ${o.active||0}</span></div>`;
            if (o.overdue) html += `<div class="tooltip-row"><span class="tooltip-label">Vencidas:</span> <span class="tooltip-value" style="color:#ef4444;font-weight:700">${o.overdue}</span></div>`;
        }
        if (level !== 'region') html += '<div class="tooltip-row"><span class="tooltip-label" style="color:#9ca3af">Clique para o painel de ação</span></div>';
        return html;
    }

    _desaturate(hex) {
        // Converte cor hex para versao desaturada (cinza com leve tint)
        const r = parseInt(hex.slice(1,3), 16);
        const g = parseInt(hex.slice(3,5), 16);
        const b = parseInt(hex.slice(5,7), 16);
        const gray = Math.round(r * 0.3 + g * 0.59 + b * 0.11);
        // Misturar 70% cinza + 30% cor original
        const mr = Math.round(gray * 0.7 + r * 0.3);
        const mg = Math.round(gray * 0.7 + g * 0.3);
        const mb = Math.round(gray * 0.7 + b * 0.3);
        return `rgb(${mr},${mg},${mb})`;
    }

    _strategicRegionClass(regionSlug) {
        if (!this._strategicData) return 'neutro';
        const cities = this._strategicData.cities.filter(c => c.region_slug === regionSlug);
        if (cities.length === 0) return 'neutro';
        // Classificação predominante (mais frequente)
        const counts = {};
        for (const c of cities) {
            counts[c.classification] = (counts[c.classification] || 0) + 1;
        }
        return Object.entries(counts).sort((a, b) => b[1] - a[1])[0][0];
    }

    _strategicTipHtml(p) {
        if (!this._strategicData) return '';
        const cities = this._strategicData.cities.filter(c => c.region_slug === p.slug);
        const counts = {};
        for (const c of cities) {
            counts[c.classification] = (counts[c.classification] || 0) + 1;
        }
        const labels = { base_forte: 'Base Forte', aliado_fraco: 'Aliado Fraco', potencial_oculto: 'Potencial Oculto', territorio_hostil: 'Hostil', neutro: 'Neutro' };
        let html = `<div class="tooltip-title">${p.name}</div>`;
        for (const [cls, count] of Object.entries(counts).sort((a,b) => b[1]-a[1])) {
            const color = this._strategicColor(cls);
            html += `<div class="tooltip-row"><span class="tooltip-label"><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${color};margin-right:4px"></span>${labels[cls] || cls}</span> <span class="tooltip-value">${count} cidades</span></div>`;
        }
        html += `<div class="tooltip-row"><span class="tooltip-label" style="color:#9ca3af">Clique para ver cidades</span></div>`;
        return html;
    }

    _zoneRegionPerformance(regionSlug) {
        if (!this._zoneRankingData) return 'ausente';
        const czm = this._zoneRankingData.city_zone_map;
        // Coletar performances das cidades desta região
        const perfs = [];
        for (const [slug, info] of Object.entries(czm)) {
            // Precisamos saber se a cidade é desta região - usar geojson
            if (this._stateGeojson) {
                const feature = this._stateGeojson.features.find(f => f.properties.slug === regionSlug);
                if (feature && feature.properties.cities && feature.properties.cities.includes(slug)) {
                    perfs.push(info.performance);
                }
            }
        }
        // Fallback: buscar nas zones data
        if (perfs.length === 0) {
            for (const z of this._zoneRankingData.zones) {
                for (const c of z.cities) {
                    if (c.region_slug === regionSlug) {
                        perfs.push(z.performance);
                    }
                }
            }
        }
        if (perfs.length === 0) return 'ausente';
        // Melhor performance da região
        const order = ['lider', 'competitivo', 'medio', 'baixo', 'ausente'];
        perfs.sort((a, b) => order.indexOf(a) - order.indexOf(b));
        return perfs[0];
    }

    _zoneRegionAvgPosition(regionSlug) {
        if (!this._zoneRankingData) return 99;
        const positions = [];
        for (const z of this._zoneRankingData.zones) {
            for (const c of z.cities) {
                if (c.region_slug === regionSlug) {
                    positions.push(z.ls_position || 99);
                    break; // uma vez por zona
                }
            }
        }
        if (positions.length === 0) return 99;
        return Math.round(positions.reduce((s, p) => s + p, 0) / positions.length);
    }

    _zoneRegionTipHtml(p) {
        if (!this._zoneRankingData) return '';
        // Zonas desta região
        const regionZones = this._zoneRankingData.zones.filter(z =>
            z.cities.some(c => c.region_slug === p.slug)
        );
        let html = `<div class="tooltip-title">${p.name}</div>`;
        if (regionZones.length === 0) {
            html += `<div class="tooltip-row"><span class="tooltip-label" style="color:#9ca3af">Sem dados de zona</span></div>`;
            return html;
        }
        html += `<div class="tooltip-row"><span class="tooltip-label">Zonas na região</span> <span class="tooltip-value">${regionZones.length}</span></div>`;
        // Top 3 zonas
        const sorted = [...regionZones].sort((a, b) => a.ls_position - b.ls_position);
        for (const z of sorted.slice(0, 3)) {
            const color = this._zonePerformanceColor(z.performance);
            html += `<div class="tooltip-row"><span class="tooltip-label">Zona ${z.zone_number}</span> <span class="tooltip-value" style="color:${color}">${z.ls_position}º (${z.ls_votes.toLocaleString('pt-BR')} votos)</span></div>`;
        }
        if (sorted.length > 3) {
            html += `<div class="tooltip-row"><span class="tooltip-label" style="color:#9ca3af">+${sorted.length - 3} zonas...</span></div>`;
        }
        html += `<div class="tooltip-row"><span class="tooltip-label" style="color:#9ca3af">Clique para ver cidades</span></div>`;
        return html;
    }

    _zoneCityTipHtml(p) {
        if (!this._zoneRankingData) return this._cityTipHtml(p);
        const czm = this._zoneRankingData.city_zone_map[p.slug];
        if (!czm) return this._cityTipHtml(p);
        const color = this._zonePerformanceColor(czm.performance);
        let html = `<div class="tooltip-title">${p.name}</div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Zona</span> <span class="tooltip-value">${czm.zone_number}</span></div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Posição LS</span> <span class="tooltip-value" style="color:${color};font-weight:bold">${this._zonePerformanceLabel(czm.performance)} (${czm.ls_position}º)</span></div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Votos LS</span> <span class="tooltip-value">${czm.ls_votes.toLocaleString('pt-BR')}</span></div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Penetração</span> <span class="tooltip-value">${czm.ls_percentage}%</span></div>`;
        return html;
    }

    _plNetworkRegionScore(regionSlug) {
        if (!this._plNetworkData) return 0;
        const cities = this._plNetworkData.cities.filter(c => c.region_slug === regionSlug);
        if (cities.length === 0) return 0;
        return Math.round(cities.reduce((s, c) => s + c.score, 0) / cities.length);
    }

    _plNetworkRegionTipHtml(p) {
        if (!this._plNetworkData) return '';
        const cities = this._plNetworkData.cities.filter(c => c.region_slug === p.slug);
        const avgScore = cities.length ? Math.round(cities.reduce((s, c) => s + c.score, 0) / cities.length) : 0;
        const counts = { forte: 0, moderada: 0, fraca: 0, ausente: 0 };
        for (const c of cities) counts[c.level] = (counts[c.level] || 0) + 1;
        let html = `<div class="tooltip-title">${p.name}</div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Score médio</span> <span class="tooltip-value" style="color:${this._plNetworkColor(avgScore)};font-weight:bold">${avgScore}/100</span></div>`;
        for (const [level, count] of Object.entries(counts)) {
            if (count === 0) continue;
            html += `<div class="tooltip-row"><span class="tooltip-label"><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${this._plNetworkLevelColor(level)};margin-right:4px"></span>${this._plNetworkLevelLabel(level)}</span> <span class="tooltip-value">${count} cidades</span></div>`;
        }
        html += `<div class="tooltip-row"><span class="tooltip-label" style="color:#9ca3af">Clique para ver cidades</span></div>`;
        return html;
    }

    _plNetworkCityTipHtml(p) {
        if (!this._plNetworkData) return this._cityTipHtml(p);
        const city = this._plNetworkData.cities.find(c => c.slug === p.slug);
        if (!city) return this._cityTipHtml(p);
        const color = this._plNetworkColor(city.score);
        let html = `<div class="tooltip-title">${p.name}</div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Força PL</span> <span class="tooltip-value" style="color:${color};font-weight:bold">${this._plNetworkLevelLabel(city.level)} (${city.score}/100)</span></div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Coordenador</span> <span class="tooltip-value">${city.has_coordinator ? '✓ Sim' : '✗ Não'}</span></div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Vereadores PL</span> <span class="tooltip-value">${city.num_vereadores_pl}/${city.num_vereadores}</span></div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Diretório PL</span> <span class="tooltip-value">${city.pl_executive_president ? '✓ ' + city.pl_executive_president : '✗ Não'}</span></div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Apoiadores</span> <span class="tooltip-value">${city.apoiadores || 0}</span></div>`;
        return html;
    }

    _applyStateColors(instant) {
        const colorScale = this._heatScale();
        const self = this;
        const sel = this.g.selectAll('path.region');
        const t = instant ? sel : sel.transition().duration(400);
        t.attr('fill', function(d) {
                if (self.victoryEnabled && self._victoryData) {
                    const r = (self._victoryData.regions || {})[d.properties.slug];
                    return self._victoryColor(r ? r.nivel : 0);
                }
                if (self.visitUrgencyEnabled && self._visitUrgencyData) {
                    const r = (self._visitUrgencyData.regions || {})[d.properties.slug];
                    return self._urgencyColor(r ? r.nivel : 0);
                }
                if (self.voteTransferEnabled && self._voteTransferData) {
                    // Colorir região pela classificação cruzada mais relevante
                    const cities = self._voteTransferData.cities.filter(c => c.region_slug === d.properties.slug);
                    if (cities.length === 0) return '#d1d5db';
                    const order = ['zona_ouro', 'polo_ls', 'buscar_ambos', 'buscar_jorginho', 'buscar_carol', 'baixa_prioridade'];
                    const best = cities.reduce((b, c) => order.indexOf(c.opp_class) < order.indexOf(b) ? c.opp_class : b, 'baixa_prioridade');
                    return self._transferOppColor(best);
                }
                if (self.neighborDeputiesEnabled && self._neighborDeputiesData) {
                    const cities = self._neighborDeputiesData.cities.filter(c => c.region_slug === d.properties.slug);
                    if (cities.length === 0) return '#d1d5db';
                    const order = ['ponte_forte', 'base_conjunta', 'territorio_dep', 'territorio_ls', 'sem_presenca'];
                    const best = cities.reduce((b, c) => order.indexOf(c.classification) < order.indexOf(b) ? c.classification : b, 'sem_presenca');
                    return self._deputyClassColor(best);
                }
                if (self.zoneRankingEnabled) {
                    return self._zonePerformanceColor(self._zoneRegionPerformance(d.properties.slug));
                }
                if (self.plNetworkEnabled) {
                    return self._plNetworkColor(self._plNetworkRegionScore(d.properties.slug));
                }
                if (self.strategicEnabled) {
                    return self._strategicColor(self._strategicRegionClass(d.properties.slug));
                }
                if (self.demandsEnabled) {
                    if (self.demandLayer === 'promessas') return self._promessaColor(self._promessaRegionTaxa(d.properties.slug));
                    const dd = (self._demandsData || {})[d.properties.slug];
                    if (self.demandLayer === 'mismatch') return self._mismatchColor(dd ? dd.mismatch : null);
                    return self._demandColor(dd ? dd.status : 'empty');
                }
                if (self.elections2022Enabled && self._elections2022Data) {
                    const cities = self._elections2022Data.cities.filter(c => c.region_slug === d.properties.slug);
                    if (cities.length === 0) return '#d1d5db';
                    const avgPos = cities.reduce((s, c) => s + c.ls_position, 0) / cities.length;
                    if (avgPos <= 10) return '#15803d';
                    if (avgPos <= 20) return '#22c55e';
                    if (avgPos <= 40) return '#eab308';
                    if (avgPos <= 70) return '#f97316';
                    return '#ef4444';
                }
                if (self.doacoesEnabled && self._doacoesData) {
                    const rd = (self._doacoesData.regions || {})[d.properties.slug];
                    const valor = rd ? rd.total : 0;
                    return self._doacoesColor(valor, self._doacoesMaxRegion);
                }
                if (self.heatmapEnabled) {
                    if (self._heatLayersData) return self._heatColor(self.heatLayer, self._heatVal(d.properties.slug, 'region'));
                    const pct = self._penetracao(d.properties.total_votes_2022, d.properties.registered_voters);
                    return colorScale(pct);
                }
                const baseColor = d.properties.color || '#90a4ae';
                if (self.itinerariesEnabled) return self._desaturate(baseColor);
                return baseColor;
            })
            .attr('fill-opacity', (self.victoryEnabled ? 0.85 : self.visitUrgencyEnabled ? 0.8 : self.itinerariesEnabled ? 0.45 : (self.voteTransferEnabled) ? 0.5 : (self.heatmapEnabled || self.demandsEnabled || self.strategicEnabled || self.plNetworkEnabled || self.zoneRankingEnabled || self.neighborDeputiesEnabled || self.elections2022Enabled || self.doacoesEnabled) ? 0.85 : 0.75));

        // Cursor: desabilitar pointer no modo eleições
        this.g.selectAll('path.region')
            .attr('cursor', self.elections2022Enabled ? 'default' : 'pointer');

        // Animacao de pulso para regioes em atraso
        this.g.selectAll('path.region')
            .classed('pulse-overdue', d => {
                if (!self.demandsEnabled) return false;
                const dd = (self._demandsData || {})[d.properties.slug];
                return dd && dd.status === 'overdue';
            });

        // Restaurar labels quando nao estiver no modo roteiros
        if (!self.itinerariesEnabled) {
            this.g.selectAll('text.region-label').attr('opacity', 1);
            this.g.selectAll('text.region-pop').attr('opacity', 1);
        }

        // Atualizar tooltips
        const tipHtmls = new Map();
        for (const f of this._stateGeojson.features) {
            if (self.demandsEnabled) {
                tipHtmls.set(f.properties.slug, self._demandTipHtml(f.properties.slug, 'region'));
            } else if (self.heatmapEnabled && self._heatLayersData) {
                tipHtmls.set(f.properties.slug, self._heatTipHtml(f.properties, 'region'));
            } else if (self.victoryEnabled) {
                tipHtmls.set(f.properties.slug, self._victoryRegionTipHtml(f.properties));
            } else if (self.visitUrgencyEnabled) {
                tipHtmls.set(f.properties.slug, self._urgencyRegionTipHtml(f.properties));
            } else if (self.voteTransferEnabled) {
                // Tooltip com info cruzada da região
                const cities = (self._voteTransferData?.cities || []).filter(c => c.region_slug === f.properties.slug);
                const counts = {};
                for (const c of cities) counts[c.opp_class] = (counts[c.opp_class] || 0) + 1;
                let html = `<div class="tooltip-title">${f.properties.name}</div>`;
                for (const [cls, n] of Object.entries(counts)) {
                    if (n === 0) continue;
                    html += `<div class="tooltip-row"><span class="tooltip-label"><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${self._transferOppColor(cls)};margin-right:4px"></span>${self._transferOppLabel(cls)}</span> <span class="tooltip-value">${n}</span></div>`;
                }
                html += `<div class="tooltip-row"><span class="tooltip-label" style="color:#9ca3af">Clique para ver cidades</span></div>`;
                tipHtmls.set(f.properties.slug, html);
            } else if (self.neighborDeputiesEnabled) {
                const cities = (self._neighborDeputiesData?.cities || []).filter(c => c.region_slug === f.properties.slug);
                const counts = {};
                for (const c of cities) counts[c.classification] = (counts[c.classification] || 0) + 1;
                let html = `<div class="tooltip-title">${f.properties.name}</div>`;
                for (const [cls, n] of Object.entries(counts)) {
                    if (n === 0) continue;
                    html += `<div class="tooltip-row"><span class="tooltip-label"><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${self._deputyClassColor(cls)};margin-right:4px"></span>${self._deputyClassLabel(cls)}</span> <span class="tooltip-value">${n}</span></div>`;
                }
                html += `<div class="tooltip-row"><span class="tooltip-label" style="color:#9ca3af">Clique para ver cidades</span></div>`;
                tipHtmls.set(f.properties.slug, html);
            } else if (self.doacoesEnabled && self._doacoesData) {
                const rd = (self._doacoesData.regions || {})[f.properties.slug] || {};
                let html = `<div class="tooltip-title">${f.properties.name}</div>`;
                html += `<div class="tooltip-row"><span class="tooltip-label">Arrecadado:</span> <span class="tooltip-value" style="color:#1e3a8a;font-weight:bold">${fmt.currency(rd.total || 0)}</span></div>`;
                html += `<div class="tooltip-row"><span class="tooltip-label">Doadores:</span> <span class="tooltip-value">${rd.doadores || 0}</span></div>`;
                html += `<div class="tooltip-row"><span class="tooltip-label">Captadores:</span> <span class="tooltip-value">${rd.captadores || 0}</span></div>`;
                html += `<div class="tooltip-row"><span class="tooltip-label">Doações:</span> <span class="tooltip-value">${rd.count || 0}</span></div>`;
                if (rd.top_captadores && rd.top_captadores.length > 0) {
                    html += `<div class="tooltip-row" style="margin-top:4px"><span class="tooltip-label" style="font-weight:600">Top captadores:</span></div>`;
                    for (const c of rd.top_captadores.slice(0, 3)) {
                        html += `<div class="tooltip-row"><span class="tooltip-label" style="padding-left:8px">${c.nome}</span> <span class="tooltip-value">${fmt.currency(c.total)}</span></div>`;
                    }
                }
                html += `<div class="tooltip-row"><span class="tooltip-label" style="color:#9ca3af">Clique para ver detalhes</span></div>`;
                tipHtmls.set(f.properties.slug, html);
            } else if (self.elections2022Enabled && self._elections2022Data) {
                const cities = self._elections2022Data.cities.filter(c => c.region_slug === f.properties.slug);
                const totalVotes = cities.reduce((s, c) => s + c.ls_votes, 0);
                const avgPos = cities.length ? (cities.reduce((s, c) => s + c.ls_position, 0) / cities.length).toFixed(1) : '-';
                let html = `<div class="tooltip-title">${f.properties.name}</div>`;
                html += `<div class="tooltip-row"><span class="tooltip-label">Cidades:</span> <span class="tooltip-value">${cities.length}</span></div>`;
                html += `<div class="tooltip-row"><span class="tooltip-label">Votos LS:</span> <span class="tooltip-value">${fmt.number(totalVotes)}</span></div>`;
                html += `<div class="tooltip-row"><span class="tooltip-label">Posição média:</span> <span class="tooltip-value">${avgPos}º</span></div>`;
                tipHtmls.set(f.properties.slug, html);
            } else if (self.zoneRankingEnabled) {
                tipHtmls.set(f.properties.slug, this._zoneRegionTipHtml(f.properties));
            } else if (self.plNetworkEnabled) {
                tipHtmls.set(f.properties.slug, this._plNetworkRegionTipHtml(f.properties));
            } else if (self.strategicEnabled) {
                tipHtmls.set(f.properties.slug, this._strategicTipHtml(f.properties));
            } else {
                tipHtmls.set(f.properties.slug, this._stateTipHtml(f.properties));
            }
        }
        this.g.selectAll('path.region')
            .on('mouseenter', (event, d) => {
                this._showTip(tipHtmls.get(d.properties.slug), event.pageX, event.pageY);
            });
    }

    _strategicCityTipHtml(p) {
        if (!this._strategicData) return '';
        const city = this._strategicData.cities.find(c => c.slug === p.slug);
        if (!city) return this._cityTipHtml(p);
        const labels = { maquina_voto: '🏭 Máquina de voto', aliado_ativar: '🤝 Aliado a ativar', construir: '🏗️ Construir', disputa: '⚔️ Em disputa', hostil: '🚫 Hostil', neutro: '⚪ Neutro' };
        const color = this._strategicColor(city.classification);
        const po = city.politicos || {};
        let html = `<div class="tooltip-title">${p.name}</div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Classificação</span> <span class="tooltip-value" style="color:${color};font-weight:bold">${labels[city.classification] || city.classification}</span></div>`;
        if (po.aliados) {
            const partes = [];
            if (po.prefeito) partes.push(po.prefeito + ' prefeito');
            if (po.vereador) partes.push(po.vereador + ' vereador(es)');
            if (po.presidente) partes.push('diretório PL');
            html += `<div class="tooltip-row"><span class="tooltip-label">Aliados políticos</span> <span class="tooltip-value">${partes.join(', ') || po.aliados}</span></div>`;
            html += `<div class="tooltip-row"><span class="tooltip-label">Cabos engajados</span> <span class="tooltip-value" style="color:${po.cabos ? '#15803d' : '#dc2626'};font-weight:700">${po.cabos}${po.cabos ? '' : ' — dormindo!'}</span></div>`;
            if (po.meta_transferir) html += `<div class="tooltip-row"><span class="tooltip-label">Meta transferência</span> <span class="tooltip-value">${po.meta_transferir.toLocaleString('pt-BR')} votos</span></div>`;
        }
        html += `<div class="tooltip-row"><span class="tooltip-label">Votos LS 2022</span> <span class="tooltip-value">${(city.votes_2022 || 0).toLocaleString('pt-BR')} (${city.penetration.toFixed(2)}%)</span></div>`;
        if (city.gap) html += `<div class="tooltip-row"><span class="tooltip-label">Votos disponíveis</span> <span class="tooltip-value">+${city.gap.toLocaleString('pt-BR')}</span></div>`;
        if (city.adversario_nome) html += `<div class="tooltip-row"><span class="tooltip-label">Adversário</span> <span class="tooltip-value" style="color:#dc2626">${city.adversario_nome} (${city.adversario_partido})</span></div>`;
        html += '<div class="tooltip-row"><span class="tooltip-label" style="color:#9ca3af">Clique para marcar o controle</span></div>';
        return html;
    }

    _applyRegionColors(instant) {
        const colorScale = this._heatScale();
        const self = this;
        const sel = this.g.selectAll('path.city');
        const t = instant ? sel : sel.transition().duration(400);
        t.attr('fill', function(d) {
                if (self.demandsEnabled) {
                    if (self.demandLayer === 'promessas') {
                        const pc = (self._promessasData?.cities || {})[d.properties.slug];
                        return self._promessaColor(pc ? pc.taxa : null);
                    }
                    const c = (self._demandsCities || {})[d.properties.slug];
                    if (self.demandLayer === 'mismatch') return self._mismatchColor(c ? c.mismatch : null);
                    return self._demandColor(c ? c.status : 'empty');
                }
                if (self.victoryEnabled && self._victoryData) {
                    const c = (self._victoryData.cities || {})[d.properties.slug];
                    return self._victoryColor(c ? c.nivel : 0);
                }
                if (self.visitUrgencyEnabled && self._visitUrgencyData) {
                    const c = (self._visitUrgencyData.cities || {})[d.properties.slug];
                    return self._urgencyColor(c ? c.nivel : 0);
                }
                if (self.voteTransferEnabled && self._voteTransferData) {
                    const city = self._voteTransferData.cities.find(c => c.slug === d.properties.slug);
                    return city ? self._transferOppColor(city.opp_class) : '#d1d5db';
                }
                if (self.neighborDeputiesEnabled && self._neighborDeputiesData) {
                    const city = self._neighborDeputiesData.cities.find(c => c.slug === d.properties.slug);
                    return city ? self._deputyClassColor(city.classification) : '#d1d5db';
                }
                if (self.zoneRankingEnabled && self._zoneRankingData) {
                    const czm = self._zoneRankingData.city_zone_map[d.properties.slug];
                    return czm ? self._zonePerformanceColor(czm.performance) : '#d1d5db';
                }
                if (self.plNetworkEnabled && self._plNetworkData) {
                    const city = self._plNetworkData.cities.find(c => c.slug === d.properties.slug);
                    return city ? self._plNetworkColor(city.score) : '#d1d5db';
                }
                if (self.strategicEnabled && self._strategicData) {
                    const city = self._strategicData.cities.find(c => c.slug === d.properties.slug);
                    return city ? self._strategicColor(city.classification) : '#d1d5db';
                }
                if (self.doacoesEnabled && self._doacoesData) {
                    const cd = (self._doacoesData.cities || {})[d.properties.slug];
                    const valor = cd ? cd.total : 0;
                    return self._doacoesColor(valor, self._doacoesMaxCity);
                }
                if (!self.heatmapEnabled) return '#80a5dc';
                if (self._heatLayersData) return self._heatColor(self.heatLayer, self._heatVal(d.properties.slug, 'city'));
                const pct = self._penetracao(d.properties.votes_2022, d.properties.registered_voters);
                return colorScale(pct);
            })
            .attr('fill-opacity', (this.heatmapEnabled || this.strategicEnabled || this.plNetworkEnabled || this.zoneRankingEnabled || this.voteTransferEnabled || this.neighborDeputiesEnabled || this.doacoesEnabled || this.demandsEnabled || this.victoryEnabled) ? 0.85 : 0.7);

        // Atualizar tooltips
        const tipHtmls = new Map();
        for (const f of this._regionGeojson.features) {
            if (self.demandsEnabled) {
                tipHtmls.set(f.properties.slug, self._demandTipHtml(f.properties.slug, 'city'));
            } else if (self.heatmapEnabled && self._heatLayersData) {
                tipHtmls.set(f.properties.slug, self._heatTipHtml(f.properties, 'city'));
            } else if (self.victoryEnabled) {
                tipHtmls.set(f.properties.slug, self._victoryCityTipHtml(f.properties));
            } else if (self.visitUrgencyEnabled) {
                tipHtmls.set(f.properties.slug, self._urgencyCityTipHtml(f.properties));
            } else if (self.voteTransferEnabled) {
                const city = (self._voteTransferData?.cities || []).find(c => c.slug === f.properties.slug);
                if (city) {
                    let html = `<div class="tooltip-title">${f.properties.name}</div>`;
                    html += `<div class="tooltip-row"><span class="tooltip-label">Classificação</span> <span class="tooltip-value" style="color:${self._transferOppColor(city.opp_class)};font-weight:bold">${self._transferOppLabel(city.opp_class)}</span></div>`;
                    html += `<div class="tooltip-row"><span class="tooltip-label">LS Penetração</span> <span class="tooltip-value" style="color:#15803d">${city.penetration}%</span></div>`;
                    for (const a of (city.aliados || [])) {
                        const forte = (city.aliados_fortes || []).includes(a.nome);
                        html += `<div class="tooltip-row"><span class="tooltip-label">${a.nome}</span> <span class="tooltip-value" style="color:${a.cor};font-weight:${forte?'700':'400'}">${(a.votes||0).toLocaleString('pt-BR')} (${a.pct||0}%)${forte?' ★':''}</span></div>`;
                    }
                    if (city.votos_carona) html += `<div class="tooltip-row"><span class="tooltip-label">Votos de carona</span> <span class="tooltip-value" style="color:#7c3aed;font-weight:700">${city.votos_carona.toLocaleString('pt-BR')}</span></div>`;
                    if ((city.agenda_aliados||[]).length) html += `<div class="tooltip-row"><span class="tooltip-value" style="color:#dc2626;font-weight:700">📅 Aliado(s) com visita marcada!</span></div>`;
                    html += '<div class="tooltip-row"><span class="tooltip-label" style="color:#9ca3af">Clique para agendar com o aliado</span></div>';
                    tipHtmls.set(f.properties.slug, html);
                } else {
                    tipHtmls.set(f.properties.slug, self._cityTipHtml(f.properties));
                }
            } else if (self.neighborDeputiesEnabled) {
                const city = (self._neighborDeputiesData?.cities || []).find(c => c.slug === f.properties.slug);
                if (city) {
                    let html = `<div class="tooltip-title">${f.properties.name}</div>`;
                    html += `<div class="tooltip-row"><span class="tooltip-label">Classificação</span> <span class="tooltip-value" style="color:${self._deputyClassColor(city.classification)};font-weight:bold">${self._deputyClassLabel(city.classification)}</span></div>`;
                    html += `<div class="tooltip-row"><span class="tooltip-label">LS</span> <span class="tooltip-value" style="color:#15803d">${city.ls_votes.toLocaleString('pt-BR')} (${city.ls_pct}%)</span></div>`;
                    if (city.best_dep_name) {
                        html += `<div class="tooltip-row"><span class="tooltip-label">Dep. mais votado</span> <span class="tooltip-value" style="color:#2563eb">${city.best_dep_name} (${city.best_dep_pct}%)</span></div>`;
                    }
                    for (const dep of (city.top3_deps || []).slice(1)) {
                        html += `<div class="tooltip-row"><span class="tooltip-label" style="padding-left:8px">${dep.name}</span> <span class="tooltip-value">${dep.votes.toLocaleString('pt-BR')} (${dep.pct}%)</span></div>`;
                    }
                    tipHtmls.set(f.properties.slug, html);
                } else {
                    tipHtmls.set(f.properties.slug, self._cityTipHtml(f.properties));
                }
            } else if (self.doacoesEnabled && self._doacoesData) {
                const cd = (self._doacoesData.cities || {})[f.properties.slug] || {};
                let html = `<div class="tooltip-title">${f.properties.name}</div>`;
                html += `<div class="tooltip-row"><span class="tooltip-label">Arrecadado:</span> <span class="tooltip-value" style="color:#1e3a8a;font-weight:bold">${fmt.currency(cd.total || 0)}</span></div>`;
                html += `<div class="tooltip-row"><span class="tooltip-label">Doadores:</span> <span class="tooltip-value">${cd.doadores || 0}</span></div>`;
                html += `<div class="tooltip-row"><span class="tooltip-label">Doações:</span> <span class="tooltip-value">${cd.count || 0}</span></div>`;
                tipHtmls.set(f.properties.slug, html);
            } else if (self.zoneRankingEnabled) {
                tipHtmls.set(f.properties.slug, this._zoneCityTipHtml(f.properties));
            } else if (self.plNetworkEnabled) {
                tipHtmls.set(f.properties.slug, this._plNetworkCityTipHtml(f.properties));
            } else if (self.strategicEnabled) {
                tipHtmls.set(f.properties.slug, this._strategicCityTipHtml(f.properties));
            } else {
                tipHtmls.set(f.properties.slug, this._cityTipHtml(f.properties));
            }
        }
        this.g.selectAll('path.city')
            .on('mouseenter', (event, d) => {
                this._showTip(tipHtmls.get(d.properties.slug), event.pageX, event.pageY);
            })
            .on('click', (event, d) => {
                this._hideTip();
                if ((self.visitUrgencyEnabled || self.victoryEnabled || self.heatmapEnabled || self.demandsEnabled || self.strategicEnabled || self.voteTransferEnabled) && self.onCityAction) {
                    self.onCityAction(d.properties.slug);
                    return;
                }
                if (self.onCityClick) self.onCityClick(d.properties.slug);
                else window.location.href = `/mapa/cidade/${d.properties.slug}/?mapa=${self.mapMode}`;
            });
    }

    async loadState() {
        try {
            const geojson = await API.maps.state();
            if (!geojson.features || geojson.features.length === 0) {
                this._showEmpty('Sem dados GeoJSON. Execute: python manage.py load_geojson');
                return;
            }

            this.currentLevel = 'state';
            this.currentSlug = null;
            this._stateGeojson = geojson;
            this.g.selectAll('*').remove();

            const projection = d3.geoMercator()
                .fitExtent([[20, 10], [this.width - 20, this.height - 10]], geojson);
            const path = d3.geoPath().projection(projection);

            const colorScale = this._heatScale();
            const self = this;

            // Pre-computar HTML dos tooltips
            const tipHtmls = new Map();
            for (const f of geojson.features) {
                tipHtmls.set(f.properties.slug, this._stateTipHtml(f.properties));
            }

            // Regioes
            this.g.selectAll('path.region')
                .data(geojson.features)
                .enter()
                .append('path')
                .attr('class', 'region')
                .attr('d', path)
                .attr('fill', d => {
                    if (self.demandsEnabled) {
                        const dd = (self._demandsData || {})[d.properties.slug];
                        return self._demandColor(dd ? dd.status : 'empty');
                    }
                    if (self.heatmapEnabled) {
                        const pct = self._penetracao(d.properties.total_votes_2022, d.properties.registered_voters);
                        return colorScale(pct);
                    }
                    return d.properties.color || '#90a4ae';
                })
                .attr('fill-opacity', (self.heatmapEnabled || self.demandsEnabled) ? 0.85 : 0.75)
                .attr('stroke', '#fff')
                .attr('stroke-width', 1.2)
                .attr('cursor', 'pointer')
                .on('mouseenter', (event, d) => {
                    this._showTip(tipHtmls.get(d.properties.slug), event.pageX, event.pageY);
                })
                .on('mousemove', (event) => {
                    this._moveTip(event.pageX, event.pageY);
                })
                .on('mouseleave', () => {
                    this._hideTip();
                })
                .on('click', (event, d) => {
                    this._hideTip();
                    if (this.elections2022Enabled) return;
                    const slug = d.properties.slug;
                    this.zoomToRegion(slug);
                    if (this.onRegionClick) this.onRegionClick(slug);
                });

            // Labels
            this.g.selectAll('text.region-label')
                .data(geojson.features)
                .enter()
                .append('text')
                .attr('class', 'region-label')
                .attr('x', d => path.centroid(d)[0])
                .attr('y', d => path.centroid(d)[1] - 4)
                .attr('text-anchor', 'middle')
                .attr('font-size', '8px')
                .attr('font-weight', '700')
                .attr('fill', '#222')
                .attr('pointer-events', 'none')
                .attr('paint-order', 'stroke')
                .attr('stroke', '#fff')
                .attr('stroke-width', '2px')
                .text(d => d.properties.name);

            // Populacao
            this.g.selectAll('text.region-pop')
                .data(geojson.features)
                .enter()
                .append('text')
                .attr('class', 'region-pop')
                .attr('x', d => path.centroid(d)[0])
                .attr('y', d => path.centroid(d)[1] + 7)
                .attr('text-anchor', 'middle')
                .attr('font-size', '6.5px')
                .attr('fill', '#444')
                .attr('pointer-events', 'none')
                .attr('paint-order', 'stroke')
                .attr('stroke', '#fff')
                .attr('stroke-width', '2px')
                .text(d => fmt.number(d.properties.population));

            // Reset zoom
            this.svg.transition().duration(300).call(this.zoom.transform, d3.zoomIdentity);

        } catch (e) {
            console.error('Erro ao carregar mapa:', e);
            this._showEmpty('Erro ao carregar mapa.');
        }
    }

    async zoomToRegion(slug) {
        try {
            const geojson = await API.maps.region(slug);
            if (!geojson.features || geojson.features.length === 0) {
                window.location.href = `/mapa/regiao/${slug}/?mapa=${this.mapMode}`;
                return;
            }

            this.currentLevel = 'region';
            this.currentSlug = slug;
            this._regionGeojson = geojson;
            this.g.selectAll('*').remove();

            const projection = d3.geoMercator()
                .fitExtent([[30, 20], [this.width - 30, this.height - 20]], geojson);
            const path = d3.geoPath().projection(projection);

            const colorScale = this._heatScale();
            const self = this;

            // Pre-computar tooltips
            const tipHtmls = new Map();
            for (const f of geojson.features) {
                tipHtmls.set(f.properties.slug, this._cityTipHtml(f.properties));
            }

            this.g.selectAll('path.city')
                .data(geojson.features)
                .enter()
                .append('path')
                .attr('class', 'city')
                .attr('d', path)
                .attr('fill', d => {
                    if (!self.heatmapEnabled) return '#80a5dc';
                    const pct = self._penetracao(d.properties.votes_2022, d.properties.registered_voters);
                    return colorScale(pct);
                })
                .attr('fill-opacity', this.heatmapEnabled ? 0.85 : 0.7)
                .attr('stroke', '#003DA5')
                .attr('stroke-width', 1)
                .attr('cursor', 'pointer')
                .on('mouseenter', (event, d) => {
                    this._showTip(tipHtmls.get(d.properties.slug), event.pageX, event.pageY);
                })
                .on('mousemove', (event) => {
                    this._moveTip(event.pageX, event.pageY);
                })
                .on('mouseleave', () => {
                    this._hideTip();
                })
                .on('click', (event, d) => {
                    this._hideTip();
                    if ((this.visitUrgencyEnabled || this.victoryEnabled || this.heatmapEnabled || this.demandsEnabled || this.strategicEnabled || this.voteTransferEnabled) && this.onCityAction) {
                        this.onCityAction(d.properties.slug);
                        return;
                    }
                    if (this.onCityClick) this.onCityClick(d.properties.slug);
                    else window.location.href = `/mapa/cidade/${d.properties.slug}/?mapa=${this.mapMode}`;
                });

            // City labels
            this.g.selectAll('text.city-label')
                .data(geojson.features)
                .enter()
                .append('text')
                .attr('class', 'city-label')
                .attr('x', d => path.centroid(d)[0])
                .attr('y', d => path.centroid(d)[1])
                .attr('text-anchor', 'middle')
                .attr('dy', '0.35em')
                .attr('font-size', '7.5px')
                .attr('font-weight', '600')
                .attr('fill', '#002776')
                .attr('pointer-events', 'none')
                .attr('paint-order', 'stroke')
                .attr('stroke', '#fff')
                .attr('stroke-width', '2px')
                .text(d => d.properties.name);

            this.svg.transition().duration(300).call(this.zoom.transform, d3.zoomIdentity);

            if (this.visitUrgencyEnabled || this.victoryEnabled || this.heatmapEnabled || this.demandsEnabled) this._applyRegionColors(true);

        } catch (e) {
            console.error('Erro zoom regiao:', e);
        }
    }

    backToState() {
        this.loadState();
    }

    _showEmpty(msg) {
        this.g.selectAll('*').remove();
        this.g.append('text')
            .attr('x', this.width / 2)
            .attr('y', this.height / 2)
            .attr('text-anchor', 'middle')
            .attr('fill', '#999')
            .attr('font-size', '14px')
            .text(msg);
    }
}
