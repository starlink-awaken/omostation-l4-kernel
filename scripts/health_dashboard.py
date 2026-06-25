#!/usr/bin/env python3
"""L4 Domain 健康 Dashboard。

提供 Web 界面展示域健康状态。

使用方式:
    python scripts/health_dashboard.py
    python scripts/health_dashboard.py --port 8080
    python scripts/health_dashboard.py --host 0.0.0.0 --port 8080
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

try:
    from flask import Flask, jsonify, render_template_string
except ImportError:
    print("错误: 请安装 Flask: pip install flask")
    sys.exit(1)

app = Flask(__name__)

# HTML 模板
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>L4 Domain 健康 Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background-color: #f5f5f5;
            color: #333;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        h1 {
            text-align: center;
            margin-bottom: 30px;
            color: #2c3e50;
        }
        .summary {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .summary-card {
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            text-align: center;
        }
        .summary-card h3 {
            font-size: 14px;
            color: #666;
            margin-bottom: 10px;
        }
        .summary-card .value {
            font-size: 36px;
            font-weight: bold;
            color: #2c3e50;
        }
        .summary-card .value.healthy {
            color: #27ae60;
        }
        .summary-card .value.unhealthy {
            color: #e74c3c;
        }
        .domains {
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .domains h2 {
            margin-bottom: 20px;
            color: #2c3e50;
        }
        .domain-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 15px;
        }
        .domain-card {
            border: 1px solid #e0e0e0;
            border-radius: 6px;
            padding: 15px;
            transition: all 0.3s ease;
        }
        .domain-card:hover {
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }
        .domain-card.healthy {
            border-left: 4px solid #27ae60;
        }
        .domain-card.unhealthy {
            border-left: 4px solid #e74c3c;
        }
        .domain-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .domain-name {
            font-weight: bold;
            font-size: 16px;
        }
        .domain-status {
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
        }
        .domain-status.healthy {
            background-color: #d4edda;
            color: #155724;
        }
        .domain-status.unhealthy {
            background-color: #f8d7da;
            color: #721c24;
        }
        .domain-details {
            font-size: 14px;
            color: #666;
        }
        .domain-details .detail {
            margin-bottom: 5px;
        }
        .domain-details .label {
            font-weight: bold;
            color: #333;
        }
        .refresh-btn {
            display: block;
            margin: 20px auto;
            padding: 10px 20px;
            background-color: #3498db;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
        }
        .refresh-btn:hover {
            background-color: #2980b9;
        }
        .timestamp {
            text-align: center;
            color: #666;
            font-size: 14px;
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>L4 Domain 健康 Dashboard</h1>

        <div class="summary">
            <div class="summary-card">
                <h3>总域数</h3>
                <div class="value" id="total-domains">-</div>
            </div>
            <div class="summary-card">
                <h3>健康域数</h3>
                <div class="value healthy" id="healthy-domains">-</div>
            </div>
            <div class="summary-card">
                <h3>不健康域数</h3>
                <div class="value unhealthy" id="unhealthy-domains">-</div>
            </div>
            <div class="summary-card">
                <h3>健康率</h3>
                <div class="value" id="health-rate">-</div>
            </div>
        </div>

        <div class="domains">
            <h2>域健康状态</h2>
            <div class="domain-grid" id="domain-grid">
                <!-- 域卡片将通过 JavaScript 动态生成 -->
            </div>
        </div>

        <button class="refresh-btn" onclick="refreshData()">刷新数据</button>

        <div class="timestamp">
            最后更新时间: <span id="last-update">-</span>
        </div>
    </div>

    <script>
        function refreshData() {
            fetch('/api/health')
                .then(response => response.json())
                .then(data => {
                    updateSummary(data);
                    updateDomainGrid(data);
                    document.getElementById('last-update').textContent = data.timestamp;
                })
                .catch(error => {
                    console.error('Error fetching data:', error);
                });
        }

        function updateSummary(data) {
            document.getElementById('total-domains').textContent = data.total_domains;
            document.getElementById('healthy-domains').textContent = data.healthy_count;
            document.getElementById('unhealthy-domains').textContent = data.unhealthy_count;
            document.getElementById('health-rate').textContent = data.health_rate;
        }

        function updateDomainGrid(data) {
            const grid = document.getElementById('domain-grid');
            grid.innerHTML = '';

            data.domains.forEach(domain => {
                const card = document.createElement('div');
                card.className = `domain-card ${domain.fresh ? 'healthy' : 'unhealthy'}`;

                const statusClass = domain.fresh ? 'healthy' : 'unhealthy';
                const statusText = domain.fresh ? '健康' : '不健康';

                card.innerHTML = `
                    <div class="domain-header">
                        <span class="domain-name">${domain.id}</span>
                        <span class="domain-status ${statusClass}">${statusText}</span>
                    </div>
                    <div class="domain-details">
                        <div class="detail"><span class="label">名称:</span> ${domain.name}</div>
                        <div class="detail"><span class="label">问题数:</span> ${domain.issue_count}</div>
                        <div class="detail"><span class="label">信号数:</span> ${domain.signal_count}</div>
                        <div class="detail"><span class="label">Capabilities:</span> ${domain.capabilities.length}</div>
                    </div>
                `;

                grid.appendChild(card);
            });
        }

        // 页面加载时刷新数据
        refreshData();

        // 每 30 秒自动刷新
        setInterval(refreshData, 30000);
    </script>
</body>
</html>
"""


def get_health_data() -> dict:
    """获取健康数据。"""
    script_dir = Path(__file__).parent
    result = subprocess.run(
        [sys.executable, str(script_dir / "health_monitor.py"), "--output", "json"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        return json.loads(result.stdout)
    else:
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "total_domains": 0,
            "document_domains": 0,
            "domains": [],
            "healthy_count": 0,
            "unhealthy_count": 0,
            "health_rate": "N/A",
        }


@app.route("/")
def index():
    """Dashboard 首页。"""
    return render_template_string(DASHBOARD_HTML)


@app.route("/api/health")
def health():
    """健康数据 API。"""
    data = get_health_data()
    return jsonify(data)


@app.route("/api/domains")
def domains():
    """域列表 API。"""
    data = get_health_data()
    return jsonify(data["domains"])


@app.route("/api/domains/<domain_id>")
def domain(domain_id: str):
    """单个域详情 API。"""
    data = get_health_data()
    for d in data["domains"]:
        if d["id"] == domain_id:
            return jsonify(d)
    return jsonify({"error": "Domain not found"}), 404


def main():
    parser = argparse.ArgumentParser(description="L4 Domain 健康 Dashboard")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="监听地址",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="监听端口",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="调试模式",
    )
    args = parser.parse_args()

    print("启动 L4 Domain 健康 Dashboard...")
    print(f"访问地址: http://{args.host}:{args.port}")
    print(f"API 地址: http://{args.host}:{args.port}/api/health")

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
