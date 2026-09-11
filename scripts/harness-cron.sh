#!/usr/bin/env bash
# Harness T0-T8 全门禁周期化 — 12 域 6h cron (蓝图 C4: Harness 结果是投影)
# 挂载: crontab -e → 0 */6 * * * bash /Users/xiamingxing/Workspace/projects/l4-kernel/scripts/harness-cron.sh
set -euo pipefail
WS="/Users/xiamingxing/Workspace"
L4_DIR="$WS/projects/l4-kernel"
REGISTRY="/Users/xiamingxing/Documents/@公共/_control/L4-DOMAIN-REGISTRY.yaml"
LOG="$WS/runtime/cron/l4-harness-cron.log"
export L4_DOMAIN_REGISTRY="$REGISTRY"
cd "$L4_DIR"

echo "=== L4 Harness cron run $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
FAIL=0
for domain in shared personal vault family creative opc work-docs work-weijian work-guozhuan work-liyongke work-contracts cockpit; do
  RESULT=$(uv run python -m l4_kernel.cli harness run "$domain" --json 2>/dev/null || echo '{"error":true}')
  OK=$(echo "$RESULT" | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('data',{}).get('ok','ERR'))" 2>/dev/null || echo "ERR")
  echo "  $domain: ok=$OK"
  [ "$OK" != "True" ] && FAIL=$((FAIL+1)) || true
done
echo "=== done: $((12-FAIL))/12 ok, $FAIL failed ==="
exit 0
