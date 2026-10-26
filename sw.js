/* My Physical Book Library — service worker
   App: rete prima, copia salvata se offline. Copertine (Open Library, Google Books): conservate dopo la prima visione. */
const VERSION = 'mpmlb-2026-10-26';
const CORE = ['./', 'index.html', 'manifest.webmanifest', 'icons/icon-192.png', 'icons/icon-512.png', 'icons/apple-touch-icon.png'];
self.addEventListener('install', e => { e.waitUntil(caches.open(VERSION).then(c => c.addAll(CORE)).then(() => self.skipWaiting())); });
self.addEventListener('activate', e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== VERSION && k !== 'covers' && k !== 'data').map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', e => {
  const req = e.request; if(req.method !== 'GET') return;
  const url = new URL(req.url);
  if(/(^|\.)(covers\.openlibrary\.org|archive\.org)$/.test(url.hostname) || (url.hostname === 'books.google.com' && url.pathname.startsWith('/books/content'))){
    e.respondWith(caches.open('covers').then(async c => { const hit = await c.match(req); if(hit) return hit; try{ const r = await fetch(req); if(r && (r.ok || r.type === 'opaque')) c.put(req, r.clone()); return r; }catch(err){ return hit || Response.error(); } }));
    return;
  }
  if(url.origin === location.origin && url.pathname.includes('/data/')){   // indice offline: subito dalla copia, aggiornato in background
    e.respondWith(caches.open('data').then(async c => { const hit = await c.match(req); const net = fetch(req).then(r => { if(r.ok) c.put(req, r.clone()); return r; }).catch(() => hit); return hit || net; }));
    return;
  }
  if(url.origin !== location.origin) return;
  if(req.mode === 'navigate' || url.pathname.endsWith('/') || url.pathname.endsWith('index.html')){
    e.respondWith(fetch(req).then(r => { const cp = r.clone(); caches.open(VERSION).then(c => c.put('index.html', cp)); return r; }).catch(() => caches.match('index.html')));
    return;
  }
  e.respondWith(caches.match(req).then(hit => hit || fetch(req)));
});
