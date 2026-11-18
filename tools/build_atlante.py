#!/usr/bin/env python3
"""
Atlante dei libri: i libri da scoprire nella scheda "Scopri" della Book Library.

Una volta alla settimana (GitHub Actions) raccoglie da Wikidata, gratis e senza chiavi:
  - le opere letterarie conosciute nel mondo (quante Wikipedia ne parlano = quanto sono note), con autore, anno,
    generi, paese, titolo italiano e voce di Wikipedia in italiano;
  - le opere italiane, anche meno note all'estero;
  - i premi: Strega, Campiello, Viareggio, Bancarella, Goncourt, Booker, Pulitzer, Hugo... (con l'anno) e i Nobel degli autori;
e da Open Library la copertina e, se c'è, l'ISBN di un'edizione italiana (così "Aggiungi alla libreria" compila la scheda).

Prima su QLever (motore veloce sui dati di Wikidata), poi, se non risponde, sul servizio ufficiale di Wikidata.
Le copertine già trovate le settimane prima si riusano (file precedente), così Open Library riceve poche richieste.

Uso:
  python tools/build_atlante.py data/atlante.json.gz [--old vecchio.json.gz] [--no-covers]

Sicurezza: se Wikidata non risponde o le opere sono troppo poche, il file della settimana prima resta com'è.
"""
import concurrent.futures, datetime, gzip, json, os, re, sys, time, urllib.parse, urllib.request

UA = 'MyPhysicalBookLibrary-Atlante/1.0 (libreria personale, aggiornamento settimanale)'
ENDPOINTS = [('QLever', 'https://qlever.cs.uni-freiburg.de/api/wikidata'), ('Wikidata', 'https://query.wikidata.org/sparql')]
PFX = """PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX p: <http://www.wikidata.org/prop/>
PREFIX ps: <http://www.wikidata.org/prop/statement/>
PREFIX pq: <http://www.wikidata.org/prop/qualifier/>
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX schema: <http://schema.org/>
"""
# tipi di opera: opera letteraria, romanzo, opera scritta, libro, graphic novel, poesia, opera teatrale, ciclo di romanzi, racconto, saggio, raccolta di racconti, romanzo breve
CLASSES = 'wd:Q7725634 wd:Q8261 wd:Q47461344 wd:Q571 wd:Q725377 wd:Q5185279 wd:Q25379 wd:Q1667921 wd:Q49084 wd:Q35760 wd:Q1279564 wd:Q149537'
KIND = {'Q8261': 'romanzo', 'Q149537': 'romanzo', 'Q1667921': 'ciclo', 'Q725377': 'fumetto', 'Q5185279': 'poesia', 'Q25379': 'teatro', 'Q49084': 'racconti', 'Q1279564': 'racconti', 'Q35760': 'saggio'}
# premi (nome come su Wikidata, lingua) -> codice breve usato dall'app
AWARDS = [('S', 'Premio Strega', 'it'), ('C', 'Premio Campiello', 'it'), ('V', 'Premio Viareggio', 'it'), ('B', 'Premio Bancarella', 'it'),
          ('G', 'Prix Goncourt', 'fr'), ('K', 'Booker Prize', 'en'), ('P', 'Pulitzer Prize for Fiction', 'en'), ('H', 'Hugo Award for Best Novel', 'en'),
          ('N', 'Nebula Award for Best Novel', 'en'), ('F', 'Premio Flaiano', 'it'), ('E', 'Edgar Award for Best Novel', 'en'), ('I', 'International Booker Prize', 'en'),
          ('A', 'National Book Award for Fiction', 'en'), ('L', 'Premio Campiello Giovani', 'it')]
