# evchargeking-website (evchargeking.com)

Website and webshop for **EVChargeking, a Belinus group company**. Same stack as `belinuswebsite`:
static pages on Bunny.net (storage zone + pull zone `evchargeking-website`), deployed automatically on
every push to `main` by `.github/workflows/deploy.yml`. The first run creates the Bunny zones.

Preview address: https://evchargeking-website.b-cdn.net/ (the live evchargeking.com still runs on Odoo).

## Status (14 Nov 2026)

- [x] Site built as real pages: one address per page and per language (nl, fr, en), 195 pages
- [x] Deploy workflow, Bunny zones created by the first run
- [x] Preview build: every page tells search engines **not** to index it, `robots.txt` blocks everything
- [ ] Password lock: built (`_src/app/protect.py`, `gate.js`) but switched **off** on 14 Nov 2026 at Steve's request. Switch on with `PROTECT: "on"` in `.github/workflows/deploy.yml` plus the repository secret `PREVIEW_PASSWORD`.
- [ ] Checkout service (Supabase functions `evck-*` in project "Belinus Portal"): cart total from Odoo, VAT number check, order in Odoo, Mollie payment, automatic service-portal account
- [ ] Odoo: dedicated API user; website pricelist rule for the ETAPpro 11 end-of-year promotion; product references; Mollie journal
- [ ] Nightly catalogue sync from Odoo (products, prices, stock, photos) instead of the snapshot in `_src/app/data.js`
- [ ] Go-live: `python3 _src/app/build.py --live`, then DNS for evchargeking.com to the pull zone, SSL, Force SSL, redirects from the old Odoo addresses

Until the checkout service is live, the checkout page says ordering is not switched on and creates nothing.

## Production safety (rule set by Steve, 14 Nov 2026)

Nothing in this repository may alter EVChargeking's production set-up until Steve approves go-live:

- **DNS for evchargeking.com** stays on Odoo. No hostnames for evchargeking.com are added to the pull zone.
- **Odoo (evck.odoo.com)**: read-only. No products, prices, pricelists, orders, website or payment settings are changed.
- **Mollie**: read-only. No payments, webhooks or profile settings are created or changed.
- **Supabase "Belinus Portal"**: no functions, tables or secrets are added for the shop until agreed.
- The deploy workflow only touches the Bunny zones named `evchargeking-website`; it never edits other zones.
- The preview is not indexable and its checkout creates no orders.

## How it is built

- `_src/app/` is the source: `shell.html` (page frame), `app.css`, `app.js` (all pages and texts), `data.js` (catalogue snapshot from Odoo and evchargeking.com, 14 Nov 2026).
- `python3 _src/app/build.py` renders every page once in a headless browser and writes the static files into the repository root (`/nl/…`, `/fr/…`, `/en/…`, `/assets/`, `sitemap.xml`, `robots.txt`, `404.html`). Do not edit those by hand.
- `python3 -m http.server 8766` in the repository root, then `python3 _src/app/test_site.py`, runs a smoke test.
- `_src/` is not uploaded to the CDN.

## Design

Belinus design system (black surface, Arial Nova, Space Grotesk capitals, pill buttons) with the EVChargeking
logo and the EVChargeking blue `#080DD4` as the only accent. Belinus blue appears only in the Belinus group band
on the home page. Photos are never cropped. Fonts are self-hosted in `/fonts/` (no Google Fonts).

## Addresses

`/{lang}/` home · `/{lang}/shop/` · `/{lang}/shop/{group}/` · `/{lang}/p/{name}-{odoo id}/` · `/{lang}/cable-finder/` ·
`/{lang}/etappro/` · `/{lang}/support/` · `/{lang}/about/` · `/{lang}/account/` · `/{lang}/terms/` · `/{lang}/privacy/` ·
`/{lang}/checkout/` · `/{lang}/order-confirmed/`. The other 22 interface languages use the `/en/` addresses.
