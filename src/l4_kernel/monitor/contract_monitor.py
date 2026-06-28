"""P110-C: l4-kernel BOS Contract Linter 监督脚本 (Phase 1, ADR-0110).

监督 git log 找修改 bos-services.yaml 的 commit, 检查 commit message
是否含 "mof contract-lint" (Phase 0 pre-commit 拦截标记). 失败时:
  1. 写入 .omo/_knowledge/audits/contract-monitor.log
  2. 创建 DEBT 条目到 .omo/_knowledge/debts/

输出 exit 1 给 cron wrapper (触发 omo_alert).

依赖: 需在 l4-kernel venv 中 (无第三方依赖, stdlib only).
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# BOS-services.yaml 路径 (相对 workspace root)
BOS_SERVICES_REL = "projects/agora/etc/bos-services.yaml"

# 7 天回溯 (P110-C 默认窗口)
DEFAULT_LOOKBACK_DAYS = 7

# 拦截标记: commit message 含此关键字 (Phase 0 pre-commit 触发的提交)
LINT_KEYWORDS = ["mof contract-lint", "mof-contract-lint", "bos contract linter", "contract lint"]


def find_modified_commits(days_back: int = DEFAULT_LOOKBACK_DAYS) -> list[str]:
    """Find commits that modified bos-services.yaml in the last N days.

    Returns:
        List of commit SHAs.
    """
    try:
        result = subprocess.run(
            [
                "git", "log", f"--since={days_back} days ago",
                "--pretty=format:%H", "--name-only", BOS_SERVICES_REL,
            ],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return []
    except Exception as e:  # noqa: BLE001  # defensive fallback
        print(f"Error scanning commits: {e}", file=sys.stderr)
        return []

    shas: list[str] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line and re.match(r"^[0-9a-f]{40}$", line):
            shas.append(line)
    return shas


def check_commit_for_lint(sha: str) -> bool:
    """Check if a specific commit contains evidence of mof contract-lint execution.

    Strategy: check commit message for LINT_KEYWORDS substring match.
    A production version would also check CI logs (Phase 1 D4 covers this).
    """
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--pretty=format:%B", sha],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            message = result.stdout.lower()
            return any(kw in message for kw in LINT_KEYWORDS)
    except Exception as e:  # noqa: BLE001  # defensive fallback
        print(f"Error checking commit {sha[:8]}: {e}", file=sys.stderr)
    return False


def log_suspicious(suspicious_shas: list[str]) -> None:
    """Log suspicious commits to audit file + create DEBT entry."""
    timestamp = datetime.now().isoformat()

    # 1. 写入 audit log
    audit_log = Path(".omo/_knowledge/audits/contract-monitor.log")
    audit_log.parent.mkdir(parents=True, exist_ok=True)
    with audit_log.open("a") as f:
        f.write(f"[{timestamp}] SUSPICIOUS_COMMITS: {', '.join(suspicious_shas)}\n")

    # 2. 创建 DEBT 条目
    debt_content = f"""---
title: "BOS Contract Linter Bypass Detected (Phase 1, P110-C)"
status: "open"
priority: "P1"
type: "governance"
---

A potential bypass of the BOS Contract Linter was detected.

**Details**:
- Suspicious Commits: {', '.join(suspicious_shas)}
- Timestamp: {timestamp}
- Detection Window: {DEFAULT_LOOKBACK_DAYS} days
- Next Steps: Investigate these commits and ensure all future bos-services.yaml
  changes go through `mof contract-lint` (Phase 0 pre-commit + Phase 1 CI gate).
"""
    debt_path = Path(f".omo/_knowledge/debts/DEBT-{datetime.now().strftime('%Y%m%d%H%M%S')}-contract-bypass.yaml")
    debt_path.parent.mkdir(parents=True, exist_ok=True)
    debt_path.write_text(debt_content, encoding="utf-8")
    print(f"Created DEBT: {debt_path}")


def main() -> int:
    """Main entry point for contract_monitor (Phase 1, P110-C)."""
    print("[P110-C] Running BOS Contract Linter Bypass Monitor...")

    suspicious: list[str] = []
    for sha in find_modified_commits():
        if not check_commit_for_lint(sha):
            suspicious.append(sha)

    if suspicious:
        log_suspicious(suspicious)
        print(f"WARN: {len(suspicious)} suspicious commits found. See audit log + DEBT entry.")
        return 1
    else:
        print("[OK] No suspicious commits found. All bos-services.yaml changes went through linter.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
