/* PWA Apoiadores — fila offline (IndexedDB) + sincronização + microfone (Whisper).
   Cadastro funciona sem internet: salva localmente e envia quando voltar a rede.
   Transcrição do microfone é ONLINE (grava no aparelho e transcreve no servidor). */
(function () {
    'use strict';

    var DB_NAME = 'ls_pwa', STORE = 'pending', DB_VER = 1;
    var SYNC_URL = '/app/api/sync/';
    var TRANSCRIBE_URL = '/app/api/transcrever/';

    // ---------- util ----------
    function uuid() {
        if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
            var r = Math.random() * 16 | 0, v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }
    function csrftoken() {
        var m = document.cookie.match(/csrftoken=([^;]+)/);
        return m ? m[1] : '';
    }
    function toast(msg, kind) {
        var t = document.getElementById('toast');
        t.textContent = msg;
        t.className = 'toast show' + (kind ? ' ' + kind : '');
        setTimeout(function () { t.className = 'toast'; }, 2600);
    }

    // ---------- IndexedDB ----------
    function openDB() {
        return new Promise(function (resolve, reject) {
            var req = indexedDB.open(DB_NAME, DB_VER);
            req.onupgradeneeded = function (e) {
                var db = e.target.result;
                if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: 'client_id' });
            };
            req.onsuccess = function () { resolve(req.result); };
            req.onerror = function () { reject(req.error); };
        });
    }
    function tx(mode, fn) {
        return openDB().then(function (db) {
            return new Promise(function (resolve, reject) {
                var t = db.transaction(STORE, mode), store = t.objectStore(STORE), out = fn(store);
                t.oncomplete = function () { resolve(out && out.result !== undefined ? out.result : out); };
                t.onerror = function () { reject(t.error); };
            });
        });
    }
    function queue(rec) { return tx('readwrite', function (s) { return s.put(rec); }); }
    function remove(id) { return tx('readwrite', function (s) { return s.delete(id); }); }
    function getAll() {
        return openDB().then(function (db) {
            return new Promise(function (resolve, reject) {
                var req = db.transaction(STORE).objectStore(STORE).getAll();
                req.onsuccess = function () { resolve(req.result || []); };
                req.onerror = function () { reject(req.error); };
            });
        });
    }

    // Descarta os cadastros que o servidor rejeitou por validação (precisam de revisão).
    function discardErros() {
        return getAll().then(function (rows) {
            var chain = Promise.resolve();
            rows.filter(function (r) { return r._error; }).forEach(function (r) {
                chain = chain.then(function () { return remove(r.client_id); });
            });
            return chain.then(updateStatus);
        });
    }

    // ---------- status / badge ----------
    function updateStatus() {
        var bar = document.getElementById('syncBar'), txt = document.getElementById('syncText');
        var online = navigator.onLine;
        bar.className = 'sync-bar ' + (online ? 'online' : 'offline');
        txt.textContent = online ? 'Online' : 'Offline — os cadastros serão enviados ao reconectar';
        getAll().then(function (rows) {
            // Pendentes = aguardam envio. Com erro = rejeitados na validação (não reenviar).
            var pend = rows.filter(function (r) { return !r._error; });
            var errs = rows.filter(function (r) { return r._error; });
            var pendBox = document.getElementById('syncPend');
            document.getElementById('pendCount').textContent = pend.length;
            pendBox.style.display = pend.length ? '' : 'none';
            var errBox = document.getElementById('syncErr');
            if (errBox) {
                document.getElementById('errCount').textContent = errs.length;
                errBox.style.display = errs.length ? '' : 'none';
            }
        });
    }

    // ---------- sincronização ----------
    var syncing = false;
    function sync() {
        if (syncing || !navigator.onLine) { updateStatus(); return Promise.resolve(); }
        syncing = true;
        return getAll().then(function (rows) {
            // Só reenvia o que ainda está pendente — registros já rejeitados não voltam.
            var toSend = rows.filter(function (r) { return !r._error; });
            if (!toSend.length) { syncing = false; updateStatus(); return; }
            return fetch(SYNC_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken() },
                body: JSON.stringify({ records: toSend })
            }).then(function (r) { return r.json(); }).then(function (data) {
                var ok = 0, err = 0, chain = Promise.resolve();
                var byId = {};
                toSend.forEach(function (r) { byId[r.client_id] = r; });
                (data.results || []).forEach(function (res) {
                    if (res.status === 'ok') {
                        ok++; chain = chain.then(function () { return remove(res.client_id); });
                    } else {
                        // Erro vindo do servidor é permanente (validação): marca p/ revisão
                        // e para de reenviar — senão retransmite a cada reconexão.
                        err++;
                        var rec = byId[res.client_id];
                        if (rec) {
                            rec._error = res.error || 'Dados rejeitados';
                            chain = chain.then(function () { return queue(rec); });
                        }
                    }
                });
                return chain.then(function () {
                    syncing = false;
                    updateStatus();
                    if (ok) toast(ok + ' cadastro(s) enviado(s) ✓', 'success');
                    if (err) toast(err + ' com erro — revise e reenvie ou descarte', 'error');
                });
            }).catch(function () { syncing = false; updateStatus(); });
        });
    }

    // ---------- formulário ----------
    function bindForm() {
        var form = document.getElementById('formApoiador');
        if (!form) return;
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            var nome = (form.querySelector('#id_nome') || {}).value || '';
            var cidade = (form.querySelector('#id_cidade') || {}).value || '';
            var tel = (form.querySelector('#id_telefone') || {}).value || '';
            var obs = (form.querySelector('#id_observacoes') || {}).value || '';
            // Categoria é múltipla e opcional — coleta todas as marcadas.
            // Marcas de tipo (`tipos`) ou de nível (`niveis`) conforme o form da marca;
            // só um dos conjuntos existe no DOM. `intencao_voto` só existe no modo Contato.
            var tipos = Array.prototype.map.call(
                form.querySelectorAll('input[name="tipos"]:checked'), function (el) { return el.value; });
            var niveis = Array.prototype.map.call(
                form.querySelectorAll('input[name="niveis"]:checked'), function (el) { return el.value; });
            var votoEl = form.querySelector('[name="intencao_voto"]');
            var intencaoVoto = votoEl ? votoEl.value : '';
            if (!nome.trim()) { toast('Informe o nome', 'error'); return; }
            if (!cidade) { toast('Selecione a cidade', 'error'); return; }
            var rec = {
                client_id: uuid(), nome: nome.trim(), cidade_id: cidade,
                telefone: tel.trim(), tipos: tipos, niveis: niveis,
                intencao_voto: intencaoVoto, observacoes: obs.trim(), _ts: Date.now()
            };
            queue(rec).then(function () {
                form.reset();
                var citySearch = form.querySelector('#citySearch');
                if (citySearch) { citySearch.value = ''; citySearch.classList.remove('has-city'); }
                var cityHidden = form.querySelector('#id_cidade'); if (cityHidden) cityHidden.value = '';
                var n = form.querySelector('#id_nome'); if (n) n.focus();
                document.getElementById('micStatus').textContent = '';
                toast('Salvo ✓', 'success');
                updateStatus();
                sync();
            }).catch(function () { toast('Erro ao salvar localmente', 'error'); });
        });
    }

    // ---------- microfone (grava no aparelho, transcreve no servidor) ----------
    var recorder = null, chunks = [];
    function extFor(mime) {
        if (!mime) return 'm4a';
        if (mime.indexOf('mp4') > -1) return 'mp4';
        if (mime.indexOf('webm') > -1) return 'webm';
        if (mime.indexOf('ogg') > -1) return 'ogg';
        if (mime.indexOf('wav') > -1) return 'wav';
        return 'm4a';
    }
    function setMic(state) {
        var btn = document.getElementById('micBtn'), st = document.getElementById('micStatus');
        btn.classList.toggle('recording', state === 'rec');
        st.textContent = state === 'rec' ? '● Gravando… toque para parar'
            : state === 'trans' ? 'Transcrevendo…' : '';
    }
    function startRec() {
        if (!navigator.onLine) { document.getElementById('micStatus').textContent = 'Transcrição indisponível offline'; return; }
        if (!navigator.mediaDevices || !window.MediaRecorder) { document.getElementById('micStatus').textContent = 'Microfone não suportado neste aparelho'; return; }
        navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
            chunks = [];
            recorder = new MediaRecorder(stream);
            recorder.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
            recorder.onstop = function () {
                stream.getTracks().forEach(function (t) { t.stop(); });
                var blob = new Blob(chunks, { type: recorder.mimeType || 'audio/mp4' });
                uploadAudio(blob);
            };
            recorder.start();
            setMic('rec');
        }).catch(function () { document.getElementById('micStatus').textContent = 'Permissão de microfone negada'; });
    }
    function uploadAudio(blob) {
        setMic('trans');
        var fd = new FormData();
        fd.append('audio', blob, 'audio.' + extFor(blob.type));
        fetch(TRANSCRIBE_URL, { method: 'POST', headers: { 'X-CSRFToken': csrftoken() }, body: fd })
            .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
            .then(function (res) {
                setMic('idle');
                if (res.ok && res.j.text) {
                    var ta = document.getElementById('id_observacoes');
                    ta.value = (ta.value ? ta.value.trim() + ' ' : '') + res.j.text;
                    toast('Transcrição adicionada', 'success');
                } else {
                    document.getElementById('micStatus').textContent = res.j.error || 'Não foi possível transcrever';
                }
            }).catch(function () { setMic('idle'); document.getElementById('micStatus').textContent = 'Falha ao transcrever'; });
    }
    function bindMic() {
        var btn = document.getElementById('micBtn');
        if (!btn) return;
        btn.addEventListener('click', function () {
            if (recorder && recorder.state === 'recording') recorder.stop();
            else startRec();
        });
    }

    // ---------- init ----------
    function init() {
        bindForm();
        bindMic();
        updateStatus();
        window.addEventListener('online', function () { updateStatus(); sync(); });
        window.addEventListener('offline', updateStatus);
        sync();
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();

    window.LSPWA = { sync: sync, discardErros: discardErros };
})();
