#!/usr/bin/env bash
# 发布前检查：体积、凭证、本机路径、库内一致性
# 用法：git add -A && .backtest/prepush_check.sh
# 退出码 0 = 通过（允许已登记的既有问题），1 = 有新增问题

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

BASE_LINKS=3      # validate_links.py 已登记的既有问题数
BASE_STATUS=11    # validate_status.py 已登记的既有问题数

fail=0

echo "== 1. 体积：行情数据与虚拟环境不应入库 =="
hits=$(git ls-files | grep -cE "\.backtest/(data|venv)/" || true)
if [ "$hits" -eq 0 ]; then
  echo "  OK"
else
  echo "  FAIL: $hits 个大文件路径被跟踪"
  git ls-files | grep -E "\.backtest/(data|venv)/" | head
  fail=1
fi

echo "== 2. 凭证 =="
# 排除本脚本自身：它内嵌了匹配用的正则
cred=$(git grep --cached -InE "(api[_-]?key|secret[_-]?key|access[_-]?key|token|password|passwd|authorization|bearer |BEGIN [A-Z ]*PRIVATE KEY|ghp_|github_pat_|AKIA[0-9A-Z]{16})" -- . ':(exclude).backtest/prepush_check.sh' 2>/dev/null)
if [ -z "$cred" ]; then
  echo "  OK"
else
  echo "  FAIL: 命中以下行，请逐条确认"
  echo "$cred" | head -20
  fail=1
fi

echo "== 3. 本机绝对路径 =="
paths=$(git grep --cached -In "/Users/" -- . ':(exclude).backtest/prepush_check.sh' 2>/dev/null)
if [ -z "$paths" ]; then
  echo "  OK"
else
  echo "  FAIL: 命中以下行（会暴露用户名，且脚本在别的机器上跑不通）"
  echo "$paths" | head -20
  fail=1
fi

echo "== 4. 链接一致性 =="
link_out=$(python3 .backtest/validate_links.py 2>&1)
link_n=$(printf '%s\n' "$link_out" | sed -n 's/.*unresolved links: \([0-9]*\).*/\1/p')
printf '%s\n' "$link_out" | sed -n '2,$p' | sed 's/^/  /'
if [ "${link_n:-999}" -gt "$BASE_LINKS" ]; then
  echo "  FAIL: 未解析链接 $link_n > 基线 $BASE_LINKS"
  fail=1
else
  echo "  OK ($link_n / 基线 $BASE_LINKS)"
fi

echo "== 5. status 与标签一致性 =="
st_out=$(python3 .backtest/validate_status.py 2>&1)
st_n=$(printf '%s\n' "$st_out" | sed -n 's/^problems: \([0-9]*\).*/\1/p')
if [ "${st_n:-999}" -gt "$BASE_STATUS" ]; then
  echo "  FAIL: 问题数 $st_n > 基线 $BASE_STATUS"
  printf '%s\n' "$st_out" | sed -n '2,$p' | sed 's/^/  /' | head -20
  fail=1
else
  echo "  OK ($st_n / 基线 $BASE_STATUS)"
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "结论：全部通过，可以提交并推送。"
else
  echo "结论：有问题，先修再提交。"
fi
exit $fail
