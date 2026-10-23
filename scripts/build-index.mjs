// Costruisce data/books-index.json: [isbn13, titolo, autori ("A | B"), anno, lingua]. Node 20+, nessuna dipendenza.
// Ogni esecuzione: (1) rinfresca le uscite recenti (ultimi 3 anni), (2) scava nel passato di qualche anno (cursore salvato nel file),
// (3) UNISCE al file esistente, così l'indice cresce e non perde nulla.
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
const OUT = 'data/books-index.json', LANGS = { ita: 'it', eng: 'en' }, YEAR = new Date().getFullYear();
const RECENT = 3, BACK_PER_RUN = 6, PAGES_RECENT = 5, PAGES_PAST = 3, MAX = 60000, OLDEST = 1900;
const UA = 'MyPhysicalBookLibrary-indexer/1.0 (GitHub Actions; personal library app)';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const digits = s => String(s || '').replace(/[^0-9X]/gi, '').toUpperCase();
const ok13 = i => { if(!/^97[89]\d{10}$/.test(i)) return false; let s = 0; for(let k = 0; k < 12; k++) s += +i[k] * (k % 2 ? 3 : 1); return (10 - s % 10) % 10 === +i[12]; };
function to13(raw){ const d = digits(raw); if(d.length === 13 && ok13(d)) return d;
  if(d.length === 10 && /^\d{9}[\dX]$/.test(d)){ const b = '978' + d.slice(0, 9); let s = 0; for(let k = 0; k < 12; k++) s += +b[k] * (k % 2 ? 3 : 1); const r = b + ((10 - s % 10) % 10); return ok13(r) ? r : ''; } return ''; }
async function get(url){ for(let t = 0; t < 3; t++){ try{ const r = await fetch(url, { headers: { 'User-Agent': UA, Accept: 'application/json' } });
  if(r.ok) return await r.json(); if(r.status === 429 || r.status >= 500){ await sleep(5000 * (t + 1)); continue; } return null; }catch(e){ await sleep(3000); } } return null; }
const db = existsSync(OUT) ? JSON.parse(readFileSync(OUT, 'utf8')) : { v: 1, b: [], cursor: {} };
const map = new Map(db.b.map(x => [x[0], x])); db.cursor ||= {};
let added = 0;
async function harvest(ol, lc, year, sort, pages){
  for(let page = 1; page <= pages; page++){
    const q = encodeURIComponent(`language:${ol} first_publish_year:${year}`);
    const j = await get(`https://openlibrary.org/search.json?q=${q}&sort=${sort}&limit=100&page=${page}&fields=key,title,author_name,first_publish_year,isbn,editions,editions.title,editions.isbn,editions.language`);
    await sleep(1200);
    if(!j || !j.docs || !j.docs.length) break;
    for(const d of j.docs){
      const eds = (d.editions && d.editions.docs) || [];
      const cand = eds.length ? eds.map(e => ({ t: e.title || d.title, isbn: e.isbn || [] })) : [{ t: d.title, isbn: (d.isbn || []).slice(0, 3) }];
      for(const c of cand) for(const raw of c.isbn.slice(0, 4)){
        const i = to13(raw); if(!i || map.has(i) || !c.t) continue;
        map.set(i, [i, String(c.t).slice(0, 140), (d.author_name || []).slice(0, 3).join(' | '), String(d.first_publish_year || ''), lc]); added++;
      }
    }
    if(j.docs.length < 100) break;
  }
}
for(const [ol, lc] of Object.entries(LANGS)){
  for(let y = YEAR; y > YEAR - RECENT; y--) await harvest(ol, lc, y, 'new', PAGES_RECENT);
  let y = db.cursor[lc] || YEAR - RECENT;
  for(let n = 0; n < BACK_PER_RUN && y >= OLDEST; n++, y--) await harvest(ol, lc, y, 'editions', PAGES_PAST);
  db.cursor[lc] = y < OLDEST ? YEAR - RECENT : y;   // finito il passato, ricomincia: i dati si rinfrescano
}
let list = [...map.values()]; if(list.length > MAX) list = list.slice(0, MAX);
db.b = list; db.n = list.length; db.built = new Date().toISOString();
writeFileSync(OUT, JSON.stringify(db));
// nuova VERSION del service worker => le app installate vedono l'aggiornamento
const d = new Date().toISOString().slice(0, 10);
writeFileSync('sw.js', readFileSync('sw.js', 'utf8').replace(/const VERSION = '[^']*'/, `const VERSION = 'mpmlb-${d}'`));
console.log(`Aggiunti ${added} ISBN, totale ${list.length}`);
