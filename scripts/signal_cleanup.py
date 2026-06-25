#!/usr/bin/env python3
"""L4 Domain 信号清理脚本。

清理旧信号，减少信号数量。

使用方式:
    python scripts/signal_cleanup.py
    python scripts/signal_cleanup.py --days 7
    python scripts/signal_cleanup.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# 添加 src 到 path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from l4_kernel.kems import KemsPlane
from l4_kernel.registry import DomainRegistry


def cleanup_signals(days: int = 7, dry_run: bool = False) -> dict:
    """清理旧信号。"""
    registry = DomainRegistry()
    cutoff = datetime.now(UTC) - timedelta(days=days)

    result = {
        "total_cleaned": 0,
        "domains": [],
    }

    for domain in registry.list_document_domains():
        if not domain.exists():
            continue

        kems = KemsPlane(domain.path)
        signals = kems.read_signals()

        if not signals:
            continue

        # 过滤旧信号
        new_signals = []
        cleaned_count = 0

        for signal in signals:
            ts = signal.get("ts", "")
            if not ts:
                continue

            try:
                signal_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if signal_dt >= cutoff:
                    new_signals.append(signal)
                else:
                    cleaned_count += 1
            except (ValueError, TypeError):
                new_signals.append(signal)

        # 写回信号
        if cleaned_count > 0:
            if not dry_run:
                kems._write_yaml_md("signals.md", {"signals": new_signals})

            result["domains"].append({
                "id": domain.id,
                "name": domain.name,
                "cleaned": cleaned_count,
                "remaining": len(new_signals),
            })
            result["total_cleaned"] += cleaned_count

    return result


def main():
    parser = argparse.ArgumentParser(description="L4 Domain 信号清理")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="保留最近 N 天的信号",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="模拟运行，不实际清理",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("L4 Domain 信号清理")
    print("=" * 80)

    if args.dry_run:
        print("\n[DRY RUN] 模拟运行，不实际清理")

    # 清理信号
    result = cleanup_signals(args.days, args.dry_run)

    # 输出结果
    print("\n清理结果:")
    print(f"  保留天数: {args.days}")
    print(f"  清理信号数: {result['total_cleaned']}")

    if result["domains"]:
        print("\n域详情:")
        for domain in result["domains"]:
            print(f"  {domain['id']}: 清理 {domain['cleaned']} 个，剩余 {domain['remaining']} 个")
    else:
        print("\n无需清理")

    # 返回退出码
    sys.exit(0)


if __name__ == "__main__":
    main()
