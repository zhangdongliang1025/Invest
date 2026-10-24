"""Pairwise similarity scan over 10-原始素材 to find genuine duplicate/overlapping notes.

Method: strip frontmatter, images, wikilinks, markdown syntax, whitespace.
Then compare with (a) character 3-gram Jaccard, (b) difflib ratio on the
normalized bodies, (c) longest common contiguous line-block share.
"""
import re
import sys
import itertools
from pathlib import Path
from difflib import SequenceMatcher

ROOT = Path(__file__).resolve().parent.parent
DIRS = [ROOT / "10-原始素材", ROOT / "99-归档"]
# 归档索引是管理笔记，不是素材，排除
EXCLUDE = {"归档索引.md"}


def strip_fm(text):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            nl = text.find("\n", end + 1)
            return text[nl + 1:] if nl != -1 else ""
    return text


def normalize(text):
    t = strip_fm(text)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)          # images
    t = re.sub(r"\[\[([^\]|]*\|)?([^\]]*)\]\]", r"\2", t)  # wikilinks
    t = re.sub(r"https?://\S+", "", t)                     # urls
    t = re.sub(r"[#*>`~\[\]()|+\-=]", "", t)               # markdown punct
    t = re.sub(r"\s+", "", t)
    return t


def shingles(s, k=3):
    return {s[i:i + k] for i in range(max(0, len(s) - k + 1))}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    A, B = shingles(a), shingles(b)
    return len(A & B) / len(A | B)


def line_blocks(t):
    body = strip_fm(t)
    blocks = []
    for line in body.split("\n"):
        s = line.strip()
        s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
        s = re.sub(r"[#*>`~\[\]()]", "", s).strip()
        if len(s) >= 8:
            blocks.append(s)
    return blocks


def block_overlap(a, b):
    """Fraction of a's line-blocks that appear verbatim in b."""
    if not a:
        return 0.0
    sb = set(b)
    hit = sum(1 for x in a if x in sb)
    return hit / len(a)


def main():
    files = sorted(f for d in DIRS for f in d.rglob("*.md") if f.name not in EXCLUDE)
    docs = {}
    for f in files:
        raw = f.read_text(encoding="utf-8")
        docs[f] = {
            "raw": raw,
            "norm": normalize(raw),
            "blocks": line_blocks(raw),
            "rel": str(f.relative_to(ROOT)),
        }

    rows = []
    for f1, f2 in itertools.combinations(files, 2):
        d1, d2 = docs[f1], docs[f2]
        j = jaccard(d1["norm"], d2["norm"])
        r = SequenceMatcher(None, d1["norm"], d2["norm"]).ratio()
        bo = block_overlap(d1["blocks"], d2["blocks"])
        bo2 = block_overlap(d2["blocks"], d1["blocks"])
        rows.append((max(j, r), j, r, bo, bo2, d1, d2))

    rows.sort(key=lambda x: -x[0])
    print("=== top 25 pairs by normalized similarity ===")
    for score, j, r, bo, bo2, d1, d2 in rows[:25]:
        print(f"\nscore={score:.3f}  jaccard3={j:.3f}  difflib={r:.3f}  "
              f"block_a_in_b={bo:.2f}  block_b_in_a={bo2:.2f}")
        print(f"  A: {d1['rel']}  ({len(d1['norm'])} chars)")
        print(f"  B: {d2['rel']}  ({len(d2['norm'])} chars)")

    print("\n\n=== pairs with >=12% line-block containment (either direction) ===")
    seen = set()
    for score, j, r, bo, bo2, d1, d2 in rows:
        hi = max(bo, bo2)
        if hi >= 0.12:
            key = (d1["rel"], d2["rel"])
            if key in seen:
                continue
            seen.add(key)
            print(f"contain={hi:.2f} (a->b {bo:.2f}, b->a {bo2:.2f}) "
                  f"sim={score:.3f}\n  A: {d1['rel']}\n  B: {d2['rel']}")

    print("\n\n=== length table (normalized chars) ===")
    for f in files:
        print(f"{len(docs[f]['norm']):6d}  {docs[f]['rel']}")


if __name__ == "__main__":
    main()
