#!/bin/bash
set -euo pipefail

echo "已停用：verify_remaining.sh 属于旧 AI 联网核实批处理。"
echo "剩余 candidate/suspicious 应通过 review_cases、manual-source 和官方工件闭环处理。"
echo "请使用后台 Reviews/Tasks 页面，或运行官方源同步与工件抓取任务。"
exit 2
