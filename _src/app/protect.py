#!/usr/bin/env python3
"""Makes the password-protected preview copy of the built site.

  PREVIEW_PASSWORD=... python3 _src/app/protect.py   ->  writes ./_dist (what gets uploaded)

Every HTML page, assets/app.js and assets/data.js are encrypted with a key derived from the password.
Without PREVIEW_PASSWORD a random throw-away password is used: the site is then locked for everyone
(fail closed) until the secret is set. Needs: pip install cryptography.
"""
import base64, hashlib, json, os, re, secrets, shutil, sys
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "_src" / "app"; DIST = ROOT / "_dist"; ITER = 310000
pw = os.environ.get("PREVIEW_PASSWORD", "")
locked_out = not pw
if locked_out: pw = secrets.token_urlsafe(32); print("PREVIEW_PASSWORD is not set: the preview is locked for everyone until it is.")
salt = secrets.token_bytes(16)
key = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, ITER, 32); aes = AESGCM(key)
def enc(text): iv = secrets.token_bytes(12); return base64.b64encode(iv + aes.encrypt(iv, text.encode("utf-8"), None)).decode()

if DIST.exists(): shutil.rmtree(DIST)
SKIP_DIRS = {".git", ".github", "_src", "_dist", "node_modules"}; SKIP_FILES = {"README.md", "CLAUDE.md", ".gitignore", "sitemap.xml"}
ver = re.search(r"app\.css\?v=([0-9a-f]+)", (ROOT / "index.html").read_text(encoding="utf-8")).group(1)
GATE_CSS = """html,body{margin:0;background:#000;color:#fff;font:16px/1.6 "Arial Nova","Helvetica Neue",Helvetica,Arial,sans-serif}
.gate{min-height:100vh;display:grid;align-content:center;justify-items:start;gap:14px;max-width:420px;margin:0 auto;padding:32px 24px;box-sizing:border-box}
.gate img{height:22px;filter:invert(1) brightness(1.6);margin-bottom:18px}.gate p{margin:0;color:#a9b0ba}
.gate form{display:grid;gap:10px;width:100%;margin-top:8px}.gate label{font-size:.84rem;color:#a9b0ba}
.gate input{background:#000;border:1px solid #3a424d;border-radius:8px;color:#fff;padding:12px;font:inherit}.gate input:focus{outline:none;border-color:#6d74ff;box-shadow:0 0 0 4px rgba(109,116,255,.2)}
.gate .btn{justify-self:start;margin-top:6px}.gate .err{color:#e85d4d;font-size:.9rem;min-height:1.4em}"""
n = 0
for f in ROOT.rglob("*"):
    rel = f.relative_to(ROOT)
    if not f.is_file() or rel.parts[0] in SKIP_DIRS or rel.name in SKIP_FILES: continue
    out = DIST / rel; out.parent.mkdir(parents=True, exist_ok=True)
    if rel.suffix == ".html":
        h = f.read_text(encoding="utf-8")
        lang = re.search(r'<html lang="([a-z]+)"', h).group(1); title = re.search(r"<title>(.*?)</title>", h, re.S).group(1)
        body = h[h.index("<body>") + 6:h.index('<script src="/assets/data.js')]
        payload = enc(json.dumps({"title": title, "body": body}, ensure_ascii=False))
        gate = {"salt": base64.b64encode(salt).decode(), "iter": ITER, "v": ver}
        out.write_text(f"""<!DOCTYPE html>
<html lang="{lang}" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EVChargeking · preview</title>
<meta name="robots" content="noindex, nofollow">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/assets/app.css?v={ver}">
<style>{GATE_CSS}</style>
</head>
<body>
<script type="application/octet-stream" id="gate-data">{payload}</script>
<script>window.__GATE={json.dumps(gate)};</script>
<script src="/assets/gate.js?v={ver}"></script>
</body>
</html>
""", encoding="utf-8"); n += 1
    elif str(rel) in ("assets/app.js", "assets/data.js"):
        (out.parent / (rel.name + ".enc")).write_text(enc(f.read_text(encoding="utf-8")), encoding="utf-8")
    else:
        shutil.copy(f, out)
shutil.copy(SRC / "gate.js", DIST / "assets" / "gate.js")
(DIST / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
print(f"protected {n} pages -> {DIST}" + (" (LOCKED: no password set)" if locked_out else ""))
