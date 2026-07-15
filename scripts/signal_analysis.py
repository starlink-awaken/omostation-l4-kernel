#!/usr/bin/env python3
"""L4 Domain 跨域信号分析。

分析跨域信号模式，识别系统性风险。

使用方式:
    python scripts/signal_analysis.py
    python scripts/signal_analysis.py --hours 72
    python scripts/signal_analysis.py --output json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

# 添加 src 到 path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from l4_kernel.config_loader import load_overrides_from_config
from l4_kernel.kems import KemsPlane
from l4_kernel.registry import DomainRegistry

CONFIG_PATH = Path(__file__).parent.parent / "l4_domain_paths.toml"


def collect_signals(hours: int = 72) -> list[dict]:
    """收集信号。"""
    registry = DomainRegistry(path_overrides=load_overrides_from_config(CONFIG_PATH))
    signals = []
    cutoff = datetime.now(UTC) - timedelta(hours=hours)

    for domain in registry.list_document_domains():
        if not domain.exists():
            continue

        kems = KemsPlane(domain.path)
        domain_signals = kems.read_signals()

        if not domain_signals:
            continue

        for signal in domain_signals:
            ts = signal.get("ts", "")
            if not ts:
                continue

            try:
                signal_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if signal_dt >= cutoff:
                    signal["domain_id"] = domain.id
                    signal["domain_name"] = domain.name
                    signals.append(signal)
            except (ValueError, TypeError):
                continue

    return signals


def analyze_signals(signals: list[dict]) -> dict:
    """分析信号。"""
    if not signals:
        return {
            "total_signals": 0,
            "by_domain": {},
            "by_type": {},
            "patterns": [],
            "risks": [],
        }

    # 按域分组
    by_domain = defaultdict(list)
    for signal in signals:
        domain_id = signal.get("domain_id", "unknown")
        by_domain[domain_id].append(signal)

    # 按类型分组
    by_type = defaultdict(list)
    for signal in signals:
        signal_type = signal.get("type", "ℹ️")
        by_type[signal_type].append(signal)

    # 检测模式
    patterns = []

    # 模式 1: 多域同时 ⚠️
    warning_domains = set()
    for signal in signals:
        if signal.get("type") == "⚠️":
            warning_domains.add(signal.get("domain_id", ""))
    if len(warning_domains) >= 3:
        patterns.append({
            "pattern": "multi_domain_warning",
            "domains": sorted(warning_domains),
            "count": len(warning_domains),
            "level": "⚠️",
            "message": f"{len(warning_domains)} 个域同时出现 ⚠️ 信号 — 可能存在系统性问题",
        })

    # 模式 2: 同域连续 🔴
    for domain_id, domain_signals in by_domain.items():
        reds = [s for s in domain_signals if s.get("type") == "🔴"]
        if len(reds) >= 3:
            patterns.append({
                "pattern": "consecutive_red",
                "domain": domain_id,
                "count": len(reds),
                "level": "🔴",
                "message": f"{domain_id} 连续出现 {len(reds)} 个 🔴 信号 — 需要升级处理",
            })

    # 模式 3: 信号数量异常
    avg_signals = len(signals) / len(by_domain) if by_domain else 0
    for domain_id, domain_signals in by_domain.items():
        if len(domain_signals) > avg_signals * 2:
            patterns.append({
                "pattern": "high_signal_volume",
                "domain": domain_id,
                "count": len(domain_signals),
                "level": "ℹ️",
                "message": f"{domain_id} 信号数量异常 ({len(domain_signals)} 个，平均 {avg_signals:.1f} 个)",
            })

    # 检测风险
    risks = []

    # 风险 1: 系统性风险
    if len(warning_domains) >= 3:
        risks.append({
            "risk": "systemic_risk",
            "severity": "high",
            "domains": sorted(warning_domains),
            "message": f"系统性风险: {len(warning_domains)} 个域同时出现 ⚠️ 信号",
        })

    # 风险 2: 单点故障风险
    for domain_id, domain_signals in by_domain.items():
        reds = [s for s in domain_signals if s.get("type") == "🔴"]
        if len(reds) >= 5:
            risks.append({
                "risk": "single_point_failure",
                "severity": "high",
                "domain": domain_id,
                "message": f"单点故障风险: {domain_id} 出现 {len(reds)} 个 🔴 信号",
            })

    # 风险 3: 信号丢失风险
    for domain_id, domain_signals in by_domain.items():
        if len(domain_signals) == 0:
            risks.append({
                "risk": "signal_loss",
                "severity": "medium",
                "domain": domain_id,
                "message": f"信号丢失风险: {domain_id} 没有信号",
            })

    return {
        "total_signals": len(signals),
        "by_domain": {k: len(v) for k, v in by_domain.items()},
        "by_type": {k: len(v) for k, v in by_type.items()},
        "patterns": patterns,
        "risks": risks,
    }


def output_text(result: dict) -> None:
    """输出文本格式。"""
    print("=" * 80)
    print("L4 Domain 跨域信号分析")
    print("=" * 80)

    print(f"\n总信号数: {result['total_signals']}")

    print("\n## 按域分布")
    for domain_id, count in sorted(result["by_domain"].items()):
        print(f"  {domain_id}: {count} 个信号")

    print("\n## 按类型分布")
    for signal_type, count in sorted(result["by_type"].items()):
        print(f"  {signal_type}: {count} 个信号")

    print("\n## 检测到的模式")
    if result["patterns"]:
        for pattern in result["patterns"]:
            print(f"  [{pattern['level']}] {pattern['message']}")
    else:
        print("  未检测到异常模式")

    print("\n## 风险评估")
    if result["risks"]:
        for risk in result["risks"]:
            print(f"  [{risk['severity'].upper()}] {risk['message']}")
    else:
        print("  未发现风险")


def output_json(result: dict) -> None:
    """输出 JSON 格式。"""
    print(json.dumps(result, indent=2, ensure_ascii=False))


def output_markdown(result: dict) -> None:
    """输出 Markdown 格式。"""
    print("# L4 Domain 跨域信号分析")
    print("")
    print(f"> 总信号数: {result['total_signals']}")

    print("")
    print("## 按域分布")
    print("")
    print("| 域 | 信号数 |")
    print("|----|--------|")
    for domain_id, count in sorted(result["by_domain"].items()):
        print(f"| {domain_id} | {count} |")

    print("")
    print("## 按类型分布")
    print("")
    print("| 类型 | 数量 |")
    print("|------|------|")
    for signal_type, count in sorted(result["by_type"].items()):
        print(f"| {signal_type} | {count} |")

    print("")
    print("## 检测到的模式")
    print("")
    if result["patterns"]:
        for pattern in result["patterns"]:
            print(f"- **{pattern['level']}**: {pattern['message']}")
    else:
        print("未检测到异常模式")

    print("")
    print("## 风险评估")
    print("")
    if result["risks"]:
        for risk in result["risks"]:
            print(f"- **{risk['severity'].upper()}**: {risk['message']}")
    else:
        print("未发现风险")


def main():
    parser = argparse.ArgumentParser(description="L4 Domain 跨域信号分析")
    parser.add_argument(
        "--hours",
        type=int,
        default=72,
        help="分析时间窗口（小时）",
    )
    parser.add_argument(
        "--output",
        choices=["text", "json", "markdown"],
        default="text",
        help="输出格式",
    )
    args = parser.parse_args()

    # 收集信号
    signals = collect_signals(args.hours)

    # 分析信号
    result = analyze_signals(signals)

    # 输出结果
    if args.output == "text":
        output_text(result)
    elif args.output == "json":
        output_json(result)
    elif args.output == "markdown":
        output_markdown(result)

    # 返回退出码
    if result["risks"]:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
