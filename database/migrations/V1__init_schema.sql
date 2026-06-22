-- ============================================================
-- 网安合规助手 - 数据库初始化迁移脚本
-- 版本: V1
-- 说明: 完整建表 + 索引 + 约束 + 注释
-- 执行: psql -U compliance_user -d cybersec_compliance -f V1__init_schema.sql
-- ============================================================

-- 启用扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- 模糊搜索
CREATE EXTENSION IF NOT EXISTS "vector";    -- pgvector，语义检索（后期）

-- ============================================================
-- 枚举类型
-- ============================================================

DO $$ BEGIN
    CREATE TYPE entry_type_enum AS ENUM ('regulation', 'standard', 'certification');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE mandatory_enum AS ENUM ('mandatory', 'voluntary', 'recommended');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE status_enum AS ENUM ('active', 'deprecated', 'draft', 'superseded');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE priority_enum AS ENUM ('P1', 'P2', 'P3');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE change_type_enum AS ENUM ('created', 'updated', 'deprecated', 'restored');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE product_category_enum AS ENUM (
        'enterprise_router',
        'home_router',
        'switch',
        'firewall_utm',
        'wireless_ap',
        'industrial_gateway',
        'sd_wan',
        'security_gateway',
        'cloud_desktop',
        'software',
        'other'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ============================================================
-- 国家/地区表
-- ============================================================
CREATE TABLE IF NOT EXISTS countries (
    id              SERIAL PRIMARY KEY,
    code            VARCHAR(10)  NOT NULL UNIQUE,   -- ISO 3166-1 alpha-2，如 CN、US、EU
    name_zh         VARCHAR(100) NOT NULL,
    name_en         VARCHAR(100) NOT NULL,
    region          VARCHAR(50)  NOT NULL,           -- 地区：欧洲、亚太、美洲等
    priority        priority_enum NOT NULL DEFAULT 'P3',
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  countries         IS '国家/地区配置表';
COMMENT ON COLUMN countries.code    IS 'ISO 3166-1 alpha-2 国家代码，欧盟用 EU';
COMMENT ON COLUMN countries.priority IS 'P1:每日检查 P2:每周检查 P3:每月检查';

-- ============================================================
-- 产品表
-- ============================================================
CREATE TABLE IF NOT EXISTS products (
    id              SERIAL PRIMARY KEY,
    code            VARCHAR(50)  NOT NULL UNIQUE,   -- 内部标识，如 enterprise_router
    name_zh         VARCHAR(100) NOT NULL,
    name_en         VARCHAR(100) NOT NULL,
    category        product_category_enum NOT NULL,
    description     TEXT,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE products IS '产品类型表，支持动态增删';

-- ============================================================
-- 合规知识库主表
-- ============================================================
CREATE TABLE IF NOT EXISTS compliance_knowledge (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- 基础信息
    name                VARCHAR(500) NOT NULL,               -- 认证/法规名称
    name_local          VARCHAR(500),                        -- 本地语言名称
    entry_type          entry_type_enum NOT NULL,            -- regulation/standard/certification
    mandatory           mandatory_enum NOT NULL DEFAULT 'mandatory',
    status              status_enum NOT NULL DEFAULT 'active',

    -- 地理范围
    country_code        VARCHAR(10) NOT NULL,                -- 对应 countries.code
    region_scope        TEXT,                                -- 适用地区说明

    -- 认证机构与标准
    issuing_body        VARCHAR(200),                        -- 认证机构
    technical_standards TEXT[],                              -- 引用技术标准，数组
    regulation_basis    TEXT[],                              -- 所依据法规，数组（认证层填此字段）

    -- 时间信息
    effective_date      DATE,                                -- 强制生效日期
    transition_end_date DATE,                                -- 过渡期截止日期
    validity_period     VARCHAR(100),                        -- 有效期描述，如"3年"
    published_date      DATE,                                -- 发布日期

    -- 适用范围
    applicable_products TEXT[],                              -- 适用产品类型，数组
    scope_description   TEXT,                                -- 适用范围描述

    -- 要求详情
    requirements        JSONB,                               -- 具体要求（结构化）
    testing_bodies      TEXT[],                              -- 测试机构，数组
    assessment_procedure TEXT,                               -- 符合性评估流程

    -- 参考资料
    official_url        TEXT,                                -- 官方链接
    official_url_backup TEXT,                                -- 备用链接
    remarks             TEXT,                                -- 备注

    -- 数据质量
    data_source         VARCHAR(100),                        -- 数据来源（模型名/人工）
    verified            BOOLEAN NOT NULL DEFAULT FALSE,      -- 是否人工核实
    confidence_score    SMALLINT CHECK (confidence_score BETWEEN 0 AND 100),

    -- 向量检索（后期启用）
    -- embedding        vector(1536),

    -- 版本控制
    version             INTEGER NOT NULL DEFAULT 1,
    last_checked        TIMESTAMPTZ,                         -- 上次检查时间
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 约束
    CONSTRAINT fk_country FOREIGN KEY (country_code)
        REFERENCES countries(code) ON UPDATE CASCADE
);

COMMENT ON TABLE  compliance_knowledge               IS '合规知识库主表';
COMMENT ON COLUMN compliance_knowledge.entry_type    IS 'regulation:法规 standard:标准 certification:认证';
COMMENT ON COLUMN compliance_knowledge.regulation_basis IS '认证条目所依据的法规名称列表';
COMMENT ON COLUMN compliance_knowledge.requirements  IS '具体技术要求，JSONB结构化存储';
COMMENT ON COLUMN compliance_knowledge.confidence_score IS 'AI生成数据置信度 0-100';

-- 主表索引
CREATE INDEX IF NOT EXISTS idx_ck_country      ON compliance_knowledge(country_code);
CREATE INDEX IF NOT EXISTS idx_ck_entry_type   ON compliance_knowledge(entry_type);
CREATE INDEX IF NOT EXISTS idx_ck_status       ON compliance_knowledge(status);
CREATE INDEX IF NOT EXISTS idx_ck_mandatory    ON compliance_knowledge(mandatory);
CREATE INDEX IF NOT EXISTS idx_ck_effective    ON compliance_knowledge(effective_date);
CREATE INDEX IF NOT EXISTS idx_ck_verified     ON compliance_knowledge(verified);
CREATE INDEX IF NOT EXISTS idx_ck_last_checked ON compliance_knowledge(last_checked);
CREATE INDEX IF NOT EXISTS idx_ck_products     ON compliance_knowledge USING GIN(applicable_products);
CREATE INDEX IF NOT EXISTS idx_ck_name_trgm    ON compliance_knowledge USING GIN(name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_ck_requirements ON compliance_knowledge USING GIN(requirements);
CREATE INDEX IF NOT EXISTS idx_ck_updated      ON compliance_knowledge(updated_at DESC);

-- ============================================================
-- 知识库条目 ↔ 产品 多对多关联表
-- ============================================================
CREATE TABLE IF NOT EXISTS compliance_products (
    compliance_id   UUID NOT NULL REFERENCES compliance_knowledge(id) ON DELETE CASCADE,
    product_id      INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (compliance_id, product_id)
);

CREATE INDEX IF NOT EXISTS idx_cp_product ON compliance_products(product_id);

-- ============================================================
-- 变更日志表
-- ============================================================
CREATE TABLE IF NOT EXISTS change_log (
    id              BIGSERIAL PRIMARY KEY,
    record_id       UUID NOT NULL REFERENCES compliance_knowledge(id) ON DELETE CASCADE,
    change_type     change_type_enum NOT NULL,
    changed_fields  TEXT[],                                  -- 变更字段列表
    old_value       JSONB,                                   -- 变更前快照
    new_value       JSONB,                                   -- 变更后快照
    diff_summary    TEXT,                                    -- 人可读差异摘要
    data_source     VARCHAR(100),                            -- 触发更新的数据源
    reviewed        BOOLEAN NOT NULL DEFAULT FALSE,          -- 是否已人工审核
    reviewed_by     VARCHAR(100),
    reviewed_at     TIMESTAMPTZ,
    changed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE change_log IS '合规数据变更日志，保留完整历史';
COMMENT ON COLUMN change_log.old_value IS '变更前完整记录快照（JSONB）';

CREATE INDEX IF NOT EXISTS idx_cl_record    ON change_log(record_id);
CREATE INDEX IF NOT EXISTS idx_cl_type      ON change_log(change_type);
CREATE INDEX IF NOT EXISTS idx_cl_changed   ON change_log(changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_cl_reviewed  ON change_log(reviewed) WHERE reviewed = FALSE;

-- ============================================================
-- 预警规则表
-- ============================================================
CREATE TABLE IF NOT EXISTS alert_rules (
    id                  SERIAL PRIMARY KEY,
    name                VARCHAR(200) NOT NULL,
    rule_type           VARCHAR(50) NOT NULL,    -- effective_date / new_regulation / amendment / deprecated
    days_before         INTEGER,                 -- 提前N天预警（effective_date类型使用）
    priority_filter     priority_enum[],         -- 只对哪些优先级国家生效，NULL=全部
    entry_type_filter   entry_type_enum[],       -- 只对哪些条目类型生效，NULL=全部
    notification_channel VARCHAR(50) NOT NULL DEFAULT 'feishu',
    enabled             BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 默认预警规则
INSERT INTO alert_rules (name, rule_type, days_before, notification_channel) VALUES
    ('生效前30天预警', 'effective_date', 30, 'feishu'),
    ('生效前7天预警',  'effective_date', 7,  'feishu'),
    ('当天生效通知',   'effective_date', 0,  'feishu'),
    ('新法规发布通知', 'new_regulation', NULL, 'feishu'),
    ('法规修订通知',   'amendment',      NULL, 'feishu'),
    ('法规废止通知',   'deprecated',     NULL, 'feishu')
ON CONFLICT DO NOTHING;

-- ============================================================
-- 预警发送记录表（去重，防止重复发送）
-- ============================================================
CREATE TABLE IF NOT EXISTS alert_sent_log (
    id              BIGSERIAL PRIMARY KEY,
    rule_id         INTEGER NOT NULL REFERENCES alert_rules(id),
    record_id       UUID NOT NULL REFERENCES compliance_knowledge(id) ON DELETE CASCADE,
    sent_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    channel         VARCHAR(50) NOT NULL DEFAULT 'feishu',
    success         BOOLEAN NOT NULL DEFAULT TRUE,
    error_msg       TEXT,
    UNIQUE (rule_id, record_id, sent_at::DATE)   -- 同一天同一条目同一规则不重复发
);

CREATE INDEX IF NOT EXISTS idx_asl_record ON alert_sent_log(record_id);
CREATE INDEX IF NOT EXISTS idx_asl_sent   ON alert_sent_log(sent_at DESC);

-- ============================================================
-- API 配置表（动态切换，不改代码）
-- ============================================================
CREATE TABLE IF NOT EXISTS api_configs (
    id              SERIAL PRIMARY KEY,
    provider        VARCHAR(50) NOT NULL,        -- volcengine / dashscope / deepseek
    model           VARCHAR(100) NOT NULL,
    api_key_encrypted TEXT NOT NULL,             -- 加密存储
    base_url        TEXT NOT NULL,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    priority        INTEGER NOT NULL DEFAULT 1,  -- 数字越小越优先
    max_retries     INTEGER NOT NULL DEFAULT 3,
    timeout_seconds INTEGER NOT NULL DEFAULT 120,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE api_configs IS 'AI Provider API配置，支持动态切换，key加密存储';

-- ============================================================
-- 更新任务记录表
-- ============================================================
CREATE TABLE IF NOT EXISTS update_tasks (
    id              BIGSERIAL PRIMARY KEY,
    task_type       VARCHAR(50) NOT NULL,        -- full_update / incremental / manual
    status          VARCHAR(20) NOT NULL DEFAULT 'running',  -- running/success/failed/partial
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    total_records   INTEGER DEFAULT 0,
    processed       INTEGER DEFAULT 0,
    created_count   INTEGER DEFAULT 0,
    updated_count   INTEGER DEFAULT 0,
    error_count     INTEGER DEFAULT 0,
    error_details   JSONB,
    triggered_by    VARCHAR(100) DEFAULT 'scheduler',  -- scheduler / manual / api
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_ut_status  ON update_tasks(status);
CREATE INDEX IF NOT EXISTS idx_ut_started ON update_tasks(started_at DESC);

-- ============================================================
-- 报告记录表
-- ============================================================
CREATE TABLE IF NOT EXISTS report_records (
    id              BIGSERIAL PRIMARY KEY,
    report_type     VARCHAR(50) NOT NULL,        -- weekly / monthly / adhoc
    report_date     DATE NOT NULL,
    file_name       VARCHAR(500),
    cos_url         TEXT,
    feishu_sent     BOOLEAN NOT NULL DEFAULT FALSE,
    feishu_sent_at  TIMESTAMPTZ,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    stats           JSONB                         -- 报告统计数据快照
);

CREATE INDEX IF NOT EXISTS idx_rr_type ON report_records(report_type, report_date DESC);

-- ============================================================
-- 自动更新 updated_at 触发器
-- ============================================================
CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$ DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['countries','products','compliance_knowledge','api_configs'] LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS set_updated_at ON %I;
             CREATE TRIGGER set_updated_at
             BEFORE UPDATE ON %I
             FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();',
            t, t
        );
    END LOOP;
END $$;

-- ============================================================
-- 视图：即将生效的法规（30天内）
-- ============================================================
CREATE OR REPLACE VIEW v_upcoming_effective AS
SELECT
    ck.id,
    ck.name,
    ck.entry_type,
    ck.country_code,
    c.name_zh AS country_name,
    c.priority,
    ck.effective_date,
    ck.effective_date - CURRENT_DATE AS days_until_effective,
    ck.mandatory,
    ck.applicable_products
FROM compliance_knowledge ck
JOIN countries c ON ck.country_code = c.code
WHERE ck.status = 'active'
  AND ck.effective_date IS NOT NULL
  AND ck.effective_date >= CURRENT_DATE
  AND ck.effective_date <= CURRENT_DATE + INTERVAL '30 days'
ORDER BY ck.effective_date;

-- ============================================================
-- 视图：未审核的重大变更
-- ============================================================
CREATE OR REPLACE VIEW v_pending_review AS
SELECT
    cl.id AS log_id,
    cl.record_id,
    ck.name,
    ck.country_code,
    c.name_zh AS country_name,
    cl.change_type,
    cl.changed_fields,
    cl.diff_summary,
    cl.changed_at
FROM change_log cl
JOIN compliance_knowledge ck ON cl.record_id = ck.id
JOIN countries c ON ck.country_code = c.code
WHERE cl.reviewed = FALSE
ORDER BY cl.changed_at DESC;

-- ============================================================
-- 完成提示
-- ============================================================
DO $$ BEGIN
    RAISE NOTICE '✅ 数据库初始化完成！';
    RAISE NOTICE '   表: countries, products, compliance_knowledge';
    RAISE NOTICE '   表: compliance_products, change_log, alert_rules';
    RAISE NOTICE '   表: alert_sent_log, api_configs, update_tasks, report_records';
    RAISE NOTICE '   视图: v_upcoming_effective, v_pending_review';
END $$;
