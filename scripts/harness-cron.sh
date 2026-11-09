#!/usr/bin/env bash
# Harness T0-T8 全门禁周期化 — 12 域 6h cron (蓝图 C4: Harness 结果是投影)
# 挂载: crontab -e → 0 */6 * * * bash /Users/xiamingxing/Workspace/projects/l4-kernel/scripts/harness-cron.sh
set -euo pipefail
# cron 的最小 PATH 是 /usr/bin:/bin, 不含 /opt/homebrew/bin —— 而 `uv` 在那里。
# 实测 (2026-11-09): 不带这一行时, 同一条 crontab 下 12/12 域全报 ok=ERR
# (env -i PATH=/usr/bin:/bin 复现), 而交互/直跑全绿 —— 因为 `uv run` 直接 FileNotFound,
# 被 `|| echo '{"error":true}'` 吞成 ERR。补上 PATH 后 12/12 ok=True。
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
WS="/Users/xiamingxing/Workspace"
L4_DIR="$WS/projects/l4-kernel"
REGISTRY="/Users/xiamingxing/Documents/@公共/_control/L4-DOMAIN-REGISTRY.yaml"
LOG="$WS/runtime/cron/l4-harness-cron.log"
export L4_DOMAIN_REGISTRY="$REGISTRY"
cd "$L4_DIR"

echo "=== L4 Harness cron run $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
FAIL=0
for domain in shared personal vault family creative opc work-docs work-weijian work-guozhuan work-liyongke work-contracts cockpit; do
  ERR_FILE="$(mktemp)"
  RESULT=$(uv run python -m l4_kernel.cli harness run "$domain" --json 2>"$ERR_FILE" || echo '{"error":true}')
  OK=$(echo "$RESULT" | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('data',{}).get('ok','ERR'))" 2>/dev/null || echo "ERR")
  echo "  $domain: ok=$OK"
  # 失败时打出 stderr 末行 —— 此前是 `2>/dev/null`, 把「uv 不在 PATH」这类死因全吞成 ERR,
  # 于是 12/12 全 ERR 的日志里没有任何可诊断信息 (2026-11-09 实测)。
  if [ "$OK" != "True" ] && [ -s "$ERR_FILE" ]; then
    echo "    err: $(tail -1 "$ERR_FILE")"
  fi
  rm -f "$ERR_FILE"
  [ "$OK" != "True" ] && FAIL=$((FAIL+1)) || true
done
echo "=== done: $((12-FAIL))/12 ok, $FAIL failed ==="
exit 0
