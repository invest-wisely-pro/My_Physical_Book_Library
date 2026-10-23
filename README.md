# My Physical Book Library

A private, offline-first web app for physical book collectors: exact editions by ISBN (Google Books + Open Library), collector details (first edition, signed, dust jacket, series, translator), book-trade condition grading, reading tracking with a yearly goal, stats. No API keys, data stays on the device.

## Auto-update
- `index.html` / `sw.js`: network-first; the service worker checks for updates at every open/return to the app.
- `.github/workflows/update-index.yml` runs monthly (and on demand) and rebuilds `data/books-index.json` (ISBN, title, authors of recent and past books, Italian + English, cumulative) with `scripts/build-index.mjs`; it also bumps the service-worker version so installed apps update.
- No API keys anywhere. First-time setup of the workflow is explained in the app: ⋯ → “Indice offline: guida”.