NOBEL = 'Q37922'
ASIA = {'Q148', 'Q17', 'Q884', 'Q668', 'Q865', 'Q423', 'Q881', 'Q843', 'Q252', 'Q836'}   # Cina, Giappone, Corea, India, Taiwan, Corea del Nord, Vietnam, Pakistan, Indonesia, Myanmar
GENRE_RULES = [('giallo', r'crime|detective|mystery|giallo|noir|police procedural|whodunit'), ('thriller', r'thriller|suspense|spy'), ('fantascienza', r'science fiction|dystopi|cyberpunk|space opera|utopi'),
               ('fantasy', r'fantasy|sword and sorcery'), ('horror', r'horror|gothic|ghost'), ('storico', r'historical'), ('avventura', r'adventure|picaresque|sea story|western'),
               ('formazione', r'bildungsroman|coming.of.age'), ('ragazzi', r"children|young adult|juvenile|fairy tale"), ('amore', r'romance|love story|romantic novel'),
               ('umorismo', r'humou?r|comic novel|satir'), ('guerra', r'war novel|war fiction|military'), ('filosofico', r'philosoph|existential|allegor'), ('biografia', r'biograph|memoir|autobiograph'),
               ('poesia', r'poetry|poem|epic'), ('teatro', r'play|drama|tragedy|comedy'), ('saggio', r'essay|non.fiction|treatise')]
MIN_SL, MIN_SL_IT, MAX_WORKS, MAX_IT = 14, 4, 4500, 1600


def ask(q, tries=3):
    errors = []
    for name, url in ENDPOINTS:
        for k in range(tries):
            try:
                enc = urllib.parse.urlencode({'query': PFX + q}); hd = {'User-Agent': UA, 'Accept': 'application/sparql-results+json'}
                if len(enc) < 7000: req = urllib.request.Request(url + '?' + enc, headers=hd)
                else: req = urllib.request.Request(url, data=enc.encode(), headers={**hd, 'Content-Type': 'application/x-www-form-urlencoded'})
                with urllib.request.urlopen(req, timeout=240) as r:
                    j = json.loads(r.read().decode('utf-8'))
                if 'results' in j: return j['results'].get('bindings', [])
                errors.append(f'{name}: risposta senza risultati')
            except Exception as e:
                errors.append(f'{name}: {e}'); time.sleep(4 * (k + 1))
    raise RuntimeError(' | '.join(errors[:2] + errors[-2:]))


qid = lambda b, k: (b.get(k, {}).get('value', '').rsplit('/', 1)[-1]) if b.get(k) else ''
val = lambda b, k: b.get(k, {}).get('value', '')


def chunks(l, n):
    for i in range(0, len(l), n): yield l[i:i + n]


