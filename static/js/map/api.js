// API client para o módulo de Mapas
function apiGet(url) {
    return fetch(url, {
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {'X-Requested-With': 'XMLHttpRequest'},
    }).then(r => {
        if (!r.ok) throw new Error(`API ${r.status}: ${url}`);
        return r.json();
    });
}

const API = {
    maps: {
        state: () => apiGet('/mapa/api/state/'),
        stateCities: () => apiGet('/mapa/api/state-cities/'),
        region: (slug) => apiGet(`/mapa/api/region/${slug}/`),
        city: (slug) => apiGet(`/mapa/api/city/${slug}/`),
        heatmap: (metric) => apiGet(`/mapa/api/heatmap/${metric}/`),
        victory: () => apiGet('/mapa/api/vitoria/'),
        heatLayers: () => apiGet('/mapa/api/calor-camadas/'),
    },
    dashboard: {
        overview: () => apiGet('/mapa/api/overview/'),
        region: (slug) => apiGet(`/mapa/api/dashboard/region/${slug}/`),
        city: (slug) => apiGet(`/mapa/api/dashboard/city/${slug}/`),
        strategic: () => apiGet('/mapa/api/strategic/'),
        plNetwork: () => apiGet('/mapa/api/pl-network/'),
        zoneRanking: () => apiGet('/mapa/api/zone-ranking/'),
        voteTransfer: () => apiGet('/mapa/api/vote-transfer/'),
        neighborDeputies: () => apiGet('/mapa/api/neighbor-deputies/'),
        elections2022: () => apiGet('/mapa/api/elections-2022/'),
    },
    doacoes: {
        mapData: () => apiGet('/mapa/api/doacoes/'),
    },
    demandas: {
        mapStatus: (tipo) => apiGet('/mapa/api/demandas/' + (tipo ? '?tipo=' + tipo : '')),
    },
    roteiros: {
        mapData: (showCompleted) => apiGet(`/mapa/api/roteiros/?completed=${showCompleted}`),
        dia: (showCompleted) => apiGet(`/mapa/api/roteiro-dia/?completed=${showCompleted}`),
        oportunidades: () => apiGet('/mapa/api/roteiro-oportunidades/'),
        urgency: () => apiGet('/mapa/api/urgencia-visita/'),
        cityAction: (slug) => apiGet(`/mapa/api/cidade-acao/${slug}/`),
    },
    perfilIdeologico: {
        _cache: null,
        async dados(ano = 2022) {
            if (!this._cache) {
                this._cache = apiGet(`/mapa/api/perfil-ideologico/?ano=${ano}&_v=4`);
                try { await this._cache; } catch(e) { this._cache = null; throw e; }
            }
            return this._cache;
        },
    },
    competicao: {
        _cache: {},
        candidatos() {
            if (!this._cacheCandidatos) this._cacheCandidatos = apiGet('/mapa/api/competicao/');
            return this._cacheCandidatos;
        },
        cidades(cand) {
            if (!this._cache[cand]) this._cache[cand] = apiGet(`/mapa/api/competicao/?cand=${encodeURIComponent(cand)}`);
            return this._cache[cand];
        },
    },
};

// Formatador de números
const fmt = {
    number: (n) => (n || 0).toLocaleString('pt-BR'),
    currency: (n) => 'R$ ' + (n || 0).toLocaleString('pt-BR', {minimumFractionDigits: 2}),
    pct: (n) => (n || 0).toFixed(1) + '%',
};
