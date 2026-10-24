// Legge i dump mensili di Open Library (in streaming) e scrive:
//  data/s/N.json.gz  (512 file: ogni ISBN-13 cade in uno solo, N = cifre 4-12 dell'ISBN % 512) -> ISBN di tutto il mondo
//  data/it-search.json.gz  edizioni italiane per ricerca offline di titolo/autore
//  data/meta.json
// Riga indice: [isbn13, titolo, autori "A | B", anno, lingua(it|en|...)]. Node 20+, avviare con --max-old-space-size=6000.
import { createWriteStream, mkdirSync, writeFileSync } from 'node:fs';
import { Readable } from 'node:stream';
import { createGunzip, gzipSync } from 'node:zlib';
import { createInterface } from 'node:readline';
const BASE = 'https://openlibrary.org/data/', SHARDS = 512, MAX_INTL = +process.env.MAX_INTL || 3000000, MAX_IT_SEARCH = 300000;
const UA = { 'User-Agent': 'MyPhysicalBookLibrary-indexer/2.0 (GitHub Actions; personal library app)' };
const L = { ita: 'it', eng: 'en', fre: 'fr', fra: 'fr', ger: 'de', deu: 'de', spa: 'es', por: 'pt', lat: 'la', rus: 'ru', jpn: 'ja', dut: 'nl', swe: 'sv', gre: 'el' };
function ok13(i){ if(!/^97[89]\d{10}$/.test(i)) return false; let s = 0; for(let k = 0; k < 12; k++) s += +i[k] * (k % 2 ? 3 : 1); return (10 - s % 10) % 10 === +i[12]; }
function to13(raw){ const d = String(raw || '').replace(/[^0-9Xx]/g, '').toUpperCase();
  if(d.length === 13) return ok13(d) ? d : '';
  if(d.length === 10 && /^\d{9}[\dX]$/.test(d)){ const b = '978' + d.slice(0, 9); let s = 0; for(let k = 0; k < 12; k++) s += +b[k] * (k % 2 ? 3 : 1); return b + ((10 - s % 10) % 10); } return ''; }
async function* lines(name){
  const r = await fetch(BASE + name, { headers: UA, redirect: 'follow' }); if(!r.ok) throw new Error(name + ' http ' + r.status);
  const rl = createInterface({ input: Readable.fromWeb(r.body).pipe(createGunzip()), crlfDelay: Infinity });
  for await (const l of rl) yield l;
}
// 1) autori: chiave -> nome
const authors = new Map(); let n = 0;
for await (const l of lines('ol_dump_authors_latest.txt.gz')){
  const t = l.split('\t'); if(t.length < 5) continue; const m = t[4].match(/"name": ?"((?:[^"\\]|\\.)*)"/); if(!m) continue;
  try{ authors.set(t[1].slice(9), JSON.parse('"' + m[1] + '"').slice(0, 60)); }catch(e){} if(++n % 1e6 === 0) console.log('autori', n);
}
console.log('autori totali', authors.size);
// 2) edizioni
const shards = Array.from({ length: SHARDS }, () => new Map()), it = new Map(); let seen = 0, intl = 0, itn = 0;
for await (const l of lines('ol_dump_editions_latest.txt.gz')){
  if(++seen % 2e6 === 0) console.log('edizioni', seen, 'it', itn, 'estere', intl);
  if(!l.includes('"isbn_13"') && !l.includes('"isbn_10"')) continue;
  const t = l.split('\t'); let j; try{ j = JSON.parse(t[4]); }catch(e){ continue; }
  const title = j.title && String(j.title).trim(); if(!title) continue;
  const isbn = to13((j.isbn_13 || [])[0] || (j.isbn_10 || [])[0]); if(!isbn) continue;
  const lang = L[String(((j.languages || [])[0] || {}).key || '').slice(11)] || '';
  const au = (j.authors || []).map(a => authors.get(String(a.key || '').slice(9))).filter(Boolean).slice(0, 3).join(' | ');
  const year = (String(j.publish_date || '').match(/\d{4}/) || [''])[0];
  const row = [isbn, (j.subtitle ? title + ': ' + j.subtitle : title).slice(0, 140), au, year, lang];
  const s = shards[parseInt(isbn.slice(3, 12), 10) % SHARDS];
  if(lang === 'it'){ if(!s.has(isbn)) itn++; s.set(isbn, row); if(au && it.size < 1e7) it.set(isbn, row); }
  else if(intl < MAX_INTL && !s.has(isbn)){ s.set(isbn, row); intl++; }   // estere: tutte finché c'è spazio (priorità a quelle con autore)
}
mkdirSync('data/s', { recursive: true });
let total = 0;
shards.forEach((m, i) => { const a = [...m.values()]; total += a.length; writeFileSync(`data/s/${i}.json.gz`, gzipSync(JSON.stringify(a), { level: 9 })); });
const itl = [...it.values()].sort((a, b) => (b[3] || 0) - (a[3] || 0)).slice(0, MAX_IT_SEARCH);   // più recenti per prime
writeFileSync('data/it-search.json.gz', gzipSync(JSON.stringify(itl), { level: 9 }));
writeFileSync('data/meta.json', JSON.stringify({ v: 2, built: new Date().toISOString(), n: total, it: itn, itSearch: itl.length, shards: SHARDS }));
console.log('Fatto: totale', total, 'italiane', itn, 'ricerca it', itl.length);
