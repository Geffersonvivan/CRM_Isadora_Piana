/**
 * Lideranças — Funções compartilhadas
 * Máscara de telefone + carregamento dinâmico de cidades por região
 */

(function () {
    'use strict';

    // ===== Máscara de telefone =====
    function initPhoneMask(selector) {
        const el = document.querySelector(selector || '#id_telefone');
        if (!el) return;
        el.addEventListener('input', function (e) {
            let v = e.target.value.replace(/\D/g, '');
            if (v.length > 11) v = v.slice(0, 11);
            if (v.length <= 2) v = v.replace(/^(\d{0,2})/, '($1');
            else if (v.length <= 6) v = v.replace(/^(\d{2})(\d{0,4})/, '($1) $2');
            else if (v.length <= 10) v = v.replace(/^(\d{2})(\d{4})(\d{0,4})/, '($1) $2-$3');
            else v = v.replace(/^(\d{2})(\d{5})(\d{0,4})/, '($1) $2-$3');
            e.target.value = v;
        });
    }

    // ===== Carregamento de cidades por região =====
    function initCityLoader(regiaoSelector, cidadeSelector, keepCurrent) {
        const regiao = document.querySelector(regiaoSelector || '#id_regiao');
        const cidade = document.querySelector(cidadeSelector || '#id_cidade');
        if (!regiao || !cidade) return;

        const cidadeAtual = cidade.value;

        regiao.addEventListener('change', function () {
            const regiaoId = regiao.value;
            cidade.innerHTML = '<option value="">---------</option>';
            if (!regiaoId) return;

            fetch('/liderancas/api/cidades/' + regiaoId + '/')
                .then(function (r) { return r.json(); })
                .then(function (cidades) {
                    cidades.forEach(function (c) {
                        var opt = document.createElement('option');
                        opt.value = c.id;
                        opt.textContent = c.nome;
                        if (keepCurrent && String(c.id) === String(cidadeAtual)) {
                            opt.selected = true;
                        }
                        cidade.appendChild(opt);
                    });
                });
        });
    }

    // ===== Carregamento de cidades nos filtros =====
    function initFilterCityLoader(regiaoSelector, cidadeSelector) {
        const regiao = document.querySelector(regiaoSelector || '#filtroRegiao');
        const cidade = document.querySelector(cidadeSelector || '#filtroCidade');
        if (!regiao || !cidade) return;

        regiao.addEventListener('change', function () {
            var regiaoId = regiao.value;
            cidade.innerHTML = '<option value="">Todas</option>';
            if (!regiaoId) return;

            fetch('/liderancas/api/cidades/' + regiaoId + '/')
                .then(function (r) { return r.json(); })
                .then(function (cidades) {
                    cidades.forEach(function (c) {
                        var opt = document.createElement('option');
                        opt.value = c.id;
                        opt.textContent = c.nome;
                        cidade.appendChild(opt);
                    });
                });
        });
    }

    // ===== Dropdown customizado de região com preview de cidades no hover =====
    // O <select> nativo do macOS não exibe tooltip nas opções, então trocamos o select
    // de região por um dropdown próprio: cada linha carrega data-tip (o balão #ajTip já
    // existente em base.html) com as cidades da região. O <select> nativo permanece no
    // DOM (escondido) como fonte de verdade — sincronizamos o valor e disparamos 'change'
    // para não quebrar o carregamento de cidades/coordenadores que já existe.
    var _regioesCidadesPromise = null;
    function _fetchRegioesCidades() {
        if (!_regioesCidadesPromise) {
            _regioesCidadesPromise = fetch('/liderancas/api/regioes-cidades/')
                .then(function (r) { return r.json(); })
                .catch(function () { return {}; });  // offline/erro: dropdown sem preview, sem quebrar
        }
        return _regioesCidadesPromise;
    }

    var CARET = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E";
    function _injectRcdCss() {
        if (document.getElementById('rcd-css')) return;
        var st = document.createElement('style');
        st.id = 'rcd-css';
        st.textContent =
            '.rcd{position:relative;width:100%;}' +
            '.rcd-btn{display:flex;align-items:center;width:100%;text-align:left;padding-right:34px;' +
            'position:relative;box-sizing:border-box;}' +
            ".rcd-btn::after{content:'';position:absolute;right:12px;top:50%;width:12px;height:12px;" +
            'margin-top:-6px;pointer-events:none;background:url("' + CARET + '") no-repeat center;}' +
            '.rcd-btn:focus{outline:none;border-color:var(--accent);background:#fff;box-shadow:0 0 0 3px var(--accent-ring);}' +
            '.rcd-label{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block;width:100%;}' +
            '.rcd-label.rcd-placeholder{color:#94a3b8;}' +
            '.rcd-list{position:absolute;z-index:900;top:calc(100% + 4px);left:0;right:0;max-height:320px;' +
            'overflow-y:auto;background:#fff;border:1.5px solid #e2e8f0;border-radius:12px;' +
            'box-shadow:0 12px 30px rgba(0,0,0,.14);padding:4px;display:none;}' +
            '.rcd.open .rcd-list{display:block;}' +
            '.rcd-opt{padding:8px 12px;border-radius:8px;font-size:0.85rem;color:#1e293b;cursor:pointer;line-height:1.35;}' +
            '.rcd-opt:hover,.rcd-opt.active{background:var(--accent-ring);}' +
            ".rcd-opt[aria-selected='true']{font-weight:600;color:var(--accent);}" +
            '.rcd-search{position:sticky;top:0;z-index:1;box-sizing:border-box;width:100%;' +
            'margin-bottom:4px;padding:9px 11px;border:1.5px solid #e2e8f0;border-radius:8px;' +
            'font-size:0.85rem;background:#fff;}' +
            '.rcd-search:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-ring);}' +
            '.rcd-empty{padding:8px 12px;font-size:0.82rem;color:#94a3b8;}';
        document.head.appendChild(st);
    }

    function _buildRegiaoDropdown(select, mapa) {
        if (!select || select.dataset.rcdEnhanced === '1') return;
        select.dataset.rcdEnhanced = '1';
        _injectRcdCss();

        var wrap = document.createElement('div');
        wrap.className = 'rcd';
        var btn = document.createElement('div');
        btn.className = 'rcd-btn ' + (select.className || '');
        btn.setAttribute('tabindex', '0');
        btn.setAttribute('role', 'combobox');
        btn.setAttribute('aria-haspopup', 'listbox');
        btn.setAttribute('aria-expanded', 'false');
        var label = document.createElement('span');
        label.className = 'rcd-label';
        btn.appendChild(label);
        var list = document.createElement('div');
        list.className = 'rcd-list';
        list.setAttribute('role', 'listbox');

        // Caixa de busca (filtra as regiões por digitação, sem acento/maiúscula)
        var search = document.createElement('input');
        search.type = 'text';
        search.className = 'rcd-search';
        search.setAttribute('placeholder', 'Buscar região…');
        search.setAttribute('autocomplete', 'off');
        list.appendChild(search);
        function _norm(s) { return (s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, ''); }

        function syncLabel() {
            var opt = select.options[select.selectedIndex];
            label.textContent = opt ? opt.text : '';
            label.classList.toggle('rcd-placeholder', !select.value);
        }

        var rows = [];
        Array.prototype.forEach.call(select.options, function (opt) {
            var row = document.createElement('div');
            row.className = 'rcd-opt';
            row.setAttribute('role', 'option');
            row.textContent = opt.text;
            row.dataset.value = opt.value;
            var cidades = mapa[opt.value];
            if (cidades && cidades.length) {
                row.setAttribute('data-tip', opt.text + '|' + cidades.join(', '));
            }
            row.setAttribute('aria-selected', opt.value === select.value ? 'true' : 'false');
            row.addEventListener('click', function () {
                if (select.value !== opt.value) {
                    select.value = opt.value;
                    select.dispatchEvent(new Event('change', { bubbles: true }));
                }
                syncLabel();
                markSelected();
                close();
            });
            list.appendChild(row);
            rows.push(row);
        });

        function markSelected() {
            rows.forEach(function (r) {
                r.setAttribute('aria-selected', r.dataset.value === select.value ? 'true' : 'false');
            });
        }

        var emptyMsg = document.createElement('div');
        emptyMsg.className = 'rcd-empty';
        emptyMsg.textContent = 'Nenhuma região encontrada';
        emptyMsg.style.display = 'none';
        list.appendChild(emptyMsg);

        var activeRow = null;
        function visibleRows() { return rows.filter(function (r) { return r.style.display !== 'none'; }); }
        function setActiveRow(r) {
            if (activeRow) activeRow.classList.remove('active');
            activeRow = r || null;
            if (activeRow) { activeRow.classList.add('active'); activeRow.scrollIntoView({ block: 'nearest' }); }
        }
        function move(delta) {
            var vis = visibleRows();
            if (!vis.length) { setActiveRow(null); return; }
            var cur = vis.indexOf(activeRow);
            var next = cur < 0 ? (delta > 0 ? 0 : vis.length - 1) : (cur + delta + vis.length) % vis.length;
            setActiveRow(vis[next]);
        }
        function applyFilter(term) {
            var t = _norm(term);
            rows.forEach(function (r) {
                r.style.display = (!t || _norm(r.textContent).indexOf(t) !== -1) ? '' : 'none';
            });
            var vis = visibleRows();
            emptyMsg.style.display = vis.length ? 'none' : '';
            setActiveRow(vis.length ? vis[0] : null);
        }
        function open() {
            document.querySelectorAll('.rcd.open').forEach(function (w) { if (w !== wrap) w.classList.remove('open'); });
            wrap.classList.add('open');
            btn.setAttribute('aria-expanded', 'true');
            search.value = '';
            applyFilter('');
            var selRow = rows.filter(function (r) { return r.dataset.value === select.value; })[0];
            if (selRow) setActiveRow(selRow);
            search.focus();
        }
        function close() {
            wrap.classList.remove('open');
            btn.setAttribute('aria-expanded', 'false');
        }

        btn.addEventListener('click', function () {
            wrap.classList.contains('open') ? close() : open();
        });
        btn.addEventListener('keydown', function (e) {
            var isOpen = wrap.classList.contains('open');
            if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (!isOpen) open(); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); if (!isOpen) open(); }
            else if (e.key === 'Escape') { close(); }
        });
        search.addEventListener('input', function () { applyFilter(search.value); });
        search.addEventListener('keydown', function (e) {
            if (e.key === 'ArrowDown') { e.preventDefault(); move(1); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); move(-1); }
            else if (e.key === 'Enter') { e.preventDefault(); if (activeRow) activeRow.click(); }
            else if (e.key === 'Escape') { e.preventDefault(); close(); btn.focus(); }
        });

        select.style.display = 'none';
        select.parentNode.insertBefore(wrap, select.nextSibling);
        wrap.appendChild(btn);
        wrap.appendChild(list);
        select.addEventListener('change', function () { syncLabel(); markSelected(); });
        syncLabel();
    }

    function initRegiaoCustomDropdown(root) {
        var scope = root && root.querySelectorAll ? root : document;
        _fetchRegioesCidades().then(function (mapa) {
            scope.querySelectorAll('select[name="regiao"]').forEach(function (s) {
                _buildRegiaoDropdown(s, mapa);
            });
        });
    }

    // Fechar dropdown ao clicar fora (uma vez só)
    if (!document.__rcdOutside) {
        document.__rcdOutside = true;
        document.addEventListener('click', function (e) {
            document.querySelectorAll('.rcd.open').forEach(function (w) {
                if (!w.contains(e.target)) w.classList.remove('open');
            });
        });
    }

    // Enhancer para selects que aparecem depois (form-modal da agenda, etc.)
    if (!window.__rcdObserver && typeof MutationObserver !== 'undefined') {
        window.__rcdObserver = new MutationObserver(function (muts) {
            for (var i = 0; i < muts.length; i++) {
                var added = muts[i].addedNodes;
                for (var j = 0; j < added.length; j++) {
                    var n = added[j];
                    if (n.nodeType !== 1) continue;
                    if (n.matches && n.matches('select[name="regiao"]')) initRegiaoCustomDropdown(n.parentNode);
                    else if (n.querySelector && n.querySelector('select[name="regiao"]')) initRegiaoCustomDropdown(n);
                }
            }
        });
    }

    // ===== Território derivado da cidade (Isadora) =====
    // Escolhida a cidade, preenche os campos read-only Assoc/Micro/Meso a partir do
    // lookup embutido (#cidadeRegioes). Funciona na página cheia e no modal.
    function initCidadeDerivados(scope) {
        var root = (scope && document.querySelector(scope)) || document;
        var island = root.querySelector('#cidadeRegioes') || document.getElementById('cidadeRegioes');
        var cid = root.querySelector('#id_cidade');
        if (!island || !cid || cid.dataset.derivadosWired) return;
        cid.dataset.derivadosWired = '1';
        var mapa;
        try { mapa = JSON.parse(island.textContent || '{}'); } catch (e) { return; }
        var assoc = root.querySelector('#id_assoc_display');
        var micro = root.querySelector('#id_micro_display');
        var meso = root.querySelector('#id_meso_display');
        function preencher() {
            var r = mapa[cid.value] || ['', '', ''];
            if (assoc) assoc.value = r[0] || '';
            if (micro) micro.value = r[1] || '';
            if (meso) meso.value = r[2] || '';
        }
        cid.addEventListener('change', preencher);
        preencher();
    }

    // ===== Busca na cidade (combo pesquisável sobre o <select> nativo) =====
    function _injectCsbCss() {
        if (document.getElementById('csb-css')) return;
        var st = document.createElement('style'); st.id = 'csb-css';
        st.textContent =
            '.csb{position:relative;width:100%;}' +
            '.csb-list{position:absolute;z-index:950;top:calc(100% + 4px);left:0;right:0;' +
            'max-height:280px;overflow-y:auto;background:#fff;border:1.5px solid #e2e8f0;' +
            'border-radius:12px;box-shadow:0 12px 30px rgba(0,0,0,.14);padding:4px;}' +
            '.csb-opt{padding:8px 12px;border-radius:8px;font-size:0.85rem;color:#1e293b;cursor:pointer;line-height:1.35;}' +
            '.csb-opt:hover,.csb-opt.active{background:var(--accent-ring,#eef2ff);}' +
            '.csb-empty{padding:8px 12px;font-size:0.82rem;color:#94a3b8;}';
        document.head.appendChild(st);
    }
    function initCidadeSearch(scope) {
        var root = (scope && document.querySelector(scope)) || document;
        var sel = root.querySelector('select#id_cidade');
        if (!sel || sel.dataset.searchable) return;
        _injectCsbCss();
        sel.dataset.searchable = '1';
        sel.style.display = 'none';
        var wrap = document.createElement('div'); wrap.className = 'csb';
        var input = document.createElement('input');
        input.type = 'text'; input.className = 'form-input csb-input';
        input.placeholder = 'Buscar cidade…'; input.autocomplete = 'off';
        var list = document.createElement('div'); list.className = 'csb-list'; list.hidden = true;
        sel.parentNode.insertBefore(wrap, sel);
        wrap.appendChild(input); wrap.appendChild(sel); wrap.appendChild(list);
        if (sel.value && sel.options[sel.selectedIndex]) input.value = sel.options[sel.selectedIndex].textContent;
        function render(f) {
            f = (f || '').toLowerCase(); list.innerHTML = ''; var n = 0;
            Array.prototype.forEach.call(sel.options, function (opt) {
                if (!opt.value) return;
                if (f && opt.textContent.toLowerCase().indexOf(f) === -1) return;
                if (n++ >= 60) return;
                var d = document.createElement('div'); d.className = 'csb-opt'; d.textContent = opt.textContent;
                d.addEventListener('mousedown', function (e) {
                    e.preventDefault();
                    sel.value = opt.value; input.value = opt.textContent; list.hidden = true;
                    sel.dispatchEvent(new Event('change', { bubbles: true }));
                });
                list.appendChild(d);
            });
            if (!n) { var em = document.createElement('div'); em.className = 'csb-empty'; em.textContent = 'Nenhuma cidade'; list.appendChild(em); }
            list.hidden = false;
        }
        input.addEventListener('focus', function () { render(input.value); });
        input.addEventListener('input', function () { render(input.value); });
        input.addEventListener('blur', function () { setTimeout(function () { list.hidden = true; }, 150); });
    }

    // ===== Cidade-primeiro (Sorgatto): cidade buscável → região derivada =====
    // Genérico para qualquer form: cidade vira o ponto de partida (combo buscável)
    // e a região é preenchida a partir do lookup #cidadeRegioesMap. Preenche o
    // display read-only (#id_regiao_display) e/ou o <select name="regiao"> (se o
    // form ainda o submete, escondido). Idempotente via data-attr no #id_cidade.
    function initCidadePrimeiro(scope) {
        var root = (scope && document.querySelector(scope)) || document;
        var island = root.querySelector('#cidadeRegioesMap') || document.getElementById('cidadeRegioesMap');
        var cid = root.querySelector('#id_cidade');
        if (!island || !cid || cid.dataset.cpWired) return;
        cid.dataset.cpWired = '1';
        initCidadeSearch(scope);
        var mapa;
        try { mapa = JSON.parse(island.textContent || '{}'); } catch (e) { return; }
        var disp = root.querySelector('#id_regiao_display');
        var regSel = root.querySelector('select[name="regiao"]');
        function preencher() {
            var info = mapa[cid.value];
            if (disp) disp.value = info ? info.nome : '';
            if (regSel && info && info.rid) regSel.value = info.rid;
        }
        cid.addEventListener('change', preencher);
        preencher();
    }

    // Expose
    window.LiderancasCommon = {
        initPhoneMask: initPhoneMask,
        initCityLoader: initCityLoader,
        initFilterCityLoader: initFilterCityLoader,
        initRegiaoCustomDropdown: initRegiaoCustomDropdown,
        initCidadeDerivados: initCidadeDerivados,
        initCidadeSearch: initCidadeSearch,
        initCidadePrimeiro: initCidadePrimeiro,
    };

    // Auto-init em todos os selects de região (uma vez só)
    if (!window.__rcdInit) {
        window.__rcdInit = true;
        function _rcdStart() {
            initRegiaoCustomDropdown();
            if (window.__rcdObserver) window.__rcdObserver.observe(document.body, { childList: true, subtree: true });
        }
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', _rcdStart);
        } else {
            _rcdStart();
        }
    }

    // Auto-init do território derivado (Isadora): funciona na página cheia E quando
    // o form é injetado num modal — sem depender de quem chama initWidgets. Observa
    // o DOM e liga busca+preenchimento assim que a ilha #cidadeRegioes aparece.
    if (!window.__cidadeAutoInit) {
        window.__cidadeAutoInit = true;
        function _cidadeStart() {
            if (!document.getElementById('cidadeRegioes')) return;
            initCidadeSearch();
            initCidadeDerivados();
        }
        var _obs = new MutationObserver(function () { _cidadeStart(); });
        function _boot() { _cidadeStart(); _obs.observe(document.body, { childList: true, subtree: true }); }
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', _boot);
        } else {
            _boot();
        }
    }

    // Auto-init cidade-primeiro (Sorgatto): liga busca+derivação da região assim
    // que a ilha #cidadeRegioesMap aparece — funciona na página cheia e no modal.
    if (!window.__cpAutoInit) {
        window.__cpAutoInit = true;
        function _cpStart() { if (document.getElementById('cidadeRegioesMap')) initCidadePrimeiro(); }
        var _cpObs = new MutationObserver(function () { _cpStart(); });
        function _cpBoot() { _cpStart(); _cpObs.observe(document.body, { childList: true, subtree: true }); }
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', _cpBoot);
        } else {
            _cpBoot();
        }
    }
})();

