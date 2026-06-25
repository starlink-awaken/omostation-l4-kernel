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
LOG_FILE="$LOG_DIR/health_$(date +%Y%m%d_%H%M%S).log"
REPORT_FILE="$LOG_DIR/health_report_$(date +%Y%m%d_%H%M%S).json"

# 创建日志目录
mkdir -p "$LOG_DIR"

echo "========================================" | tee -a "$LOG_FILE"
echo "L4 Domain 健康监控 - $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# 运行健康监控脚本
cd "$PROJECT_DIR"
python3 scripts/health_monitor.py --output json > "$REPORT_FILE" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ 健康检查通过" | tee -a "$LOG_FILE"
else
    echo "⚠️ 健康检查发现问题" | tee -a "$LOG_FILE"
fi

# 输出报告摘要
echo "" | tee -a "$LOG_FILE"
echo "报告文件: $REPORT_FILE" | tee -a "$LOG_FILE"
echo "日志文件: $LOG_FILE" | tee -a "$LOG_FILE"

# 清理超过 30 天的日志
find "$LOG_DIR" -name "health_*.log" -mtime +30 -delete 2>/dev/null || true
find "$LOG_DIR" -name "health_report_*.json" -mtime +30 -delete 2>/dev/null || true

exit $EXIT_CODE
