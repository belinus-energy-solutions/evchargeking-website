#!/usr/bin/env python3
"""Checks that every legal translation lines up with the Dutch original, line for line."""
import re, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
def nl_lines(which):
    L = (HERE / f"{which}.nl.txt").read_text(encoding="utf-8").rstrip("\n").split("\n")
    return L
def kind(l): 
    m = re.match(r"(## |- |[a-h]\. )", l); return m.group(1) if m else ""
ok = True
for f in sorted(HERE.glob("*.??.txt")):
    which, lang = f.name.split(".")[:2]
    if lang == "nl": continue
    a = nl_lines(which); b = f.read_text(encoding="utf-8").rstrip("\n").split("\n")
    if len(a) != len(b): print(f.name, "line count", len(b), "expected", len(a)); ok = False
    for i, (x, y) in enumerate(zip(a, b), 1):
        if kind(x) != kind(y): print(f.name, "line", i, repr(kind(x)), "vs", repr(y[:50])); ok = False; break
print("legal ok" if ok else "legal MISMATCH"); sys.exit(0 if ok else 1)
