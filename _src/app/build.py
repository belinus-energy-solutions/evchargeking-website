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
SITE = "https://evchargeking.com"
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

def head(meta, paths, lang, canonical=None):
    e = html.escape; url = SITE + (canonical or paths[lang]); img = SITE + meta["image"]
    h = [f"<title>{e(meta['title'])}</title>", f'<meta name="description" content="{e(meta["desc"])}">',
         f'<link rel="canonical" href="{url}">']
    h += [f'<link rel="alternate" hreflang="{l}" href="{SITE}{paths[l]}">' for l in LANGS]
    h.append(f'<link rel="alternate" hreflang="x-default" href="{SITE}{paths["en"]}">')
    if not LIVE or meta.get("noindex"): h.append('<meta name="robots" content="noindex, nofollow">')
    h += [f'<meta property="og:site_name" content="EVChargeking">', f'<meta property="og:type" content="{"product" if meta.get("product") else "website"}">',
          f'<meta property="og:title" content="{e(meta["title"])}">', f'<meta property="og:description" content="{e(meta["desc"])}">',
          f'<meta property="og:url" content="{url}">', f'<meta property="og:image" content="{img}">', '<meta name="theme-color" content="#000000">']
    p = meta.get("product")
    if p:
        ld = {"@context": "https://schema.org", "@type": "Product", "name": p["name"], "sku": str(p["id"]), "brand": {"@type": "Brand", "name": "EVChargeking"},
              "description": meta["desc"], "offers": {"@type": "Offer", "url": url, "priceCurrency": "EUR", "price": f'{p["price"]:.2f}',
              "availability": "https://schema.org/" + ("InStock" if p["stock"] else "BackOrder"), "seller": {"@type": "Organization", "name": "EVChargeking"}}}
        if p.get("image"): ld["image"] = SITE + p["image"]
        h.append('<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script>")
    elif meta["route"] == "home":
        ld = {"@context": "https://schema.org", "@type": "Organization", "name": "EVChargeking", "url": SITE, "logo": SITE + "/img/logo.png",
              "parentOrganization": {"@type": "Organization", "name": "Belinus", "url": "https://belinus.com"}}
        h.append('<script type="application/ld+json">' + json.dumps(ld) + "</script>")
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
                page = shell.replace("<!--HEAD-->", head(meta, paths[r], l)).replace('<html lang="en">', f'<html lang="{l}" data-theme="dark">')
                page = page[:page.index("<body>") + 6] + body + page[page.index('<script src="/assets/data.js'):]
                write(ROOT / paths[r][l].strip("/") / "index.html", page); n += 1
                if not meta.get("noindex"): sitemap.append((paths[r], l))
                if r == "home" and l == "en":
                    root_page = page.replace(f'<link rel="canonical" href="{SITE}/en/">', f'<link rel="canonical" href="{SITE}/en/">')
                    write(ROOT / "index.html", root_page)
                    write(ROOT / "404.html", page.replace("</title>", "</title>\n<meta name=\"robots\" content=\"noindex\">", 1))
        await b.close()
        if errs: print("PAGE ERRORS:", errs[:5]); sys.exit(1)
        x = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">']
        for p, l in sitemap:
            x.append(f"<url><loc>{SITE}{p[l]}</loc>" + "".join(f'<xhtml:link rel="alternate" hreflang="{k}" href="{SITE}{p[k]}"/>' for k in LANGS) + "</url>")
        x.append("</urlset>"); write(ROOT / "sitemap.xml", "\n".join(x) + "\n")
        write(ROOT / "robots.txt", (f"User-agent: *\nAllow: /\nDisallow: /*/checkout/\nDisallow: /*/order-confirmed/\nSitemap: {SITE}/sitemap.xml\n" if LIVE else "User-agent: *\nDisallow: /\n"))
        print(f"built {n} pages, version {ver}, {'LIVE' if LIVE else 'PREVIEW (noindex)'}")
asyncio.run(main()); srv.shutdown()
