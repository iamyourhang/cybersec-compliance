#!/bin/bash
# backup.sh - 一键备份网安合规助手
# 用法: bash backup.sh [备份目录]

set -e
BACKUP_DIR=${1:-/opt/backups/cybersec-$(date +%Y%m%d-%H%M%S)}
PROJECT=/opt/cybersec-compliance

echo "🚀 开始备份到: $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"

# 1. 备份数据库
echo "📦 备份数据库..."
docker exec cybersec-postgres pg_dump \
    -U compliance_user cybersec_compliance \
    > "$BACKUP_DIR/database.sql"
echo "  ✅ 数据库: $(wc -l < $BACKUP_DIR/database.sql) 行"

# 2. 备份配置文件
echo "📦 备份配置..."
cp "$PROJECT/config/.env" "$BACKUP_DIR/.env"
echo "  ✅ .env 配置"

# 3. 备份代码（排除虚拟环境、node_modules、缓存）
echo "📦 备份代码..."
tar -czf "$BACKUP_DIR/code.tar.gz" \
    --exclude='.venv' \
    --exclude='node_modules' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='dist' \
    --exclude='logs/*.log' \
    -C /opt cybersec-compliance
echo "  ✅ 代码: $(du -sh $BACKUP_DIR/code.tar.gz | cut -f1)"

# 4. 备份 systemd 服务文件
echo "📦 备份服务配置..."
mkdir -p "$BACKUP_DIR/systemd"
for svc in cybersec-compliance cybersec-admin cybersec-feishu-bot cybersec-postgres; do
    [ -f "/etc/systemd/system/$svc.service" ] && \
        cp "/etc/systemd/system/$svc.service" "$BACKUP_DIR/systemd/"
done
echo "  ✅ systemd 服务文件"

# 5. 生成备份清单
VERIFIED_RECORDS=$(docker exec cybersec-postgres psql -U compliance_user -d cybersec_compliance -At -c "SELECT CASE WHEN to_regclass('public.compliance_index') IS NULL THEN 0 ELSE (SELECT COUNT(*) FROM compliance_index WHERE authenticity_status='verified') END" | tr -d ' ')
VERIFIED_COUNTRIES=$(docker exec cybersec-postgres psql -U compliance_user -d cybersec_compliance -At -c "SELECT CASE WHEN to_regclass('public.compliance_index') IS NULL THEN 0 ELSE (SELECT COUNT(DISTINCT country_code) FROM compliance_index WHERE authenticity_status='verified') END" | tr -d ' ')

cat > "$BACKUP_DIR/README.md" << EOF
# 网安合规助手备份
- 备份时间: $(date '+%Y-%m-%d %H:%M:%S')
- verified 正式记录: $VERIFIED_RECORDS
- verified 覆盖国家: $VERIFIED_COUNTRIES

## 恢复方法
bash restore.sh $BACKUP_DIR
EOF

echo ""
echo "✅ 备份完成: $BACKUP_DIR"
echo "   总大小: $(du -sh $BACKUP_DIR | cut -f1)"
