/* AFYA APP - Service Worker minimal : rend l'app installable (PWA).
   Strategie reseau d'abord : jamais de donnees perimees pour une app medicale. */
const CACHE = 'afya-v1';

self.addEventListener('install', (e) => {
    self.skipWaiting();
});

self.addEventListener('activate', (e) => {
    e.waitUntil(clients.claim());
});

self.addEventListener('fetch', (e) => {
    if (e.request.method !== 'GET') return;
    e.respondWith(
        fetch(e.request).catch(() =>
            caches.match(e.request).then((r) => r || new Response('Hors ligne', { status: 503 }))
        )
    );
});
