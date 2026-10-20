# FTD — Forsaken To Decay

Waitlist site and Drop 01 product pages for FTD. It lives in this folder on its own and
shares nothing with TurnaroundIQ except the server it can be deployed to.

- **Frontend:** Vite + React + React Router, plain CSS with design tokens (`src/styles/tokens.css`).
- **Waitlist API:** a small FastAPI service (`server/waitlist_api.py`). It stores signups in SQLite and
  can also sync them to a Resend audience.
- **Artwork:** every image in `public/art/` comes from the scripts in `scripts/`. Nothing is stock or traced from
  third-party posters. The FTD wordmark is a vector trace of the supplied logo (`art/ftd-logo-source.jpg`).

## Pages

| Route | What it is |
| --- | --- |
| `/` | Hero, waitlist, the ruin and About statement, Drop 01 preview |
| `/shop` | Drop 01 grid (four pieces) |
| `/shop/crossbone-zip-hoodie` | Full product page: gallery, sizes, size guide, notify-me, campaign, other pieces |
| `/shop/:slug` | The same template for the pants and both tees |

## Run it locally

```bash
cd ftd
npm install
pip install fastapi uvicorn requests
npm run api      # waitlist API on 127.0.0.1:8090
npm run dev      # site on http://localhost:5173 (proxies /api to the API)
```

Signups go to `server/ftd_waitlist.db`. Check them with:

```bash
python3 server/waitlist_api.py count
python3 server/waitlist_api.py export > signups.csv
```

## How the waitlist works

- `POST /api/waitlist` with `{ email, source, product?, size? }`.
- The address is validated, then written to SQLite. Matching ignores case, so a repeat signup gets
  "Already on the list" and isn't stored twice.
- The browser shows success **only** after the API returns `{ ok: true }`. A network failure, a 4xx/5xx
  response or a proxy error page shows an error saying the email was not saved.
- Notify-me on a product page posts the product slug and chosen size. They are stored in
  `waitlist_interest`, so you can see who wants which size.
- Spam protection: a hidden honeypot field (bots get a fake success and nothing is stored), a limit of
  8 attempts per IP per 10 minutes, and an optional origin allow-list.
- If Resend is configured, each new signup is also added to a Resend audience in the background. If that
  sync fails, the signup is still safe in SQLite. Retry the queued ones with
  `python3 server/waitlist_api.py sync`.

### Environment variables

Set these in `/etc/ftd.env` on the server. Locally, copy `deploy/ftd.env.example` to `server/.env`.
None of them are read by the browser.

| Variable | Required | Meaning |
| --- | --- | --- |
| `FTD_WAITLIST_DB` | no | SQLite path. Default `server/ftd_waitlist.db`. On the server use `/var/lib/ftd/ftd_waitlist.db` and back it up. |
| `RESEND_API_KEY` | no | Resend API key with permission to manage contacts. |
| `RESEND_AUDIENCE_ID` | no | The Resend audience to add signups to. Sync is off unless both Resend values are set. |
| `FTD_ALLOWED_ORIGINS` | no | Comma-separated origins allowed to POST, e.g. `https://ftd.example.com`. |
| `VITE_WAITLIST_ENDPOINT` | no | Build-time only. Use it if the API is served from somewhere other than `/api/waitlist`. |

**Resend setup:** create an audience in Resend → copy its ID → create an API key → put both in
`/etc/ftd.env` → `systemctl restart ftd-waitlist`. `GET /api/health` reports `"resend": true` once both
are set.

## Deploy (same VPS pattern as TurnaroundIQ)

One-time setup:

1. Point a DNS record (e.g. `ftd.yourdomain.com`) at the VPS.
2. Put your hostname into `ftd/deploy/Caddyfile.ftd` and add the block to `/etc/caddy/Caddyfile`. To keep it
   separate, add `import /root/TurnaroundIQ/ftd/deploy/Caddyfile.ftd` to the end of that file instead. Note that
   `deploy/build_web.sh` copies the TurnaroundIQ Caddyfile over `/etc/caddy/Caddyfile`, so the `import` line
   has to live in `deploy/Caddyfile` in the repo, or it will be wiped on the next TurnaroundIQ web deploy.
3. Edit `/etc/ftd.env` after the first deploy creates it.

Every deploy, as one line:

```bash
cd ~/TurnaroundIQ && git pull -q origin main && bash ftd/deploy/deploy.sh
```

This builds the site into `/var/www/ftd`, installs and restarts the `ftd-waitlist` systemd service on
127.0.0.1:8090, checks `/api/health`, and reloads Caddy.

## Placeholder content to replace before launch

These are labelled as indicative on the site, but they are not real yet:

- **Prices** (£120 / £110 / £70 / £65). They're shown with "Indicative price — confirmed at release".
- **Details and size chart** (`src/data/products.js`, `SIZE_GUIDE`). Marked as illustrative spec and
  indicative measurements. Replace them with the real fabric, weight and grading.
- **Garment and campaign imagery.** These are shaded illustrations made by the art pipeline, not
  photographs. When you have real photography, drop it into `public/art/` with the same file names and
  proportions and nothing else needs to change:
  - Product images are 1000×1100, with 400×440 `-thumb` versions.
  - Campaign images are 900×1200.
- **Release status.** `DROP.status` in `src/data/products.js`. No checkout exists. "Notify me at drop"
  joins the waitlist with the chosen size.
- **Privacy notice.** Collecting emails in the UK falls under UK GDPR. Add a privacy page (what you store,
  why, how to unsubscribe and delete) and link it from the footer before launch.
- **Social share URLs.** `og:image` is relative. Make it absolute once the domain is known, in `index.html`.

## Regenerating the artwork

The artwork is built from code, so it can be changed and rebuilt:

```bash
pip install numpy pillow
npx playwright --version        # Chromium comes from /opt/pw-browsers or CHROMIUM_PATH
python3 scripts/build_art.py            # all images, or name some: hero-skull hoodie-front …
python3 scripts/art_textures.py         # grain + ink-dropout mask
node scripts/og.mjs                     # share card
node scripts/trace-logo.mjs             # re-trace the wordmark (needs art/_logo_bw.png)
```

- `art_hero.py`: skull, halo, shoulders.
- `art_garments.py`: the hoodie, pants and tees, and the crossbone motif.
- `art_scenes.py`: the cathedral and the campaign panels.

Each image is drawn as greyscale SVG, rendered by Chromium, then given a screen-print finish in `art_lib.py`.

## QA scripts

With the dev server and API running:

```bash
node scripts/shoot.mjs /tmp/shots / /shop /shop/crossbone-zip-hoodie   # desktop + mobile screenshots, overflow check
node scripts/qa-flows.mjs /tmp/shots                                    # waitlist, gallery, sizes, size guide, notify, menu
```
