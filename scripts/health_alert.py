#!/usr/bin/env python3
"""L4 Domain 健康告警脚本。

当健康检查失败时，自动发送告警通知。

使用方式:
    python scripts/health_alert.py
    python scripts/health_alert.py --channel slack
    python scripts/health_alert.py --channel email
    python scripts/health_alert.py --channel wechat
    python scripts/health_alert.py --level info
    python scripts/health_alert.py --level warning
    python scripts/health_alert.py --level error
    python scripts/health_alert.py --level critical
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# 添加 src 到 path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# 告警级别定义
ALERT_LEVELS = {
    "info": {
        "name": "信息",
        "color": "#3498db",
        "channels": ["slack"],
        "priority": 1,
    },
    "warning": {
        "name": "警告",
        "color": "#f39c12",
        "channels": ["slack", "email"],
        "priority": 2,
    },
    "error": {
        "name": "错误",
        "color": "#e74c3c",
        "channels": ["slack", "email", "wechat"],
        "priority": 3,
    },
    "critical": {
        "name": "严重",
        "color": "#c0392b",
        "channels": ["slack", "email", "wechat"],
        "priority": 4,
    },
}

# 告警规则
ALERT_RULES = [
    {
        "name": "健康率下降",
        "condition": lambda data: data["health_rate"] != "100.0%",
        "level": "error",
        "message": "健康率下降到 {health_rate}",
    },
    {
        "name": "信号数量异常",
        "condition": lambda data: any(d["signal_count"] > 100 for d in data["domains"]),
        "level": "warning",
        "message": "检测到信号数量异常",
    },
    {
        "name": "域不健康",
        "condition": lambda data: any(not d["fresh"] for d in data["domains"]),
        "level": "error",
        "message": "检测到不健康的域",
    },
    {
        "name": "多个域不健康",
        "condition": lambda data: sum(1 for d in data["domains"] if not d["fresh"]) >= 3,
        "level": "critical",
        "message": "多个域不健康，可能存在系统性问题",
    },
    {
        "name": "KEMS 面不完整",
        "condition": lambda data: any(not d["has_state"] or not d["has_status"] for d in data["domains"]),
        "level": "warning",
        "message": "检测到 KEMS 面配置不完整",
    },
]


def send_slack_alert(message: str, level: str = "warning") -> bool:
    """发送 Slack 告警。"""
    import os

    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("警告: SLACK_WEBHOOK_URL 环境变量未设置")
        return False

    try:
        import urllib.request

        level_info = ALERT_LEVELS.get(level, ALERT_LEVELS["warning"])
        payload = {
            "text": f"[{level_info['name']}] L4 Domain Health Alert",
            "attachments": [
                {
                    "color": level_info["color"],
                    "text": message,
                    "ts": int(datetime.now(UTC).timestamp()),
                }
            ],
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status == 200
    except Exception as e:
        print(f"发送 Slack 告警失败: {e}")
        return False


def send_email_alert(message: str, level: str = "warning") -> bool:
    """发送邮件告警。"""
    import os
    import smtplib
    from email.mime.text import MIMEText

    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    alert_email = os.environ.get("ALERT_EMAIL")

    if not all([smtp_host, smtp_user, smtp_pass, alert_email]):
        print("警告: 邮件配置环境变量未设置")
        return False

    try:
        level_info = ALERT_LEVELS.get(level, ALERT_LEVELS["warning"])
        msg = MIMEText(message)
        msg["Subject"] = f"[{level_info['name']}] L4 Domain Health Alert"
        msg["From"] = smtp_user
        msg["To"] = alert_email

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        return True
    except Exception as e:
        print(f"发送邮件告警失败: {e}")
        return False


def send_wechat_alert(message: str, level: str = "warning") -> bool:
    """发送企业微信告警。"""
    import os
    import urllib.request

    webhook_url = os.environ.get("WECHAT_WEBHOOK_URL")
    if not webhook_url:
        print("警告: WECHAT_WEBHOOK_URL 环境变量未设置")
        return False

    try:
        level_info = ALERT_LEVELS.get(level, ALERT_LEVELS["warning"])
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": f"## [{level_info['name']}] L4 Domain Health Alert\n\n{message}"
            },
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status == 200
    except Exception as e:
        print(f"发送企业微信告警失败: {e}")
        return False


def send_alert(message: str, level: str = "warning", channel: str = "all") -> bool:
    """发送告警通知。"""
    channels = {
        "slack": send_slack_alert,
        "email": send_email_alert,
        "wechat": send_wechat_alert,
    }

    level_info = ALERT_LEVELS.get(level, ALERT_LEVELS["warning"])

    if channel == "all":
        # 根据告警级别选择渠道
        target_channels = level_info["channels"]
        results = []
        for name in target_channels:
            func = channels.get(name)
            if func:
                result = func(message, level)
                results.append((name, result))
                if result:
                    print(f"  ✅ {name} 告警发送成功")
                else:
                    print(f"  ⚠️ {name} 告警发送失败")
        return any(r for _, r in results)
    else:
        func = channels.get(channel)
        if func:
            return func(message, level)
        else:
            print(f"未知的告警渠道: {channel}")
            return False


def run_health_check() -> dict:
    """运行健康检查。"""
    script_dir = Path(__file__).parent
    result = subprocess.run(
        [sys.executable, str(script_dir / "health_monitor.py"), "--output", "json"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        return json.loads(result.stdout)
    else:
        print(f"健康检查失败: {result.stderr}")
        return None


def run_trend_analysis() -> dict:
    """运行趋势分析。"""
    script_dir = Path(__file__).parent
    result = subprocess.run(
        [sys.executable, str(script_dir / "health_trend.py"), "--days", "7", "--output", "json"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        return json.loads(result.stdout)
    else:
        print(f"趋势分析失败: {result.stderr}")
        return None


def run_signal_analysis() -> dict:
    """运行信号分析。"""
    script_dir = Path(__file__).parent
    result = subprocess.run(
        [sys.executable, str(script_dir / "signal_analysis.py"), "--hours", "72", "--output", "json"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        return json.loads(result.stdout)
    else:
        print(f"信号分析失败: {result.stderr}")
        return None


def evaluate_rules(health_data: dict, trend_data: dict, signal_data: dict) -> list[dict]:
    """评估告警规则。"""
    triggered = []

    for rule in ALERT_RULES:
        try:
            if rule["condition"](health_data):
                triggered.append({
                    "name": rule["name"],
                    "level": rule["level"],
                    "message": rule["message"].format(**health_data),
                })
        except Exception as e:
            print(f"评估规则 {rule['name']} 失败: {e}")
            continue

    # 检查趋势异常
    if trend_data and trend_data.get("anomalies"):
        for anomaly in trend_data["anomalies"]:
            triggered.append({
                "name": "趋势异常",
                "level": anomaly.get("severity", "warning"),
                "message": anomaly.get("message", "检测到趋势异常"),
            })

    # 检查信号风险
    if signal_data and signal_data.get("risks"):
        for risk in signal_data["risks"]:
            triggered.append({
                "name": "信号风险",
                "level": risk.get("severity", "warning"),
                "message": risk.get("message", "检测到信号风险"),
            })

    return triggered


def main():
    parser = argparse.ArgumentParser(description="L4 Domain 健康告警")
    parser.add_argument(
        "--channel",
        choices=["all", "slack", "email", "wechat"],
        default="all",
        help="告警渠道",
    )
    parser.add_argument(
        "--level",
        choices=["info", "warning", "error", "critical"],
        default=None,
        help="强制指定告警级别",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="模拟运行，不发送告警",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("L4 Domain 健康告警检查")
    print("=" * 80)

    # 运行健康检查
    print("\n运行健康检查...")
    health_data = run_health_check()

    if health_data is None:
        print("❌ 健康检查失败")
        sys.exit(1)

    # 运行趋势分析
    print("运行趋势分析...")
    trend_data = run_trend_analysis()

    # 运行信号分析
    print("运行信号分析...")
    signal_data = run_signal_analysis()

    # 评估告警规则
    print("\n评估告警规则...")
    triggered_rules = evaluate_rules(health_data, trend_data, signal_data)

    if not triggered_rules:
        print(f"\n✅ 所有 {health_data['total_domains']} 个域健康状态正常")
        sys.exit(0)

    # 确定最高告警级别
    if args.level:
        max_level = args.level
    else:
        max_priority = max(ALERT_LEVELS[r["level"]]["priority"] for r in triggered_rules)
        max_level = next(
            level for level, info in ALERT_LEVELS.items()
            if info["priority"] == max_priority
        )

    level_info = ALERT_LEVELS[max_level]

    # 构建告警消息
    print(f"\n⚠️ 触发 {len(triggered_rules)} 条告警规则:")
    message = f"触发 {len(triggered_rules)} 条告警规则:\n\n"

    for rule in triggered_rules:
        rule_level = ALERT_LEVELS.get(rule["level"], ALERT_LEVELS["warning"])
        print(f"  [{rule_level['name']}] {rule['name']}: {rule['message']}")
        message += f"- **{rule['name']}** [{rule_level['name']}]: {rule['message']}\n"

    message += f"\n健康率: {health_data['health_rate']}"
    message += f"\n检查时间: {health_data['timestamp']}"

    # 发送告警
    if args.dry_run:
        print("\n[DRY RUN] 模拟运行，不发送告警")
        print(f"告警级别: {level_info['name']}")
        print(f"告警渠道: {', '.join(level_info['channels'])}")
        print(f"告警消息:\n{message}")
    else:
        print(f"\n发送告警 (级别: {level_info['name']}, 渠道: {args.channel})...")
        success = send_alert(message, max_level, args.channel)

        if success:
            print("✅ 告警发送成功")
        else:
            print("❌ 告警发送失败")

    sys.exit(1)


if __name__ == "__main__":
    main()
