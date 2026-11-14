#!/usr/bin/env python3
"""Builds the static EVChargeking site into the repository root.

  python3 _src/app/build.py            # preview build (search engines are told not to index)
  python3 _src/app/build.py --live     # go-live build (indexable, sitemap active)

Every page (per language: nl, fr, en) is rendered once in a headless browser and saved as its own
HTML file with its own title, description, canonical address and language alternates. The same
app.js then takes over in the visitor's browser. Needs: pip install playwright, and Chrome/Chromium.
"""
import asyncio, hashlib, html, http.server, json, os, re, shutil, socketserver, sys, threading
from pathlib import Path
from playwright.async_api import async_playwright

LIVE = "--live" in sys.argv
# Addresses in the pages (canonical, share images) must point at where the site really is.
SITE = "https://evchargeking.com" if LIVE else "https://evchargeking-website.b-cdn.net"
# Google Tag Manager container of the live shop (holds Analytics, Ads, Meta and LinkedIn tags). Go-live build only.
GTM_ID = "GTM-5G8H3GLB"
# Google Search Console: paste the "HTML tag" verification code here before go-live (optional if verified through DNS).
GSC_TOKEN = ""
LOCALE = {"nl": "nl_BE", "fr": "fr_BE", "en": "en_GB"}
ORG = {"@type": "OnlineStore", "@id": "https://evchargeking.com/#org", "name": "EVChargeking", "legalName": "Some BV", "url": "https://evchargeking.com",
       "logo": "https://evchargeking.com/share/logo.png", "email": "service@evchargeking.com", "telephone": "+32475443669", "vatID": "BE0829249337",
       "address": {"@type": "PostalAddress", "streetAddress": "Hooilaar 40", "postalCode": "2230", "addressLocality": "Herselt", "addressCountry": "BE"},
       "sameAs": ["https://www.facebook.com/evchargeking", "https://x.com/EVChargeKing", "https://www.linkedin.com/company/evchargeking", "https://www.youtube.com/@EVChargeking/videos"],
       "parentOrganization": {"@type": "Organization", "name": "Belinus", "url": "https://belinus.com"}}
SRC = Path(__file__).resolve().parent
ROOT = SRC.parent.parent
LANGS = ["nl", "fr", "en"]
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")

def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text, encoding="utf-8")

# 1. assets
(ROOT / "assets").mkdir(exist_ok=True)
ver = hashlib.sha1(b"".join((SRC / f).read_bytes() for f in ("app.js", "app.css", "data.js"))).hexdigest()[:10]
for f in ("app.js", "app.css", "data.js"): shutil.copy(SRC / f, ROOT / "assets" / f)
shell = (SRC / "shell.html").read_text(encoding="utf-8").replace("__V__", ver)

# 1b. share images: 1200x630 JPEG per product, category and a default one (what WhatsApp, Facebook, LinkedIn and X show)
from PIL import Image
def share_image(src, dest):
    W, H = 1200, 630; card = Image.new("RGB", (W, H), "#f4f5f6")
    im = Image.open(src).convert("RGB"); im.thumbnail((W - 120, H - 150), Image.LANCZOS)
    card.paste(im, ((W - im.width) // 2, 40 + (H - 150 - im.height) // 2))
    logo = Image.open(ROOT / "img" / "logo.png").convert("RGBA"); logo.thumbnail((300, 40), Image.LANCZOS)
    card.paste(logo, (60, H - 40 - logo.height), logo)
    dest.parent.mkdir(exist_ok=True); card.save(dest, "JPEG", quality=86, optimize=True, progressive=True)
def logo_png():
    logo = Image.open(ROOT / "img" / "logo.png").convert("RGBA"); logo.thumbnail((560, 120), Image.LANCZOS)
    c = Image.new("RGB", (640, 640), "white"); c.paste(logo, ((640 - logo.width) // 2, (640 - logo.height) // 2), logo); c.save(ROOT / "share" / "logo.png")
SHARE = {}
def share_for(key, webp):
    if key not in SHARE:
        f = ROOT / webp.lstrip("/")
        if not f.exists(): return SHARE.get("default")
        share_image(f, ROOT / "share" / (key + ".jpg")); SHARE[key] = "/share/" + key + ".jpg"
    return SHARE[key]
(ROOT / "share").mkdir(exist_ok=True); share_for("default", "/img/199_big.webp"); logo_png()

# 2. local server: any address without a file extension gets the empty shell, so the app can render it
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=str(ROOT), **k)
    def log_message(self, *a): pass
    def do_GET(self):
        p = self.path.split("?")[0]
        if "." in p.rsplit("/", 1)[-1]:
            try: return super().do_GET()
            except (BrokenPipeError, ConnectionResetError): return
        b = shell.replace("<!--HEAD-->", "<title>build</title>").encode()
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
socketserver.TCPServer.allow_reuse_address = True
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), H); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

def ld(obj): return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False).replace("</", "<\\/") + "</script>"

