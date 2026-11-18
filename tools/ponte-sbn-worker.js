// Ponte per le biblioteche italiane (OPAC SBN) — Cloudflare Worker gratuito, nessuna chiave.
// Inoltra SOLO le richieste al catalogo SBN e aggiunge il permesso CORS, così l'app dei libri può leggerlo.
export default {
  async fetch(request) {
    const cors = { 'access-control-allow-origin': '*', 'access-control-allow-methods': 'GET, OPTIONS' };
    if (request.method === 'OPTIONS') return new Response(null, { headers: cors });
    const target = new URL(request.url).searchParams.get('url') || '';
    if (!/^https:\/\/opac\.sbn\.it\/opacmobilegw\/(search|full)\.json\?/.test(target)) return new Response('Solo richieste al catalogo SBN', { status: 400, headers: cors });
    try {
      const r = await fetch(target, { headers: { Accept: 'application/json', 'User-Agent': 'MyPhysicalBookLibrary/1.0 (uso personale)' }, cf: { cacheTtl: 86400, cacheEverything: true } });
      return new Response(r.body, { status: r.status, headers: { ...cors, 'content-type': 'application/json; charset=utf-8', 'cache-control': 'public, max-age=86400' } });
    } catch (e) {
      return new Response(JSON.stringify({ error: 'sbn' }), { status: 502, headers: { ...cors, 'content-type': 'application/json' } });
    }
  }
};
