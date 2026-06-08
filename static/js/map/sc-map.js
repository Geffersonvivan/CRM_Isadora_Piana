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
        this.itinerariesEnabled = false;
        this.strategicEnabled = false;
        this.plNetworkEnabled = false;
        this.zoneRankingEnabled = false;
        this.voteTransferEnabled = false;
        this.neighborDeputiesEnabled = false;
        this.elections2022Enabled = false;
        this.doacoesEnabled = false;
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

    _strategicColor(classification) {
        const map = {
            base_forte: '#15803d',
            aliado_fraco: '#86efac',
            potencial_oculto: '#eab308',
            territorio_hostil: '#dc2626',
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
            zona_ouro: '#fbbf24',
            buscar_ambos: '#7c3aed',
            buscar_jorginho: '#2563eb',
            buscar_carol: '#ec4899',
            polo_ls: '#15803d',
            baixa_prioridade: '#d1d5db',
        };
        return map[opp_class] || '#d1d5db';
    }

    _transferOppLabel(opp_class) {
        const map = {
            zona_ouro: 'Zona de Ouro',
            buscar_ambos: 'Buscar Ambos',
            buscar_jorginho: 'Buscar Jorginho',
            buscar_carol: 'Buscar Carol',
            polo_ls: 'Polo LS',
            baixa_prioridade: 'Baixa Prioridade',
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

        this.zoom = d3.zoom()
            .scaleExtent([1, 1])
            .on('zoom', () => {});
        this.svg.on('.zoom', null);

        return this;
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
            if (!this._perfilData) {
                try { this._perfilData = await API.perfilIdeologico.dados(); }
                catch (e) { this._perfilData = null; }
            }
        }
        if (!enabled) {
            this._resetToNeutral();
        }
        if (enabled && this._allCitiesGeojson && this._perfilData) {
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

    _perfilTipHtml(d) {
        const slug = d.properties.slug;
        const cidades = this._perfilData?.cidades || {};
        const c = cidades[slug];
        let html = `<div class="tooltip-title">${d.properties.name}</div>`;
        if (!c) {
            html += `<div class="tooltip-row"><span style="color:#9ca3af">Sem dados</span></div>`;
            return html;
        }
        const scoreLabel = c.score <= 0.35 ? 'Esquerda' : c.score <= 0.55 ? 'Centro' : c.score <= 0.75 ? 'Centro-Direita' : 'Direita';
        const scoreColor = this._perfilColor(c.score);
        html += `<div class="tooltip-row"><span class="tooltip-label">Índice</span> <span class="tooltip-value" style="color:${scoreColor};font-weight:bold">${(c.score * 100).toFixed(1)} — ${scoreLabel}</span></div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Score Socioecon.</span> <span class="tooltip-value">${(c.score_socio * 100).toFixed(1)}</span></div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Score Eleitoral</span> <span class="tooltip-value">${(c.score_eleitoral * 100).toFixed(1)}</span></div>`;
        if (c.votos_total > 0) {
            html += `<div class="tooltip-row"><span class="tooltip-label">Votos Direita</span> <span class="tooltip-value" style="color:#1565C0">${c.votos_dir.toLocaleString('pt-BR')}</span></div>`;
            html += `<div class="tooltip-row"><span class="tooltip-label">Votos Esquerda</span> <span class="tooltip-value" style="color:#E53935">${c.votos_esq.toLocaleString('pt-BR')}</span></div>`;
        }
        if (!c.tem_indicadores) {
            html += `<div class="tooltip-row"><span style="color:#f59e0b;font-size:.75rem">⚠ Sem indicadores socioeconômicos</span></div>`;
        }
        return html;
    }

    _renderPerfilIdeologicoCityMap() {
        if (!this._allCitiesGeojson || !this._perfilData) return;
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
        const cidades = this._perfilData.cidades || {};

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
                window.location.href = `/mapa/cidade/${d.properties.slug}/`;
            });

        enter.merge(paths)
            .transition().duration(400)
            .attr('fill', d => {
                const c = cidades[d.properties.slug];
                return c ? self._perfilColor(c.score) : '#e2e8f0';
            });
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
                window.location.href = `/mapa/cidade/${d.properties.slug}/?mapa=${self.mapMode}`;
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
        this.g.selectAll('.itinerary-line,.itinerary-marker,.transfer-arrow,.transfer-marker,.transfer-city,.concorrencia-city,.perfil-city').remove();
    }

    setHeatmap(enabled) {
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

        // Pre-computar tooltips
        const tipHtmls = new Map();
        for (const f of geojson.features) {
            const city = cityMap[f.properties.slug];
            if (city) {
                let html = `<div class="tooltip-title">${f.properties.name}</div>`;
                html += `<div class="tooltip-row"><span class="tooltip-label">Classificação</span> <span class="tooltip-value" style="color:${self._transferOppColor(city.opp_class)};font-weight:bold">${self._transferOppLabel(city.opp_class)}</span></div>`;
                html += `<div class="tooltip-row"><span class="tooltip-label">LS Penetração</span> <span class="tooltip-value" style="color:#15803d;font-weight:bold">${city.penetration}%</span></div>`;
                html += `<div class="tooltip-row"><span class="tooltip-label">Votos LS</span> <span class="tooltip-value">${city.votes.toLocaleString('pt-BR')}</span></div>`;
                html += `<div class="tooltip-row"><span class="tooltip-label">Jorginho Melo</span> <span class="tooltip-value" style="color:#2563eb">${(city.jorginho_votes||0).toLocaleString('pt-BR')} (${city.jorginho_pct||0}%)</span></div>`;
                html += `<div class="tooltip-row"><span class="tooltip-label">Carol De Toni</span> <span class="tooltip-value" style="color:#ec4899">${(city.carol_votes||0).toLocaleString('pt-BR')} (${city.carol_pct||0}%)</span></div>`;
                html += `<div class="tooltip-row"><span class="tooltip-label">Eleitores</span> <span class="tooltip-value">${city.voters.toLocaleString('pt-BR')}</span></div>`;
                tipHtmls.set(f.properties.slug, html);
            } else {
                tipHtmls.set(f.properties.slug, `<div class="tooltip-title">${f.properties.name}</div><div class="tooltip-row"><span class="tooltip-label" style="color:#9ca3af">Sem dados</span></div>`);
            }
        }

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
                self._showTip(tipHtmls.get(d.properties.slug), event.pageX, event.pageY);
            })
            .on('mousemove', (event) => { self._moveTip(event.pageX, event.pageY); })
            .on('mouseleave', () => { self._hideTip(); })
            .on('click', (event, d) => {
                self._hideTip();
                window.location.href = `/mapa/cidade/${d.properties.slug}/?mapa=${self.mapMode}`;
            });

        // Desenhar setas de transferência
        let defs = this.svg.select('defs');
        if (defs.empty()) defs = this.svg.append('defs');
        defs.selectAll('marker.transfer-arrow-marker').remove();

        ['alta', 'media'].forEach(pri => {
            const color = this._transferPriorityColor(pri);
            defs.append('marker')
                .attr('class', 'transfer-arrow-marker')
                .attr('id', `transfer-arrow-${pri}`)
                .attr('viewBox', '0 0 10 6')
                .attr('refX', 10)
                .attr('refY', 3)
                .attr('markerWidth', 7)
                .attr('markerHeight', 4)
                .attr('orient', 'auto')
                .append('path')
                .attr('d', 'M0,0 L10,3 L0,6 Z')
                .attr('fill', color)
                .attr('fill-opacity', 0.7);
        });

        const topOpps = this._voteTransferData.opportunities
            .filter(o => o.priority === 'alta')
            .slice(0, 50);

        topOpps.forEach(opp => {
            const src = projection([opp.source.cx, opp.source.cy]);
            const tgt = projection([opp.target.cx, opp.target.cy]);
            if (!src || !tgt) return;

            const color = this._transferPriorityColor(opp.priority);
            const width = Math.max(1.5, Math.min(4, opp.potential_votes / 1000));

            // Sombra
            this.g.append('line')
                .attr('class', 'transfer-arrow')
                .attr('x1', src[0]).attr('y1', src[1])
                .attr('x2', tgt[0]).attr('y2', tgt[1])
                .attr('stroke', color)
                .attr('stroke-width', width + 3)
                .attr('stroke-opacity', 0.08)
                .attr('pointer-events', 'none');

            // Linha
            this.g.append('line')
                .attr('class', 'transfer-arrow')
                .attr('x1', src[0]).attr('y1', src[1])
                .attr('x2', tgt[0]).attr('y2', tgt[1])
                .attr('stroke', color)
                .attr('stroke-width', width)
                .attr('stroke-opacity', 0.6)
                .attr('marker-end', `url(#transfer-arrow-${opp.priority})`)
                .attr('cursor', 'pointer')
                .on('mouseenter', (event) => {
                    let html = `<div class="tooltip-title">${opp.source.name} → ${opp.target.name}</div>`;
                    html += `<div class="tooltip-row"><span class="tooltip-label">LS origem</span> <span class="tooltip-value" style="color:#15803d">${opp.source.penetration}%</span></div>`;
                    html += `<div class="tooltip-row"><span class="tooltip-label">LS alvo</span> <span class="tooltip-value" style="color:#f97316">${opp.target.penetration}%</span></div>`;
                    html += `<div class="tooltip-row"><span class="tooltip-label">Diferença</span> <span class="tooltip-value">${opp.pen_diff}%</span></div>`;
                    html += `<div class="tooltip-row"><span class="tooltip-label">Potencial</span> <span class="tooltip-value" style="font-weight:bold">+${opp.potential_votes.toLocaleString('pt-BR')} votos</span></div>`;
                    html += `<div class="tooltip-row"><span class="tooltip-label">Distância</span> <span class="tooltip-value">${opp.distance_km}km</span></div>`;
                    self._showTip(html, event.pageX, event.pageY);
                })
                .on('mousemove', (event) => { self._moveTip(event.pageX, event.pageY); })
                .on('mouseleave', () => { self._hideTip(); });
        });

        // Marcadores nos polos
        const polos = new Map();
        topOpps.forEach(opp => {
            if (!polos.has(opp.source.slug)) polos.set(opp.source.slug, opp.source);
        });
        polos.forEach(src => {
            const pt = projection([src.cx, src.cy]);
            if (!pt) return;
            this.g.append('circle')
                .attr('class', 'transfer-marker')
                .attr('cx', pt[0]).attr('cy', pt[1])
                .attr('r', 4)
                .attr('fill', '#15803d')
                .attr('stroke', '#fff')
                .attr('stroke-width', 1.5)
                .attr('opacity', 0.9)
                .attr('pointer-events', 'none');
        });

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
                this._demandsData = {};
                const data = await API.demandas.mapStatus();
                for (const d of data) {
                    this._demandsData[d.slug] = d;
                }
            } catch (e) {
                this._demandsData = {};
            }
        }
        if (this.currentLevel === 'state' && this._stateGeojson) {
            this._applyStateColors(true);
        } else if (this.currentLevel === 'region' && this._regionGeojson) {
            this._applyRegionColors(true);
        }
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
                    const dd = (self._demandsData || {})[d.properties.slug];
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
                    const pct = self._penetracao(d.properties.total_votes_2022, d.properties.registered_voters);
                    return colorScale(pct);
                }
                const baseColor = d.properties.color || '#90a4ae';
                if (self.itinerariesEnabled) return self._desaturate(baseColor);
                return baseColor;
            })
            .attr('fill-opacity', (self.itinerariesEnabled ? 0.45 : (self.voteTransferEnabled) ? 0.5 : (self.heatmapEnabled || self.demandsEnabled || self.strategicEnabled || self.plNetworkEnabled || self.zoneRankingEnabled || self.neighborDeputiesEnabled || self.elections2022Enabled || self.doacoesEnabled) ? 0.85 : 0.75));

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
            if (self.voteTransferEnabled) {
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
        const labels = { base_forte: 'Base Forte', aliado_fraco: 'Aliado Fraco', potencial_oculto: 'Potencial Oculto', territorio_hostil: 'Território Hostil', neutro: 'Neutro' };
        const color = this._strategicColor(city.classification);
        let html = `<div class="tooltip-title">${p.name}</div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Classificação</span> <span class="tooltip-value" style="color:${color};font-weight:bold">${labels[city.classification] || city.classification}</span></div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Score</span> <span class="tooltip-value">${city.score}/100</span></div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Prefeito</span> <span class="tooltip-value">${city.mayor_name || '-'} (${city.mayor_party || '-'})</span></div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Votos LS 2022</span> <span class="tooltip-value">${(city.votes_2022 || 0).toLocaleString('pt-BR')}</span></div>`;
        html += `<div class="tooltip-row"><span class="tooltip-label">Penetração</span> <span class="tooltip-value">${city.penetration.toFixed(2)}%</span></div>`;
        return html;
    }

    _applyRegionColors(instant) {
        const colorScale = this._heatScale();
        const self = this;
        const sel = this.g.selectAll('path.city');
        const t = instant ? sel : sel.transition().duration(400);
        t.attr('fill', function(d) {
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
                const pct = self._penetracao(d.properties.votes_2022, d.properties.registered_voters);
                return colorScale(pct);
            })
            .attr('fill-opacity', (this.heatmapEnabled || this.strategicEnabled || this.plNetworkEnabled || this.zoneRankingEnabled || this.voteTransferEnabled || this.neighborDeputiesEnabled || this.doacoesEnabled) ? 0.85 : 0.7);

        // Atualizar tooltips
        const tipHtmls = new Map();
        for (const f of this._regionGeojson.features) {
            if (self.voteTransferEnabled) {
                const city = (self._voteTransferData?.cities || []).find(c => c.slug === f.properties.slug);
                if (city) {
                    let html = `<div class="tooltip-title">${f.properties.name}</div>`;
                    html += `<div class="tooltip-row"><span class="tooltip-label">Classificação</span> <span class="tooltip-value" style="color:${self._transferOppColor(city.opp_class)};font-weight:bold">${self._transferOppLabel(city.opp_class)}</span></div>`;
                    html += `<div class="tooltip-row"><span class="tooltip-label">LS Penetração</span> <span class="tooltip-value" style="color:#15803d">${city.penetration}%</span></div>`;
                    html += `<div class="tooltip-row"><span class="tooltip-label">Jorginho Melo</span> <span class="tooltip-value" style="color:#2563eb">${(city.jorginho_votes||0).toLocaleString('pt-BR')} (${city.jorginho_pct||0}%)</span></div>`;
                    html += `<div class="tooltip-row"><span class="tooltip-label">Carol De Toni</span> <span class="tooltip-value" style="color:#ec4899">${(city.carol_votes||0).toLocaleString('pt-BR')} (${city.carol_pct||0}%)</span></div>`;
                    html += `<div class="tooltip-row"><span class="tooltip-label">Eleitores</span> <span class="tooltip-value">${city.voters.toLocaleString('pt-BR')}</span></div>`;
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
