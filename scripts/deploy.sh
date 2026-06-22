#!/bin/bash
# =============================================================
# 网安合规助手 - 一键部署脚本
# 在 Ubuntu 服务器上以 root 或 sudo 用户运行
# 用法: bash scripts/deploy.sh
# =============================================================

set -euo pipefail

PROJECT_DIR="/opt/cybersec-compliance"
VENV_DIR="$PROJECT_DIR/.venv"
SERVICE_NAME="cybersec-compliance"
PG_CONTAINER="cybersec-postgres"
PG_PASSWORD="postgres_admin_2024"   # 可修改
DB_NAME="cybersec_compliance"
DB_USER="compliance_user"
DB_PASSWORD="compliance_pass_2024"  # 可修改

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

info "============================================"
info "  网安合规助手 - 部署开始"
info "============================================"

# ---- Step 1: 系统依赖 ----
info "Step 1: 安装系统依赖..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv \
    libpq-dev python3-dev curl wget git build-essential

# ---- Step 2: Docker ----
info "Step 2: 确认 Docker..."
if ! command -v docker &>/dev/null; then
    info "安装 Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    usermod -aG docker ubuntu 2>/dev/null || true
    info "✅ Docker 安装完成"
else
    info "✅ Docker 已存在: $(docker --version)"
fi

# ---- Step 3: 启动 PostgreSQL ----
info "Step 3: 启动 PostgreSQL 容器..."
if docker ps -a --format '{{.Names}}' | grep -q "^${PG_CONTAINER}$"; then
    warn "PostgreSQL 容器已存在，跳过创建"
    docker start "$PG_CONTAINER" 2>/dev/null || true
else
    docker run -d \
        --name "$PG_CONTAINER" \
        --restart unless-stopped \
        -e POSTGRES_PASSWORD="$PG_PASSWORD" \
        -p 5432:5432 \
        -v cybersec_pgdata:/var/lib/postgresql/data \
        ankane/pgvector:latest
    info "等待 PostgreSQL 启动..."
    sleep 8
fi

# 验证 PG 连通性
docker exec "$PG_CONTAINER" pg_isready -U postgres || error "PostgreSQL 未就绪"
info "✅ PostgreSQL 运行正常"

# ---- Step 4: 创建 DB 用户 ----
info "Step 4: 创建数据库用户和数据库..."
docker exec "$PG_CONTAINER" psql -U postgres -c \
    "DO \$\$ BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='${DB_USER}') THEN
            CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';
        END IF;
    END \$\$;" 2>/dev/null || true

docker exec "$PG_CONTAINER" psql -U postgres -c \
    "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1 || \
    docker exec "$PG_CONTAINER" psql -U postgres -c \
    "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER} ENCODING 'UTF8';"

docker exec "$PG_CONTAINER" psql -U postgres -c \
    "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};"

info "✅ 数据库初始化完成"

# ---- Step 5: Python 虚拟环境 ----
info "Step 5: 创建 Python 虚拟环境..."
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    info "✅ 虚拟环境创建完成"
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q
pip install -r requirements.txt -q
info "✅ Python 依赖安装完成"

# ---- Step 6: 环境变量配置 ----
info "Step 6: 配置环境变量..."
if [ ! -f "config/.env" ]; then
    cp config/.env.example config/.env
    # 自动填入数据库配置
    sed -i "s/DB_PASSWORD=your_strong_password_here/DB_PASSWORD=${DB_PASSWORD}/" config/.env
    sed -i "s/DB_USER=compliance_user/DB_USER=${DB_USER}/" config/.env
    sed -i "s/DB_NAME=cybersec_compliance/DB_NAME=${DB_NAME}/" config/.env
    warn "⚠️  config/.env 已创建，请编辑填入 API Key:"
    warn "    nano /opt/cybersec-compliance/config/.env"
else
    info "✅ config/.env 已存在"
fi

# ---- Step 7: 数据库 Schema + 种子数据 ----
info "Step 7: 初始化数据库 Schema..."
# 直接通过 Docker exec 执行 SQL
docker cp database/migrations/V1__init_schema.sql "$PG_CONTAINER":/tmp/
docker exec "$PG_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" \
    -f /tmp/V1__init_schema.sql

docker cp database/seeds/V2__seed_data.sql "$PG_CONTAINER":/tmp/
docker exec "$PG_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" \
    -f /tmp/V2__seed_data.sql

info "✅ 数据库 Schema + 种子数据完成"

# ---- Step 8: Systemd 服务 ----
info "Step 8: 配置 systemd 服务..."
cp scripts/cybersec-compliance.service /etc/systemd/system/
# 替换用户名
CURRENT_USER=$(logname 2>/dev/null || echo "ubuntu")
sed -i "s/User=ubuntu/User=${CURRENT_USER}/" /etc/systemd/system/cybersec-compliance.service
sed -i "s/Group=ubuntu/Group=${CURRENT_USER}/" /etc/systemd/system/cybersec-compliance.service

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
info "✅ systemd 服务已注册（未启动，等配置 API Key 后再启动）"

# ---- 完成 ----
info ""
info "============================================"
info "  🎉 部署完成！"
info "============================================"
info ""
info "下一步操作："
info "  1. 填入数据库、COS、AI 网关和飞书配置:"
info "     nano /opt/cybersec-compliance/config/.env"
info "     （至少填写数据库、COS、AI_BASE_URL/AI_API_KEY、FEISHU_WEBHOOK_URL 等）"
info ""
info "  2. 启动调度器和后台:"
info "     cd /opt/cybersec-compliance"
info "     source .venv/bin/activate"
info "     systemctl start cybersec-compliance"
info "     systemctl start cybersec-admin"
info ""
info "  3. 进入后台 Tasks 页面触发“每周完整更新”:"
info "     http://<server-ip>:8080/"
info ""
info "  4. 查看调度器日志:"
info "     journalctl -u cybersec-compliance -f"
info ""
info "注意：旧 scripts/run_full_update.py / scripts/ai_verify.py 已从正式链路移除，"
info "      不要用 AI 联网结果直接写入正式知识库。"
info ""
