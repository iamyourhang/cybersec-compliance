-- V19__compliance_index_regime_category.sql
-- Split verified records into product-level regimes and general cybersecurity laws.

ALTER TABLE compliance_index
    ADD COLUMN IF NOT EXISTS regime_category VARCHAR(40) NOT NULL DEFAULT 'general_cyber_law';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_compliance_index_regime_category'
    ) THEN
        ALTER TABLE compliance_index
            ADD CONSTRAINT ck_compliance_index_regime_category
            CHECK (regime_category IN ('product_regime', 'general_cyber_law'));
    END IF;
END $$;

UPDATE compliance_index
SET regime_category = CASE
    WHEN entry_type = 'certification' THEN 'product_regime'
    WHEN lower(
        COALESCE(name, '') || ' ' ||
        COALESCE(summary, '') || ' ' ||
        COALESCE(issuing_body, '')
    ) ~ (
        'certification|scheme|label|labeling|trust mark|common criteria|protection profile|' ||
        'niap|cspn|cyber essentials|cyber fundamentals|qcvn|jc-star|jc star|' ||
        'technical regulation|conformity|approval|product security|secure[- ]by[- ]design|' ||
        'iot|internet of things|connectable product|network equipment|network device|' ||
        'router|switch|firewall|gateway|wireless ap|cryptographic module|crypto module|' ||
        '认证|检测|测评|标签|标识|计划|方案|目录|清单|网络关键设备|网络安全专用产品|' ||
        '专用网络安全产品|商用密码产品|密码产品|关键信息基础设施产品|联网产品|' ||
        '物联网|智能设备|网络设备|路由器|交换机|网关|防火墙|安全产品'
    ) THEN 'product_regime'
    ELSE 'general_cyber_law'
END;

CREATE INDEX IF NOT EXISTS idx_compliance_index_regime_category
    ON compliance_index(authenticity_status, regime_category, country_code);
