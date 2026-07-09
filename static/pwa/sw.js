/* Service Worker — app-shell cacheado p/ funcionar offline.
   Estratégia: navegação/estáticos = cache-first com revalidação em background;
   POST e APIs = sempre rede (a fila offline é tratada no app.js via IndexedDB). */
const CACHE = 'crm-pwa-v14';
const SHELL = [
    '/app/',
    '/app/apoiador/novo/',
    '/app/mobilizacao/novo/',
    '/app/login/',
    '/static/pwa/app.js',
    '/static/pwa/app_voluntario.js',
    '/static/pwa/manifest.json',
    '/static/pwa/icon-192.png',
    '/static/pwa/icon-512.png',
];

self.addEventListener('install', event => {
    event.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).catch(() => {}));
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    );
    self.clients.claim();
});

self.addEventListener('fetch', event => {
    const req = event.request;
    if (req.method !== 'GET') return;                       // POST/sync/transcrição → rede (app.js cuida)
    const url = new URL(req.url);
    if (url.pathname.indexOf('/app/api/') === 0) return;    // APIs nunca do cache

    // cache-first com revalidação em background (stale-while-revalidate)
    event.respondWith(
        caches.match(req).then(cached => {
            const network = fetch(req).then(resp => {
                if (resp && resp.status === 200 && resp.type === 'basic') {
                    const clone = resp.clone();
                    caches.open(CACHE).then(c => c.put(req, clone));
                }
                return resp;
            }).catch(() => cached);
            return cached || network;
        })
    );
});
