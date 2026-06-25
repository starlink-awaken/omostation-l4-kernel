#!/bin/bash
# L4 Domain 健康监控定时任务脚本
#
# 使用方式:
#   1. 添加到 crontab: crontab -e
#   2. 添加以下行（每天凌晨 2 点运行）:
#      0 2 * * * /Users/xiamingxing/Workspace/projects/l4-kernel/scripts/health_cron.sh
#
# 或者手动运行:
#   ./scripts/health_cron.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
REPORT_DIR="$LOG_DIR/reports"
LOG_FILE="$LOG_DIR/health_$(date +%Y%m%d_%H%M%S).log"
HEALTH_REPORT="$REPORT_DIR/health_report_$(date +%Y%m%d_%H%M%S).json"
TREND_REPORT="$REPORT_DIR/trend_report_$(date +%Y%m%d_%H%M%S).json"
SIGNAL_REPORT="$REPORT_DIR/signal_report_$(date +%Y%m%d_%H%M%S).json"

# 创建日志和报告目录
mkdir -p "$LOG_DIR" "$REPORT_DIR"

echo "========================================" | tee -a "$LOG_FILE"
echo "L4 Domain 健康监控 - $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

cd "$PROJECT_DIR"

# 1. 运行健康监控脚本
echo "" | tee -a "$LOG_FILE"
echo "## 1. 健康检查" | tee -a "$LOG_FILE"
python3 scripts/health_monitor.py --output json > "$HEALTH_REPORT" 2>&1
HEALTH_EXIT=$?

if [ $HEALTH_EXIT -eq 0 ]; then
    echo "✅ 健康检查通过" | tee -a "$LOG_FILE"
else
    echo "⚠️ 健康检查发现问题" | tee -a "$LOG_FILE"
fi

# 2. 运行历史趋势分析
echo "" | tee -a "$LOG_FILE"
echo "## 2. 历史趋势分析" | tee -a "$LOG_FILE"
python3 scripts/health_trend.py --days 7 --output json > "$TREND_REPORT" 2>&1
TREND_EXIT=$?

if [ $TREND_EXIT -eq 0 ]; then
    echo "✅ 趋势分析正常" | tee -a "$LOG_FILE"
else
    echo "⚠️ 趋势分析发现异常" | tee -a "$LOG_FILE"
fi

# 3. 运行跨域信号分析
echo "" | tee -a "$LOG_FILE"
echo "## 3. 跨域信号分析" | tee -a "$LOG_FILE"
python3 scripts/signal_analysis.py --hours 72 --output json > "$SIGNAL_REPORT" 2>&1
SIGNAL_EXIT=$?

if [ $SIGNAL_EXIT -eq 0 ]; then
    echo "✅ 信号分析正常" | tee -a "$LOG_FILE"
else
    echo "⚠️ 信号分析发现风险" | tee -a "$LOG_FILE"
fi

# 4. 生成综合报告
echo "" | tee -a "$LOG_FILE"
echo "## 4. 综合报告" | tee -a "$LOG_FILE"

# 提取关键指标
HEALTH_RATE=$(python3 -c "import json; data=json.load(open('$HEALTH_REPORT')); print(data['health_rate'])" 2>/dev/null || echo "N/A")
TOTAL_SIGNALS=$(python3 -c "import json; data=json.load(open('$SIGNAL_REPORT')); print(data['total_signals'])" 2>/dev/null || echo "N/A")
ANOMALIES=$(python3 -c "import json; data=json.load(open('$TREND_REPORT')); print(len(data['anomalies']))" 2>/dev/null || echo "N/A")
RISKS=$(python3 -c "import json; data=json.load(open('$SIGNAL_REPORT')); print(len(data['risks']))" 2>/dev/null || echo "N/A")

echo "  健康率: $HEALTH_RATE" | tee -a "$LOG_FILE"
echo "  信号数: $TOTAL_SIGNALS" | tee -a "$LOG_FILE"
echo "  趋势异常: $ANOMALIES" | tee -a "$LOG_FILE"
echo "  风险数: $RISKS" | tee -a "$LOG_FILE"

# 5. 发送告警（如果有问题）
echo "" | tee -a "$LOG_FILE"
echo "## 5. 告警检查" | tee -a "$LOG_FILE"

if [ $HEALTH_EXIT -ne 0 ] || [ $TREND_EXIT -ne 0 ] || [ $SIGNAL_EXIT -ne 0 ]; then
    echo "⚠️ 发现问题，发送告警..." | tee -a "$LOG_FILE"
    python3 scripts/health_alert.py --channel all 2>&1 | tee -a "$LOG_FILE"
else
    echo "✅ 所有检查通过，无需告警" | tee -a "$LOG_FILE"
fi

# 输出报告摘要
echo "" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
echo "报告文件:" | tee -a "$LOG_FILE"
echo "  健康报告: $HEALTH_REPORT" | tee -a "$LOG_FILE"
echo "  趋势报告: $TREND_REPORT" | tee -a "$LOG_FILE"
echo "  信号报告: $SIGNAL_REPORT" | tee -a "$LOG_FILE"
echo "  日志文件: $LOG_FILE" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# 清理超过 30 天的日志和报告
find "$LOG_DIR" -name "health_*.log" -mtime +30 -delete 2>/dev/null || true
find "$REPORT_DIR" -name "*.json" -mtime +30 -delete 2>/dev/null || true

# 返回综合退出码
if [ $HEALTH_EXIT -ne 0 ] || [ $TREND_EXIT -ne 0 ] || [ $SIGNAL_EXIT -ne 0 ]; then
    exit 1
else
    exit 0
fi