def many(ids, body, sel='?w ?v', n=350, ask=ask):
    """Stessa richiesta per tanti elementi, a pezzi (VALUES)."""
    out = []
    for part in chunks(ids, n):
        q = f'SELECT {sel} WHERE {{ VALUES ?w {{ {" ".join("wd:" + x for x in part)} }} {body} }}'
        try: out += ask(q)
        except Exception as e:   # riprova a metà, poi lascia stare quel pezzo
            if len(part) > 60: out += many(part, body, sel, max(30, len(part) // 3), ask)
            else: print(f'  (un gruppo di {len(part)} non ha risposto: {str(e)[:120]})')
    return out


def build(ask=ask, cover=None, old=None, log=print):
    Y = datetime.date.today().year
    # 1) opere note nel mondo, e opere italiane (anche meno note)
    sl = {}
    for b in ask(f'SELECT ?w (MAX(?s) AS ?sl) WHERE {{ VALUES ?c {{ {CLASSES} }} ?w wdt:P31 ?c ; wdt:P50 ?a ; wikibase:sitelinks ?s . FILTER(?s >= {MIN_SL}) }} GROUP BY ?w'):
        sl[qid(b, 'w')] = int(float(val(b, 'sl') or 0))
    log(f'  opere note: {len(sl)}')
    it_cand = {}   # due richieste semplici (una sola con UNION era troppo pesante): paese Italia, oppure autore italiano
    for name, cond in (('paese Italia', '?w wdt:P495 wd:Q38 .'), ('autore italiano', '?a wdt:P27 wd:Q38 .')):
        try:
            for b in ask(f'SELECT ?w (MAX(?s) AS ?sl) WHERE {{ VALUES ?c {{ {CLASSES} }} ?w wdt:P31 ?c ; wdt:P50 ?a ; wikibase:sitelinks ?s . {cond} FILTER(?s >= {MIN_SL_IT}) }} GROUP BY ?w'):
                it_cand[qid(b, 'w')] = int(float(val(b, 'sl') or 0))
        except Exception as e: log(f'  opere italiane ({name}): {e}')
    log(f'  opere italiane: {len(it_cand)}')
    # 2) premi: si cerca il premio per nome (quello davvero usato), poi i vincitori con l'anno
    aw_ids, awards = {}, {}
    for code, name, lg in AWARDS:
        try:
            r = ask(f'SELECT ?a (COUNT(?x) AS ?n) WHERE {{ ?a rdfs:label "{name}"@{lg} . ?x wdt:P166 ?a }} GROUP BY ?a ORDER BY DESC(?n) LIMIT 1')
            if r: aw_ids[qid(r[0], 'a')] = code
        except Exception as e: log(f'  premio {name}: {e}')
    if aw_ids:
      try:
        for b in ask(f'SELECT ?w ?a ?d WHERE {{ VALUES ?a {{ {" ".join("wd:" + x for x in aw_ids)} }} ?w p:P166 ?st . ?st ps:P166 ?a . OPTIONAL {{ ?st pq:P585 ?d }} }}'):
            w, code, y = qid(b, 'w'), aw_ids.get(qid(b, 'a')), val(b, 'd')[:4]
            if w and code: awards.setdefault(w, set()).add(code + (y if re.match(r'^\d{4}$', y) else ''))
      except Exception as e: log(f'  vincitori dei premi: {e}')
    log(f'  premi trovati: {len(aw_ids)} su {len(AWARDS)}, opere premiate: {len(awards)}')
    # 3) scelta: le più note, le italiane, le premiate
    pick = sorted(sl, key=lambda w: -sl[w])[:MAX_WORKS * 2]
    its = sorted(it_cand, key=lambda w: -it_cand[w])[:MAX_IT]
    ids = list(dict.fromkeys(pick + its + list(awards)))
    allsl = {**it_cand, **sl}
    # 4) dettagli (a pezzi): autori, anno, generi, paese, tipo, titolo originale, etichette, voce italiana di Wikipedia
    D = {w: {'a': [], 'y': '', 'g': set(), 'c': set(), 'k': set(), 'lb': {}, 'o': '', 'iw': '', 'lg': set()} for w in ids}
    for b in many(ids, '?w wdt:P50 ?v', ask=ask):
        x = D.get(qid(b, 'w')); v = qid(b, 'v')
        if x is not None and v not in x['a']: x['a'].append(v)
    for b in many(ids, '?w wdt:P577 ?v', ask=ask):
        x = D.get(qid(b, 'w')); y = val(b, 'v')[:4]
        if x is not None and re.match(r'^-?\d{3,4}$', y) and (not x['y'] or int(y) < int(x['y'])): x['y'] = y
    for prop, key in (('P136', 'g'), ('P495', 'c'), ('P31', 'k'), ('P407', 'lg')):
        for b in many(ids, f'?w wdt:{prop} ?v', ask=ask):
            x = D.get(qid(b, 'w'))
            if x is not None: x[key].add(qid(b, 'v'))
    for b in many(ids, '?w rdfs:label ?v . FILTER(LANG(?v) = "it" || LANG(?v) = "en")', sel='?w ?v (LANG(?v) AS ?l)', ask=ask):
        x = D.get(qid(b, 'w'))
        if x is not None: x['lb'][val(b, 'l')] = val(b, 'v')
    for b in many(ids, '?w wdt:P1476 ?v', ask=ask):
        x = D.get(qid(b, 'w'))
        if x is not None and not x['o']: x['o'] = val(b, 'v')
    for b in many(ids, '?p schema:about ?w ; schema:isPartOf <https://it.wikipedia.org/> ; schema:name ?v', ask=ask):
        x = D.get(qid(b, 'w'))
        if x is not None: x['iw'] = val(b, 'v')
    # 5) autori: nome, cittadinanza, nascita, ritratto, Nobel
    aus = list(dict.fromkeys(a for x in D.values() for a in x['a']))
    A = {a: {'lb': {}, 'it': False, 'b': '', 'img': '', 'nob': '', 'cz': set()} for a in aus}
    for b in many(aus, '?w rdfs:label ?v . FILTER(LANG(?v) = "it" || LANG(?v) = "en")', sel='?w ?v (LANG(?v) AS ?l)', ask=ask):
        x = A.get(qid(b, 'w'))
        if x is not None: x['lb'][val(b, 'l')] = val(b, 'v')
    for b in many(aus, '?w wdt:P27 ?v', ask=ask):
        x = A.get(qid(b, 'w'))
        if x is not None: x['cz'].add(qid(b, 'v'))
    for b in many(aus, '?w wdt:P569 ?v', ask=ask):
        x = A.get(qid(b, 'w'))
        if x is not None and not x['b']: x['b'] = val(b, 'v')[:4]
    for b in many(aus, '?w wdt:P18 ?v', ask=ask):
        x = A.get(qid(b, 'w'))
        if x is not None and not x['img']: x['img'] = urllib.parse.unquote(val(b, 'v').rsplit('/', 1)[-1])
    for b in many(aus, f'?w p:P166 ?st . ?st ps:P166 wd:{NOBEL} . OPTIONAL {{ ?st pq:P585 ?v }}', ask=ask):
        x = A.get(qid(b, 'w'))
        if x is not None: x['nob'] = val(b, 'v')[:4] or '1'
    for a in A.values(): a['it'] = 'Q38' in a['cz']
    # generi: etichette inglesi -> famiglie
    gids = list(dict.fromkeys(g for x in D.values() for g in x['g']))
    glab = {}
    for b in many(gids, '?w rdfs:label ?v . FILTER(LANG(?v) = "en")', ask=ask): glab[qid(b, 'w')] = val(b, 'v').lower()
    def fam(x):
        out = []
        txt = ' | '.join(glab.get(g, '') for g in x['g'])
        for code, rx in GENRE_RULES:
            if re.search(rx, txt) and code not in out: out.append(code)
        for k in x['k']:
            kk = KIND.get(k)
            if kk in ('poesia', 'teatro', 'saggio', 'fumetto') and kk not in out: out.append(kk)
        return out[:4]
    # 6) filtro e punteggio: famosi solo in un paese asiatico no; italiani sì anche se poco noti
    works = []
    for w in ids:
        x = D[w]
        if not x['a'] or not (x['lb'].get('it') or x['lb'].get('en')): continue
        s = allsl.get(w, 0); aw = sorted(awards.get(w, ()))
        ita = 'Q38' in x['c'] or ('Q652' in x['lg'] and any(A.get(a, {}).get('it') for a in x['a'])) or (not x['c'] and all(A.get(a, {}).get('it') for a in x['a']))
        if x['c'] & ASIA and not ita and s < 45 and not any(a[0] in 'KIPGHNA' for a in aw): continue
        if re.match(r'^Q\d+$', x['lb'].get('it', '')) : continue
        title = x['iw'] and re.sub(r'\s*\((romanzo|libro|opera|racconto|poema|raccolta|saggio|dramma|commedia|fumetto)[^)]*\)\s*$', '', x['iw']) or x['lb'].get('it') or x['lb'].get('en')
        kind = next((KIND[k] for k in x['k'] if k in KIND), '')
        works.append({'q': w, 't': title, 'o': x['o'] if x['o'] and x['o'] != title else '', 'a': x['a'][:3], 'y': x['y'], 's': s, 'it': ita, 'g': fam(x), 'k': kind, 'aw': aw, 'iw': x['iw']})
    works.sort(key=lambda r: -(r['s'] + 12 * len(r['aw'])))
    log(f'  opere tenute: {len(works)} (italiane {sum(1 for r in works if r["it"])})')
    # 7) copertine e ISBN italiano (Open Library), riusando quelli già trovati
    prev = {}
    if old:
        for r in old.get('w', []): prev[r[0]] = (r[9], r[10])
    if cover:
        todo = [r for r in works if r['q'] not in prev]
        log(f'  copertine: {len(works) - len(todo)} già note, {len(todo)} da cercare')
        with concurrent.futures.ThreadPoolExecutor(4) as ex:
            for r, res in zip(todo, ex.map(lambda r: cover(r, A), todo)): prev[r['q']] = res
    # 8) uscita compatta
    au_list = list(dict.fromkeys(a for r in works for a in r['a'] if a in A))
    ai = {a: i for i, a in enumerate(au_list)}
    def an(a): lb = A[a]['lb']; return lb.get('it') or lb.get('en') or ''
    out = {'v': 1, 'built': datetime.date.today().isoformat(), 'Y': Y, 'awards': {c: n for c, n, _ in AWARDS},
           'w': [[r['q'], r['t'], r['o'], [ai[a] for a in r['a'] if a in ai], r['y'], r['s'], 1 if r['it'] else 0, ','.join(r['g']), ','.join(r['aw']), (prev.get(r['q']) or (0, ''))[0], (prev.get(r['q']) or (0, ''))[1], r['iw'], r['k']] for r in works],
           'a': [[a, an(a), A[a]['nob'], A[a]['img'], 1 if A[a]['it'] else 0, A[a]['b']] for a in au_list]}
    return out


def ol_cover(r, A):
    """Open Library: prima un'edizione italiana (ISBN 978-88 / 979-12), poi qualsiasi edizione con copertina."""
    au = (A.get(r['a'][0], {}).get('lb', {}) or {}) if r['a'] else {}
    au = au.get('en') or au.get('it') or ''
    last = au.split(' ')[-1] if au else ''
    def get(params):
        url = 'https://openlibrary.org/search.json?' + urllib.parse.urlencode(params)
        for k in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=30) as h: return json.loads(h.read().decode('utf-8')).get('docs', [])
            except Exception: time.sleep(3 * (k + 1))
        return []
    cov, isbn = 0, ''
    for d in get({'title': r['t'], 'author': last, 'language': 'ita', 'limit': 3, 'fields': 'cover_i,isbn'}):
        i13 = next((i for i in d.get('isbn', []) if re.match(r'^97(888|912)\d{8}$', i)), '')
        if i13 and not isbn: isbn = i13
        if d.get('cover_i') and not cov: cov = d['cover_i']
    if not cov:
        for t in [x for x in (r['o'], r['t']) if x]:
            docs = get({'title': t, 'author': last, 'limit': 2, 'fields': 'cover_i'})
            cov = next((d['cover_i'] for d in docs if d.get('cover_i')), 0)
            if cov: break
    time.sleep(0.4)
    return (cov, isbn)


def main():
    args = sys.argv[1:]
    if not args: print(__doc__); sys.exit(2)
    out_path = args[0]
    old_path = args[args.index('--old') + 1] if '--old' in args else (out_path if os.path.exists(out_path) else '')
    old = None
    if old_path and os.path.exists(old_path):
        try: old = json.load(gzip.open(old_path, 'rt', encoding='utf-8'))
        except Exception: old = None
    keep = 'Il file della settimana prima resta com\'è.' if old else ''
    try:
        out = build(cover=None if '--no-covers' in args else ol_cover, old=old)
    except Exception as e:
        print(f'ATTENZIONE: Wikidata non ha risposto ({e}). {keep}'); sys.exit(0 if keep else 1)
    if len(out['w']) < 800:
        print(f'ATTENZIONE: solo {len(out["w"])} opere. {keep}'); sys.exit(0 if keep else 1)
    with gzip.open(out_path, 'wt', encoding='utf-8') as f: json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    print(f'Fatto: {len(out["w"])} opere, {len(out["a"])} autori, copertine {sum(1 for r in out["w"] if r[9])}, ISBN italiani {sum(1 for r in out["w"] if r[10])} → {out_path}')


if __name__ == '__main__':
    main()
