#!/bin/bash
# restore.sh - 一键恢复网安合规助手到新环境
# 用法: bash restore.sh <备份目录>

set -e
BACKUP_DIR=$1
if [ -z "$BACKUP_DIR" ]; then
    echo "用法: bash restore.sh <备份目录>"
    exit 1
fi

echo "🚀 开始从 $BACKUP_DIR 恢复..."

# 1. 安装基础依赖
echo "📦 检查依赖..."
apt-get install -y docker.io python3-pip python3-venv nodejs npm 2>/dev/null || true

# 2. 恢复代码
echo "📦 恢复代码..."
tar -xzf "$BACKUP_DIR/code.tar.gz" -C /opt/
echo "  ✅ 代码恢复"

# 3. 恢复配置
echo "📦 恢复配置..."
cp "$BACKUP_DIR/.env" /opt/cybersec-compliance/config/.env
echo "  ✅ 配置恢复（请检查 .env 中的 IP/域名是否需要更新）"

# 4. 重建 Python 虚拟环境
echo "📦 重建 Python 环境..."
cd /opt/cybersec-compliance
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -q
echo "  ✅ Python 环境"

# 5. 重建前端
echo "📦 重建前端..."
cd /opt/cybersec-compliance/admin/frontend-vue
npm install -q
npm run build
echo "  ✅ 前端构建"

# 6. 启动数据库
echo "📦 启动数据库..."
docker run -d --name cybersec-postgres \
    -e POSTGRES_USER=compliance_user \
    -e POSTGRES_PASSWORD=compliance_pass_2024 \
    -e POSTGRES_DB=cybersec_compliance \
    -p 5433:5432 \
    --restart unless-stopped \
    postgres:15 2>/dev/null || echo "  数据库容器已存在"
sleep 5

# 7. 恢复数据库
echo "📦 恢复数据库..."
docker exec -i cybersec-postgres psql \
    -U compliance_user cybersec_compliance \
    < "$BACKUP_DIR/database.sql"
echo "  ✅ 数据库恢复"

# 8. 恢复 systemd 服务
echo "📦 恢复服务..."
cp "$BACKUP_DIR/systemd/"*.service /etc/systemd/system/ 2>/dev/null || true
systemctl daemon-reload
for svc in cybersec-postgres cybersec-compliance cybersec-admin cybersec-feishu-bot; do
    systemctl enable "$svc" 2>/dev/null || true
    systemctl start "$svc" 2>/dev/null || true
done
echo "  ✅ 服务启动"

echo ""
echo "✅ 恢复完成！"
echo "   管理后台: http://$(hostname -I | awk '{print $1}'):8080"
echo "   ⚠️  请检查 .env 中的以下配置是否需要更新："
echo "      - ADMIN_IP_WHITELIST"
echo "      - FEISHU_WEBHOOK_URL"
echo "      - COS 配置"
