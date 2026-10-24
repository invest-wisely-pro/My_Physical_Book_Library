# My Physical Book Library

A private, offline-first web app for physical book collectors: exact editions by ISBN (Google Books + Open Library), collector details (first edition, signed, dust jacket, series, translator), book-trade condition grading, reading tracking with a yearly goal, stats. No API keys, data stays on the device.

## Auto-update
- `index.html` / `sw.js`: network-first; the service worker checks for updates at every open/return to the app.
- No API keys anywhere. First-time setup of the workflow is explained in the app: ⋯ → “Indice offline: guida”.
- `.github/workflows/site.yml` (Pages source = GitHub Actions): monthly rebuilds the index from Open Library's dumps with `scripts/build-dump.mjs` (ISBN of the whole world in 512 small files + Italian search index) and publishes the site; every push to main also republishes. Index stored on branch `data-store` (history never grows).
