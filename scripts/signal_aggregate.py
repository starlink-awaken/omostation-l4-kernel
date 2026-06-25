#!/usr/bin/env python3
"""L4 Domain 信号聚合脚本。

聚合相似信号，减少信号数量。

使用方式:
    python scripts/signal_aggregate.py
    python scripts/signal_aggregate.py --window 5
    python scripts/signal_aggregate.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

# 添加 src 到 path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from l4_kernel.kems import KemsPlane
from l4_kernel.registry import DomainRegistry


def aggregate_window(signals: list[dict]) -> dict:
    """聚合一个时间窗口内的信号。"""
    if not signals:
        return {}

    # 取最新的信号作为基础
    latest = max(signals, key=lambda s: s.get("ts", ""))

    # 统计信号类型
    type_counts = {}
    for signal in signals:
        signal_type = signal.get("type", "ℹ️")
        type_counts[signal_type] = type_counts.get(signal_type, 0) + 1

    # 构建聚合消息
    messages = [s.get("message", "") for s in signals if s.get("message")]
    unique_messages = list(set(messages))
    aggregated_message = "; ".join(unique_messages[:3])  # 最多保留 3 条消息

    return {
        "ts": latest["ts"],
        "type": latest["type"],
        "source": "aggregated",
        "message": f"聚合 {len(signals)} 个信号: {aggregated_message}",
        "count": len(signals),
        "type_counts": type_counts,
    }


def aggregate_signals(window_minutes: int = 5, dry_run: bool = False) -> dict:
    """聚合相似信号。"""
    registry = DomainRegistry()

    result = {
        "total_aggregated": 0,
        "domains": [],
    }

    for domain in registry.list_document_domains():
        if not domain.exists():
            continue

        kems = KemsPlane(domain.path)
        signals = kems.read_signals()

        if not signals or len(signals) < 2:
            continue

        # 按时间排序
        sorted_signals = sorted(signals, key=lambda s: s.get("ts", ""))

        # 聚合信号
        aggregated = []
        current_window = []
        window_start = None

        for signal in sorted_signals:
            ts = signal.get("ts", "")
            if not ts:
                continue

            try:
                signal_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                aggregated.append(signal)
                continue

            if window_start is None:
                window_start = signal_dt
                current_window = [signal]
                continue

            # 检查是否在时间窗口内
            if (signal_dt - window_start).total_seconds() <= window_minutes * 60:
                current_window.append(signal)
            else:
                # 聚合当前窗口
                if current_window:
                    if len(current_window) > 1:
                        aggregated.append(aggregate_window(current_window))
                    else:
                        aggregated.extend(current_window)
                window_start = signal_dt
                current_window = [signal]

        # 处理最后一个窗口
        if current_window:
            if len(current_window) > 1:
                aggregated.append(aggregate_window(current_window))
            else:
                aggregated.extend(current_window)

        # 写回信号
        aggregated_count = len(signals) - len(aggregated)
        if aggregated_count > 0:
            if not dry_run:
                kems._write_yaml_md("signals.md", {"signals": aggregated})

            result["domains"].append({
                "id": domain.id,
                "name": domain.name,
                "aggregated": aggregated_count,
                "remaining": len(aggregated),
            })
            result["total_aggregated"] += aggregated_count

    return result


def main():
    parser = argparse.ArgumentParser(description="L4 Domain 信号聚合")
    parser.add_argument(
        "--window",
        type=int,
        default=5,
        help="聚合时间窗口（分钟）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="模拟运行，不实际聚合",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("L4 Domain 信号聚合")
    print("=" * 80)

    if args.dry_run:
        print("\n[DRY RUN] 模拟运行，不实际聚合")

    # 聚合信号
    result = aggregate_signals(args.window, args.dry_run)

    # 输出结果
    print("\n聚合结果:")
    print(f"  时间窗口: {args.window} 分钟")
    print(f"  聚合信号数: {result['total_aggregated']}")

    if result["domains"]:
        print("\n域详情:")
        for domain in result["domains"]:
            print(f"  {domain['id']}: 聚合 {domain['aggregated']} 个，剩余 {domain['remaining']} 个")
    else:
        print("\n无需聚合")

    # 返回退出码
    sys.exit(0)


if __name__ == "__main__":
    main()
