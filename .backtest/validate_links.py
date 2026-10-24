import re, pathlib, sys
root = pathlib.Path(".")
files = [p for p in root.rglob("*.md") if ".backtest" not in p.parts and ".obsidian" not in p.parts]
names = {p.stem for p in files}
bad = []
for p in files:
    txt = p.read_text(encoding="utf-8")
    for m in re.findall(r"\[\[([^\]\|#]+)(?:#[^\]\|]*)?(?:\|[^\]]*)?\]\]", txt):
        t = m.strip()
        if t and t not in names:
            bad.append((str(p), t))
print("files:", len(files), "| unresolved links:", len(bad))
for f, t in bad:
    print("  MISSING:", t, "<-", f)
