#!/usr/bin/env python3
"""校验 10-原始素材 的整理是否只做了规范化、没有改动文字。

规则：
  1. 正文（## 正文 之后）的文字，必须与整理前原文逐字一致（去时间戳标记、去行尾空白后比较）。
  2. 整理前已有的摘要块，其文字必须原样出现在新的「内容摘要」块里。
  3. frontmatter 不得改动。
退出码 0 = 全部通过。
"""
import re
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(".")
SRC = ROOT / "10-原始素材"
BASE_COMMIT = os.environ.get("BASE_COMMIT", "778d307")

TS = re.compile(r"\[\s*\d{1,2}:\d{2}\s*[~-]\s*\d{1,2}:\d{2}\s*\]|\[\s*\d{1,2}:\d{2}\s*\]")
PARA = [
    ("（含时间戳，对应核心讲解内容）", "（对应核心讲解内容）"),
    ("（含时间戳与口语化表达，对应视频核心观点）", "（含口语化表达，对应视频核心观点）"),
    ("（含时间戳与口语化表达还原）", "（含口语化表达还原）"),
    ("（含时间戳对应原文）", "（对应原文）"),
]
# 整理前就有独立摘要块的文件：以「以下是」作为原文起点
LEAD = "以下是"


def split_body(text):
    if text.startswith("---"):
        parts = text.split("---", 2)
        return parts[1], parts[2]
    return "", text


def strip_ws(s):
    return re.sub(r"\s+", "", s)


def strip_quote(s):
    out = []
    for line in s.splitlines():
        line = re.sub(r"^\s*>\s?", "", line)
        if line.strip() == ">":
            continue
        out.append(line)
    return "\n".join(out)


def normalize_orig(body):
    body = TS.sub("", body)
    for a, b in PARA:
        body = body.replace(a, b)
    return body


def main():
    only = sys.argv[1:]
    problems = []
    checked = 0
    skipped = []
    baseline = set(
        subprocess.run(
            ["git", "ls-tree", "-r", "-z", "--name-only", BASE_COMMIT, "--", "10-原始素材"],
            capture_output=True, text=True, cwd=ROOT,
        ).stdout.split("\0")
    )
    for p in sorted(SRC.rglob("*.md")):
        rel = p.relative_to(SRC)
        if only and not any(k in str(rel) for k in only):
            continue
        key = f"10-原始素材/{rel}"
        if key not in baseline:
            skipped.append(str(rel))
            continue
        orig_full = subprocess.run(
            ["git", "show", f"{BASE_COMMIT}:10-原始素材/{rel}"],
            capture_output=True, text=True, cwd=ROOT,
        ).stdout
        if not orig_full:
            problems.append(f"{rel}: 取不到基线原文")
            continue
        checked += 1
        orig_fm, orig_body = split_body(orig_full)
        cur_fm, cur_body = split_body(p.read_text(encoding="utf-8"))

        # 3. frontmatter 不得改动
        if strip_ws(orig_fm) != strip_ws(cur_fm):
            problems.append(f"{rel}: frontmatter 被改动")

        # 定位新结构
        if "> **内容摘要**" not in cur_body or "\n## 正文\n" not in cur_body:
            problems.append(f"{rel}: 缺少「内容摘要」块或「## 正文」标题")
            continue
        summary = cur_body.split("> **内容摘要**", 1)[1].split("\n## 正文\n", 1)[0]
        raw = cur_body.split("\n## 正文\n", 1)[1]

        # 1. 正文逐字比对
        norm_orig = normalize_orig(orig_body)
        if LEAD in norm_orig:
            head, tail = norm_orig.split(LEAD, 1)
            tail = LEAD + tail
        else:
            head, tail = "", norm_orig
        if strip_ws(tail) != strip_ws(raw):
            a, b = strip_ws(tail), strip_ws(raw)
            i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
            problems.append(
                f"{rel}: 正文与原文不一致（原 {len(a)} 字 / 新 {len(b)} 字，首个差异在第 {i} 字）\n"
                f"        原: ...{a[max(0,i-30):i+30]}...\n"
                f"        新: ...{b[max(0,i-30):i+30]}..."
            )

        # 2. 原有摘要必须保留在新摘要块里
        if head.strip():
            old_sum = strip_ws(strip_quote(head))
            new_sum = strip_ws(strip_quote(summary))
            if old_sum not in new_sum:
                problems.append(f"{rel}: 原有摘要文字未完整保留到「内容摘要」块")

    print(f"校验 {checked} 个文件")
    if skipped:
        print(f"跳过 {len(skipped)} 个基线之后新增的素材（无整理前原文可比）：{', '.join(skipped)}")
    if problems:
        print(f"不通过 {len(problems)} 项：")
        for x in problems:
            print("  -", x)
        return 1
    print("全部通过：正文文字零改动，原摘要完整保留，frontmatter 未动")
    return 0


if __name__ == "__main__":
    sys.exit(main())
