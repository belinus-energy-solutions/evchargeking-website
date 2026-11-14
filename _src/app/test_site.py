"""Smoke test of the built site. Run after build.py:  python3 -m http.server 8766 &  then  python3 _src/app/test_site.py"""
import asyncio
from playwright.async_api import async_playwright
B="http://127.0.0.1:8766"
async def main():
  async with async_playwright() as p:
    b=await p.chromium.launch(executable_path="/usr/bin/google-chrome",args=["--no-sandbox","--no-proxy-server"])
    ctx=await b.new_context(viewport={"width":1320,"height":900},locale="nl-BE",timezone_id="Europe/Brussels")
    pg=await ctx.new_page(); errs=[]; pg.on("pageerror",lambda e:errs.append(str(e))); pg.on("requestfailed",lambda r:errs.append("RF "+r.url))
    await pg.goto(B+"/"); await pg.wait_for_timeout(600); print("root ->",pg.url)
    await pg.click("[data-act=ck-reject]")
    await pg.click("text=Naar de shop"); await pg.wait_for_timeout(300); print(pg.url, await pg.title())
    await pg.click("#v-shop .card >> nth=1"); await pg.wait_for_timeout(300); print(pg.url, "|", await pg.title())
    await pg.click("#pAdd"); await pg.wait_for_timeout(300); print("cart", await pg.inner_text("#cartN"))
    await pg.click("#closeCart"); await pg.go_back(); await pg.wait_for_timeout(300); print("back", pg.url)
    await pg.click("#regionBtn"); await pg.wait_for_timeout(300); await pg.click("button[data-sl=fr]"); await pg.wait_for_timeout(300); print("fr", pg.url, await pg.title())
    await pg.click("#regionBtn"); await pg.wait_for_timeout(300); await pg.click("button[data-sl=de]"); await pg.wait_for_timeout(300); print("de", pg.url, (await pg.inner_text("#regionBtn")).replace("\n"," "))
    await pg.goto(B+"/nl/p/tesla-laadkabel-driefasig-32a-22kw-60/"); await pg.wait_for_timeout(400); print("deep", pg.url, await pg.inner_text("#v-product h1"), "| lang", await pg.evaluate("S.lang"))
    await pg.goto(B+"/en/checkout/"); await pg.wait_for_timeout(400); print("checkout", (await pg.inner_text("#v-checkout"))[:60].replace("\n"," "))
    await pg.goto(B+"/#p-176"); await pg.wait_for_timeout(400); print("old hash ->", pg.url)
    await pg.click("#menuBtn"); await pg.wait_for_timeout(300); await pg.click("#menuNav a >> nth=3"); await pg.wait_for_timeout(300); print("menu ->", pg.url, "| panels closed:", await pg.evaluate("document.body.className")=="")
    for w in (1920,768,390,320):
      m=await ctx.new_page(); await m.set_viewport_size({"width":w,"height":800})
      for h in ["/nl/","/nl/shop/","/fr/p/cable-de-recharge-tesla-triphase-32a-22kw-60/","/en/cable-finder/","/en/etappro/","/en/support/","/en/checkout/","/en/account/"]:
        await m.goto(B+h); await m.wait_for_timeout(150)
        sw=await m.evaluate("document.documentElement.scrollWidth")
        if sw>w: print("OVERFLOW",w,h,sw)
      if w==390: await m.goto(B+"/nl/"); await m.wait_for_timeout(300); await m.screenshot(path="/tmp/site_m.png")
      await m.close()
    await pg.goto(B+"/nl/"); await pg.wait_for_timeout(500); await pg.screenshot(path="/tmp/site_d.png")
    print("errors",errs[:6]); await b.close()
asyncio.run(main())
