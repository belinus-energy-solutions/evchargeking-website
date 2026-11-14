#!/usr/bin/env python3
"""Turns the translation files i18n/<lang>.txt (one line per text: ID§translation) into assets/i18n.js.
i18n/_source_en.txt lists every ID with its English source. IDs: U: interface, C: calculator, Y: payment names,
N: product names (by Odoo id), S: short product line, A: option labels, D: product description lines,
H: home page, B: about page, E: ETAPpro page. A missing ID simply stays in English."""
import json, re
from pathlib import Path
HERE = Path(__file__).resolve().parent
def load(f): return dict(l.split("§", 1) for l in f.read_text(encoding="utf-8").splitlines() if "§" in l)
def build(root):
    src = load(HERE / "i18n" / "_source_en.txt"); out = {}
    for f in sorted((HERE / "i18n").glob("??.txt")):
        tr = load(f); lang = f.stem; unknown = [k for k in tr if k not in src]
        if unknown: raise SystemExit(f"{f.name}: unknown IDs {unknown[:5]}")
        for k, v in tr.items():      # placeholders and markers must survive translation
            for ph in re.findall(r"\{[a-z]+\}", src[k]):
                if ph not in v: raise SystemExit(f"{f.name} {k}: placeholder {ph} missing")
            for m in ("## ", "- "):
                if src[k].startswith(m) and not v.startswith(m): raise SystemExit(f"{f.name} {k}: must start with '{m}'")
            if src[k].count("|") != v.count("|"): raise SystemExit(f"{f.name} {k}: table bars differ")
        g = lambda p: {k[len(p):]: v for k, v in tr.items() if k.startswith(p)}
        home = {}
        for k, v in g("H:").items(): i, part = k.split(":"); home.setdefault(i, {})[part] = v
        out[lang] = {"ui": g("U:"), "calc": g("C:"), "pay": g("Y:"), "names": g("N:"),
                     "short": {src["S:" + k]: v for k, v in g("S:").items()}, "attrs": {src["A:" + k]: v for k, v in g("A:").items()},
                     "lines": {src["D:" + k]: v for k, v in g("D:").items()}, "home": home,
                     "about": {src["B:" + k]: v for k, v in g("B:").items()}, "etappro": {src["E:" + k]: v for k, v in g("E:").items()}}
        print(f"i18n {lang}: {len(tr)} of {len(src)} texts")
    (root / "assets" / "i18n.js").write_text("window.EVI18N=" + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    return sorted(out)
