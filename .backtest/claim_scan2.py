"""Claim-level overlap, fixed: URL/HTML stripping must not eat Chinese text.

Regex fix: bare URLs matched with an ASCII-only charset, markdown links removed
before bare-URL removal. Then compare distinctive numeric claims per note.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIRS = [ROOT / "10-原始素材", ROOT / "99-归档"]
# 归档索引是管理笔记，不是素材，排除
EXCLUDE = {"归档索引.md"}

MD_LINK = re.compile(r"\[([^\]]*)\]\(\s*[^)\s]*\s*\)")
BARE_URL = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")
CLAIM = re.compile(r"[0-9]+(?:\.[0-9]+)?\s*(?:%|倍|年|月|日|亿|万|点|家|次|天|成|元)")


def strip_fm(text):
    if text.startswith("---"):
        e = text.find("\n---", 3)
        nl = text.find("\n", e + 1)
        return text[nl + 1:] if nl != -1 else ""
    return text


def content_of(text):
    """只取「## 正文」段——原始内容；未规范化的归档件取整篇。

    「内容摘要」是后加的概括层，不参与数值主张提取，否则摘要一改，证据就漂了。
    """
    b = strip_fm(text)
    marker = "\n## 正文\n"
    if marker in b:
        return b.split(marker, 1)[1]
    return b


def body_of(text):
    b = content_of(text)
    b = MD_LINK.sub(r"\1", b)
    b = BARE_URL.sub("", b)
    b = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", b)
    return b


def claims(text):
    out = set()
    for m in CLAIM.finditer(body_of(text)):
        out.add(re.sub(r"\s+", "", m.group(0)))
    return out


def bigrams(text):
    t = body_of(text)
    t = re.sub(r"[^\u4e00-\u9fff]", "", t)
    return {t[i:i + 2] for i in range(len(t) - 1)}


def contain(a, b):
    return len(a & b) / len(a) if a else 0.0


def main():
    files = sorted(f for d in DIRS for f in d.rglob("*.md") if f.name not in EXCLUDE)
    C, K = {}, {}
    for f in files:
        raw = f.read_text(encoding="utf-8")
        C[f] = claims(raw)
        K[f] = bigrams(raw)

    print("=== A -> B numeric-claim containment (A's claims >=70% inside B) ===")
    for f1 in files:
        for f2 in files:
            if f1 == f2 or len(C[f1]) < 2:
                continue
            r = contain(C[f1], C[f2])
            if r >= 0.7:
                print(f"  {r:>4.0%}  {f1.relative_to(ROOT)}  ->  {f2.relative_to(ROOT)}")
                print(f"         unique-in-A: {sorted(C[f1] - C[f2])}")

    print("\n=== top 20 by max keyword-bigram containment ===")
    rows = []
    for i, f1 in enumerate(files):
        for f2 in files[i + 1:]:
            if len(K[f1]) < 30 or len(K[f2]) < 30:
                continue
            r = max(contain(K[f1], K[f2]), contain(K[f2], K[f1]))
            rows.append((r, f1, f2))
    rows.sort(key=lambda x: -x[0])
    for r, f1, f2 in rows[:20]:
        print(f"  {r:>4.0%}  {f1.relative_to(ROOT)}  <->  {f2.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
