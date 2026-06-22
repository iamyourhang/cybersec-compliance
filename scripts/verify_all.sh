#!/bin/bash
set -euo pipefail

echo "已停用：verify_all.sh 属于旧 AI 联网核实批处理。"
echo "正式库真实性只能通过官方源、source_artifacts、review_cases 和人工/规则审核闭环写入。"
echo "请使用后台 Reviews/Tasks 页面，或运行官方源同步与工件抓取任务。"
exit 2
