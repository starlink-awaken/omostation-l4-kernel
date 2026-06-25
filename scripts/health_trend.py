#!/usr/bin/env python3
"""L4 Domain 历史趋势分析。

分析健康状态历史数据，识别趋势和异常。

使用方式:
    python scripts/health_trend.py
    python scripts/health_trend.py --days 30
    python scripts/health_trend.py --output json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# 添加 src 到 path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def load_health_history(days: int = 30) -> list[dict]:
    """加载健康历史数据。"""
    logs_dir = Path(__file__).parent.parent / "logs"
    if not logs_dir.exists():
        return []

    history = []
    cutoff = datetime.now(UTC) - timedelta(days=days)

    for report_file in sorted(logs_dir.glob("health_report_*.json")):
        try:
            # 从文件名提取时间戳
            timestamp_str = report_file.stem.replace("health_report_", "")
            timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S").replace(tzinfo=UTC)

            if timestamp < cutoff:
                continue

            with open(report_file) as f:
                data = json.load(f)
                data["file_timestamp"] = timestamp.isoformat()
                history.append(data)
        except (json.JSONDecodeError, ValueError):
            continue

    return history


def analyze_trends(history: list[dict]) -> dict:
    """分析趋势。"""
    if not history:
        return {
            "total_records": 0,
            "trends": {},
            "anomalies": [],
        }

    # 按域分组
    domain_health = {}
    domain_signals = {}

    for record in history:
        for domain in record.get("domains", []):
            domain_id = domain["id"]

            # 健康状态趋势
            if domain_id not in domain_health:
                domain_health[domain_id] = []
            domain_health[domain_id].append({
                "timestamp": record.get("file_timestamp"),
                "fresh": domain["fresh"],
                "issue_count": domain["issue_count"],
            })

            # 信号数量趋势
            if domain_id not in domain_signals:
                domain_signals[domain_id] = []
            domain_signals[domain_id].append({
                "timestamp": record.get("file_timestamp"),
                "signal_count": domain["signal_count"],
            })

    # 分析趋势
    trends = {}
    for domain_id, health_data in domain_health.items():
        if len(health_data) < 2:
            continue

        # 计算健康率趋势
        healthy_count = sum(1 for d in health_data if d["fresh"])
        health_rate = healthy_count / len(health_data) * 100

        # 计算问题数趋势
        issue_counts = [d["issue_count"] for d in health_data]
        avg_issues = sum(issue_counts) / len(issue_counts)
        max_issues = max(issue_counts)

        # 计算信号数趋势
        signal_data = domain_signals.get(domain_id, [])
        if signal_data:
            signal_counts = [d["signal_count"] for d in signal_data]
            avg_signals = sum(signal_counts) / len(signal_counts)
            max_signals = max(signal_counts)
            min_signals = min(signal_counts)
        else:
            avg_signals = max_signals = min_signals = 0

        trends[domain_id] = {
            "health_rate": health_rate,
            "avg_issues": avg_issues,
            "max_issues": max_issues,
            "avg_signals": avg_signals,
            "max_signals": max_signals,
            "min_signals": min_signals,
            "record_count": len(health_data),
        }

    # 检测异常
    anomalies = []

    # 检测健康率下降
    for domain_id, trend in trends.items():
        if trend["health_rate"] < 100:
            anomalies.append({
                "domain": domain_id,
                "type": "health_degradation",
                "severity": "warning",
                "message": f"{domain_id} 健康率下降到 {trend['health_rate']:.1f}%",
            })

    # 检测信号数异常
    for domain_id, trend in trends.items():
        if trend["max_signals"] > 0 and trend["min_signals"] < trend["max_signals"] * 0.5:
            anomalies.append({
                "domain": domain_id,
                "type": "signal_fluctuation",
                "severity": "info",
                "message": f"{domain_id} 信号数波动较大 ({trend['min_signals']} - {trend['max_signals']})",
            })

    return {
        "total_records": len(history),
        "date_range": {
            "start": history[0]["file_timestamp"] if history else None,
            "end": history[-1]["file_timestamp"] if history else None,
        },
        "trends": trends,
        "anomalies": anomalies,
    }


def output_text(result: dict) -> None:
    """输出文本格式。"""
    print("=" * 80)
    print("L4 Domain 历史趋势分析")
    print("=" * 80)

    print(f"\n总记录数: {result['total_records']}")
    if result["date_range"]["start"]:
        print(f"时间范围: {result['date_range']['start']} - {result['date_range']['end']}")

    print("\n## 域趋势")
    for domain_id, trend in sorted(result["trends"].items()):
        print(f"\n  {domain_id}:")
        print(f"    健康率: {trend['health_rate']:.1f}%")
        print(f"    平均问题数: {trend['avg_issues']:.1f}")
        print(f"    最大问题数: {trend['max_issues']}")
        print(f"    平均信号数: {trend['avg_signals']:.1f}")
        print(f"    信号数范围: {trend['min_signals']} - {trend['max_signals']}")
        print(f"    记录数: {trend['record_count']}")

    print("\n## 异常检测")
    if result["anomalies"]:
        for anomaly in result["anomalies"]:
            print(f"  [{anomaly['severity'].upper()}] {anomaly['message']}")
    else:
        print("  未发现异常")


def output_json(result: dict) -> None:
    """输出 JSON 格式。"""
    print(json.dumps(result, indent=2, ensure_ascii=False))


def output_markdown(result: dict) -> None:
    """输出 Markdown 格式。"""
    print("# L4 Domain 历史趋势分析")
    print("")
    print(f"> 总记录数: {result['total_records']}")
    if result["date_range"]["start"]:
        print(f"> 时间范围: {result['date_range']['start']} - {result['date_range']['end']}")

    print("")
    print("## 域趋势")
    print("")
    print("| 域 | 健康率 | 平均问题数 | 平均信号数 | 记录数 |")
    print("|----|--------|------------|------------|--------|")
    for domain_id, trend in sorted(result["trends"].items()):
        print(f"| {domain_id} | {trend['health_rate']:.1f}% | {trend['avg_issues']:.1f} | {trend['avg_signals']:.1f} | {trend['record_count']} |")

    print("")
    print("## 异常检测")
    print("")
    if result["anomalies"]:
        for anomaly in result["anomalies"]:
            print(f"- **{anomaly['severity'].upper()}**: {anomaly['message']}")
    else:
        print("未发现异常")


def main():
    parser = argparse.ArgumentParser(description="L4 Domain 历史趋势分析")
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="分析天数",
    )
    parser.add_argument(
        "--output",
        choices=["text", "json", "markdown"],
        default="text",
        help="输出格式",
    )
    args = parser.parse_args()

    # 加载历史数据
    history = load_health_history(args.days)

    # 分析趋势
    result = analyze_trends(history)

    # 输出结果
    if args.output == "text":
        output_text(result)
    elif args.output == "json":
        output_json(result)
    elif args.output == "markdown":
        output_markdown(result)

    # 返回退出码
    if result["anomalies"]:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