def head(meta, paths, lang, allpaths):
    e = html.escape; url = SITE + paths[lang]
    img = SITE + (share_for(meta["share"], meta["image"]) or SHARE["default"])
    h = [f"<title>{e(meta['title'])}</title>", f'<meta name="description" content="{e(meta["desc"])}">', f'<link rel="canonical" href="{url}">']
    h += [f'<link rel="alternate" hreflang="{l}" href="{SITE}{paths[l]}">' for l in LANGS]
    h.append(f'<link rel="alternate" hreflang="x-default" href="{SITE}{paths["en"]}">')
    if not LIVE or meta.get("noindex"): h.append('<meta name="robots" content="noindex, nofollow">')
    else: h.append('<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1">')
    if LIVE and GSC_TOKEN: h.append(f'<meta name="google-site-verification" content="{GSC_TOKEN}">')
    p = meta.get("product")
    h += ['<meta property="og:site_name" content="EVChargeking">', f'<meta property="og:type" content="{"product" if p else "website"}">',
          f'<meta property="og:locale" content="{LOCALE[lang]}">'] + [f'<meta property="og:locale:alternate" content="{LOCALE[l]}">' for l in LANGS if l != lang]
    h += [f'<meta property="og:title" content="{e(meta["title"])}">', f'<meta property="og:description" content="{e(meta["desc"])}">', f'<meta property="og:url" content="{url}">',
          f'<meta property="og:image" content="{img}">', '<meta property="og:image:type" content="image/jpeg">', '<meta property="og:image:width" content="1200">',
          '<meta property="og:image:height" content="630">', f'<meta property="og:image:alt" content="{e(meta["title"])}">',
          '<meta name="twitter:card" content="summary_large_image">', '<meta name="twitter:site" content="@EVChargeKing">',
          f'<meta name="twitter:title" content="{e(meta["title"])}">', f'<meta name="twitter:description" content="{e(meta["desc"])}">', f'<meta name="twitter:image" content="{img}">',
          '<meta name="theme-color" content="#000000">']
    if p:
        h += [f'<meta property="product:price:amount" content="{p["price"]:.2f}">', '<meta property="product:price:currency" content="EUR">',
              f'<meta property="product:availability" content="{"in stock" if p["stock"] else "available for order"}">', '<meta property="product:brand" content="EVChargeking">']
        offer = {"@type": "Offer", "url": url, "priceCurrency": "EUR", "price": f'{p["price"]:.2f}', "itemCondition": "https://schema.org/NewCondition",
                 "availability": "https://schema.org/" + ("InStock" if p["stock"] else "BackOrder"), "seller": {"@id": ORG["@id"]}}
        if p.get("until"): offer["priceValidUntil"] = p["until"]
        prod = {"@context": "https://schema.org", "@type": "Product", "name": p["name"], "sku": str(p["id"]), "category": p.get("group"), "description": meta["desc"],
                "brand": {"@type": "Brand", "name": "EVChargeking"}, "offers": offer}
        if p.get("images"): prod["image"] = [img] + [SITE + i for i in p["images"]]
        h.append(ld(prod))
    if meta["route"] == "home":
        h.append(ld({"@context": "https://schema.org", **ORG}))
        h.append(ld({"@context": "https://schema.org", "@type": "WebSite", "name": "EVChargeking", "url": SITE + "/", "inLanguage": lang, "publisher": {"@id": ORG["@id"]}}))
    if len(meta["crumbs"]) > 1:
        h.append(ld({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": n, "item": SITE + allpaths[r][lang]} for i, (n, r) in enumerate(meta["crumbs"])]}))
    if meta.get("list"):
        h.append(ld({"@context": "https://schema.org", "@type": "ItemList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "url": SITE + allpaths[r][lang]} for i, r in enumerate(meta["list"])]}))
    if LIVE: h.append(f'<script>window.EV_TAGS={{gtm:"{GTM_ID}"}};</script>')
    # theme before first paint, so light-theme visitors see no dark flash
    h.append('<script>try{var s=JSON.parse(localStorage.getItem("evck-shop-v3")||"{}");document.documentElement.setAttribute("data-theme",s.theme==="light"?"light":"dark")}catch(e){}</script>')
    return "\n".join(h)

async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(executable_path=CHROME, args=["--no-sandbox", "--no-proxy-server"])
        ctx = await b.new_context(viewport={"width": 1280, "height": 900}, locale="en-GB")
        await ctx.add_init_script("window.__PRERENDER=1;")
        pg = await ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        base = f"http://127.0.0.1:{port}"
        await pg.goto(base + "/en/"); await pg.wait_for_function("window.__meta")
        routes = await pg.evaluate('["home","shop",...GROUPS.map(g=>"cat-"+g),...PR.map(p=>"p-"+p.id),...Object.keys(SEG)]')
        paths = {r: {l: await pg.evaluate("([r,l])=>pathOf(r,l)", [r, l]) for l in LANGS} for r in routes}
        sitemap = []; n = 0
        for r in routes:
            for l in LANGS:
                await pg.goto(base + paths[r][l]); await pg.wait_for_function("window.__meta&&window.__meta.route===" + json.dumps(r))
                meta = await pg.evaluate("window.__meta")
                body = await pg.evaluate("""()=>{document.querySelectorAll('img').forEach(i=>i.removeAttribute('data-x'));
                    const c=document.body.cloneNode(true); c.querySelectorAll('script').forEach(s=>s.remove()); c.className=''; return c.innerHTML;}""")
                page = shell.replace("<!--HEAD-->", head(meta, paths[r], l, paths)).replace('<html lang="en">', f'<html lang="{l}" data-theme="dark">')
                page = page[:page.index("<body>") + 6] + body + page[page.index('<script src="/assets/data.js'):]
                write(ROOT / paths[r][l].strip("/") / "index.html", page); n += 1
                if not meta.get("noindex"): sitemap.append((paths[r], l, [SITE + i for i in (meta["product"] or {}).get("images", [])]))
                if r == "home" and l == "en":
                    root_page = page.replace(f'<link rel="canonical" href="{SITE}/en/">', f'<link rel="canonical" href="{SITE}/en/">')
                    write(ROOT / "index.html", root_page)
                    write(ROOT / "404.html", page.replace("</title>", "</title>\n<meta name=\"robots\" content=\"noindex\">", 1))
        await b.close()
        if errs: print("PAGE ERRORS:", errs[:5]); sys.exit(1)
        import datetime; today = datetime.date.today().isoformat()
        x = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">']
        for p, l, imgs in sitemap:
            x.append(f"<url><loc>{SITE}{p[l]}</loc><lastmod>{today}</lastmod>" + "".join(f'<xhtml:link rel="alternate" hreflang="{k}" href="{SITE}{p[k]}"/>' for k in LANGS)
                     + f'<xhtml:link rel="alternate" hreflang="x-default" href="{SITE}{p["en"]}"/>' + "".join(f"<image:image><image:loc>{i}</image:loc></image:image>" for i in imgs) + "</url>")
        x.append("</urlset>"); write(ROOT / "sitemap.xml", "\n".join(x) + "\n")
        write(ROOT / "robots.txt", (f"User-agent: *\nAllow: /\nDisallow: /*/checkout/\nDisallow: /*/order-confirmed/\nSitemap: {SITE}/sitemap.xml\n" if LIVE else "User-agent: *\nDisallow: /\n"))
        print(f"built {n} pages, version {ver}, {'LIVE' if LIVE else 'PREVIEW (noindex)'}")
asyncio.run(main()); srv.shutdown()