// ===== Menu "⋯" das linhas de listagem =====
// (o arquivo pode ser incluído 2x — base.html e extra_js — então registra uma vez só)
if (!window.__rowMenuBound) {
window.__rowMenuBound = true;
document.addEventListener('click', function (e) {
    const trigger = e.target.closest('[data-row-menu]');
    document.querySelectorAll('.row-menu.open').forEach(function (m) {
        if (!trigger || m !== trigger.nextElementSibling) m.classList.remove('open');
    });
    if (!trigger) return;
    const menu = trigger.nextElementSibling;
    if (!menu || !menu.classList.contains('row-menu')) return;
    if (menu.classList.contains('open')) { menu.classList.remove('open'); return; }
    const r = trigger.getBoundingClientRect();
    menu.classList.add('open');
    const h = menu.offsetHeight || 90;
    const top = (r.bottom + h + 8 > window.innerHeight) ? (r.top - h - 4) : (r.bottom + 4);
    menu.style.top = top + 'px';
    menu.style.left = Math.max(8, r.right - 165) + 'px';
});
}

// ===== Copiar canal (e-mail) com feedback no tooltip =====
window.copyChan = function (btn, text) {
    function feedback() {
        var original = btn.getAttribute('data-tip');
        btn.setAttribute('data-tip', 'Copiado!');
        setTimeout(function () { btn.setAttribute('data-tip', original); }, 1400);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(feedback);
    } else {
        var ta = document.createElement('textarea');
        ta.value = text; document.body.appendChild(ta);
        ta.select(); document.execCommand('copy'); ta.remove();
        feedback();
    }
};

