import re, pathlib
root = pathlib.Path(".")
STAT = {"unverified","to-backtest","testing","verified","deprecated","reference"}
files = [p for p in root.rglob("*.md") if ".backtest" not in p.parts and ".obsidian" not in p.parts and ".backup" not in p.parts]
prob = []
for p in files:
    txt = p.read_text(encoding="utf-8")
    if not txt.startswith("---"):
        continue
    fm = txt.split("---",2)[1]
    st = re.search(r"^status:\s*(\S+)", fm, re.M)
    tg = re.search(r"^tags:\s*\[(.*?)\]", fm, re.M)
    st_v = st.group(1).strip() if st else None
    tags = [t.strip() for t in tg.group(1).split(",")] if tg else []
    stat_tags = [t for t in tags if t in STAT]
    if st_v is None:
        prob.append((str(p),"no status field",tags)); continue
    if st_v not in STAT:
        prob.append((str(p),f"illegal status {st_v}",tags))
    if len(stat_tags)!=1:
        prob.append((str(p),f"status tags {stat_tags} (expect exactly 1) vs status={st_v}",tags))
    elif stat_tags[0]!=st_v:
        prob.append((str(p),f"tag {stat_tags[0]} != status {st_v}",tags))
    bad_tags=[t for t in tags if t not in STAT and not re.fullmatch(r"[a-z][a-z0-9]*(-[a-z0-9]+)*", t)]
    if bad_tags:
        prob.append((str(p),f"non-dict/illegal tag names {bad_tags}",tags))
print("problems:", len(prob))
for a,b,c in prob: print("  ",a,"|",b,"|",c)
