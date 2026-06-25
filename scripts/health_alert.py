#!/usr/bin/env python3
"""L4 Domain 健康告警脚本。

当健康检查失败时，自动发送告警通知。

使用方式:
    python scripts/health_alert.py
    python scripts/health_alert.py --channel slack
    python scripts/health_alert.py --channel email
    python scripts/health_alert.py --channel wechat
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


def send_slack_alert(message: str, level: str = "warning") -> bool:
    """发送 Slack 告警。"""
    import os

    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("警告: SLACK_WEBHOOK_URL 环境变量未设置")
        return False

    try:
        import urllib.request

        payload = {
            "text": f"[{level.upper()}] L4 Domain Health Alert",
            "attachments": [
                {
                    "color": "danger" if level == "error" else "warning",
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
        msg = MIMEText(message)
        msg["Subject"] = f"[{level.upper()}] L4 Domain Health Alert"
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
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": f"## [{level.upper()}] L4 Domain Health Alert\n\n{message}"
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

    if channel == "all":
        results = []
        for name, func in channels.items():
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


def main():
    parser = argparse.ArgumentParser(description="L4 Domain 健康告警")
    parser.add_argument(
        "--channel",
        choices=["all", "slack", "email", "wechat"],
        default="all",
        help="告警渠道",
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
    data = run_health_check()

    if data is None:
        print("❌ 健康检查失败")
        sys.exit(1)

    # 检查不健康的域
    unhealthy = [d for d in data["domains"] if not d["fresh"]]

    if not unhealthy:
        print(f"\n✅ 所有 {data['total_domains']} 个域健康状态正常")
        sys.exit(0)

    # 构建告警消息
    print(f"\n⚠️ 发现 {len(unhealthy)} 个不健康的域:")
    message = f"发现 {len(unhealthy)} 个不健康的域:\n\n"

    for d in unhealthy:
        print(f"  - {d['id']}: {d['issue_count']} 个问题")
        message += f"- **{d['id']}** ({d['name']}): {d['issue_count']} 个问题\n"
        for issue in d["issues"]:
            print(f"    - {issue['level']} {issue['message']}")
            message += f"  - {issue['level']} {issue['message']}\n"

    message += f"\n健康率: {data['health_rate']}"
    message += f"\n检查时间: {data['timestamp']}"

    # 发送告警
    if args.dry_run:
        print("\n[DRY RUN] 模拟运行，不发送告警")
        print(f"告警消息:\n{message}")
    else:
        print(f"\n发送告警到 {args.channel} 渠道...")
        success = send_alert(message, "error", args.channel)

        if success:
            print("✅ 告警发送成功")
        else:
            print("❌ 告警发送失败")

    sys.exit(1)


if __name__ == "__main__":
    main()
