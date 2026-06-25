#!/usr/bin/env python3
"""L4 Domain 健康监控脚本。

定期检查 KEMS 健康状态，输出报告。

使用方式:
    python scripts/health_monitor.py
    python scripts/health_monitor.py --output json
    python scripts/health_monitor.py --output markdown
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# 添加 src 到 path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from l4_kernel.health import DomainHealth
from l4_kernel.kems import KemsPlane
from l4_kernel.registry import DomainRegistry


def check_health(output_format: str = "text") -> dict:
    """检查所有域的健康状态。"""
    registry = DomainRegistry()
    health = DomainHealth(registry)

    result = {
        "timestamp": datetime.now(UTC).isoformat(),
        "total_domains": len(registry.list_all()),
        "document_domains": len(registry.list_document_domains()),
        "domains": [],
    }

    # 检查所有 DocumentDomain
    for d in registry.list_document_domains():
        if not d.exists():
            continue

        kems = KemsPlane(d.path)
        freshness = health.check_freshness(d.id)
        state = kems.read_state()
        status = kems.read_status()
        signals = kems.read_signals()

        domain_info = {
            "id": d.id,
            "name": d.name,
            "exists": True,
            "fresh": freshness["fresh"],
            "issue_count": freshness["issue_count"],
            "issues": freshness["issues"],
            "has_state": bool(state),
            "has_status": bool(status),
            "signal_count": len(signals) if signals else 0,
            "capabilities": d.capabilities,
        }
        result["domains"].append(domain_info)

    # 统计
    result["healthy_count"] = sum(1 for d in result["domains"] if d["fresh"])
    result["unhealthy_count"] = sum(1 for d in result["domains"] if not d["fresh"])
    result["health_rate"] = (
        f"{result['healthy_count'] / len(result['domains']) * 100:.1f}%" if result["domains"] else "N/A"
    )

    return result


def output_text(result: dict) -> None:
    """输出文本格式。"""
    print("=" * 80)
    print("L4 Domain 健康监控报告")
    print("=" * 80)
    print(f"\n时间: {result['timestamp']}")
    print(f"总域数: {result['total_domains']}")
    print(f"DocumentDomain: {result['document_domains']}")
    print(f"健康率: {result['health_rate']}")

    print("\n## 域健康状态")
    for d in result["domains"]:
        status = "✅" if d["fresh"] else "⚠️"
        print(f"  {d['id']}: {status} ({d['issue_count']} 个问题)")
        if d["issues"]:
            for issue in d["issues"]:
                print(f"    - {issue['level']} {issue['message']}")

    print("\n## KEMS 面配置")
    for d in result["domains"]:
        missing = []
        if not d["has_state"]:
            missing.append("state")
        if not d["has_status"]:
            missing.append("status")
        if d["signal_count"] == 0:
            missing.append("signals")

        if missing:
            print(f"  {d['id']}: 缺少 {missing}")
        else:
            print(f"  {d['id']}: ✅ 完整 ({d['signal_count']} 条信号)")


def output_json(result: dict) -> None:
    """输出 JSON 格式。"""
    print(json.dumps(result, indent=2, ensure_ascii=False))


def output_markdown(result: dict) -> None:
    """输出 Markdown 格式。"""
    print("# L4 Domain 健康监控报告")
    print("")
    print(f"> 时间: {result['timestamp']}")
    print("")
    print("## 总览")
    print("")
    print(f"- 总域数: {result['total_domains']}")
    print(f"- DocumentDomain: {result['document_domains']}")
    print(f"- 健康率: {result['health_rate']}")
    print("")
    print("## 域健康状态")
    print("")
    print("| 域 | 状态 | 问题数 | 信号数 |")
    print("|----|------|--------|--------|")
    for d in result["domains"]:
        status = "✅" if d["fresh"] else "⚠️"
        print(f"| {d['id']} | {status} | {d['issue_count']} | {d['signal_count']} |")

    print("")
    print("## KEMS 面配置")
    print("")
    print("| 域 | state | status | signals |")
    print("|----|-------|--------|---------|")
    for d in result["domains"]:
        state = "✅" if d["has_state"] else "❌"
        status = "✅" if d["has_status"] else "❌"
        signals = "✅" if d["signal_count"] > 0 else "❌"
        print(f"| {d['id']} | {state} | {status} | {signals} |")


def main():
    parser = argparse.ArgumentParser(description="L4 Domain 健康监控")
    parser.add_argument(
        "--output",
        choices=["text", "json", "markdown"],
        default="text",
        help="输出格式",
    )
    args = parser.parse_args()

    result = check_health()

    if args.output == "text":
        output_text(result)
    elif args.output == "json":
        output_json(result)
    elif args.output == "markdown":
        output_markdown(result)

    # 返回退出码
    if result["unhealthy_count"] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
