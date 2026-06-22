-- V22__jurisdiction_inheritance.sql
-- Market-level inheritance. EU regulations stay stored under EU, while EU member
-- markets can display/query them as inherited applicable requirements.

CREATE TABLE IF NOT EXISTS jurisdiction_inheritance (
    parent_code         VARCHAR(10) NOT NULL REFERENCES countries(code) ON UPDATE CASCADE,
    child_code          VARCHAR(10) NOT NULL REFERENCES countries(code) ON UPDATE CASCADE,
    relation_type       VARCHAR(40) NOT NULL DEFAULT 'member_state',
    reason              TEXT NOT NULL,
    effective_from      DATE,
    effective_to        DATE,
    enabled             BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (parent_code, child_code, relation_type)
);

CREATE INDEX IF NOT EXISTS idx_jurisdiction_inheritance_child
    ON jurisdiction_inheritance(child_code, enabled);

INSERT INTO countries (code, name_zh, name_en, region, priority) VALUES
    ('AT', '奥地利', 'Austria', '欧洲', 'P3'),
    ('BE', '比利时', 'Belgium', '欧洲', 'P3'),
    ('BG', '保加利亚', 'Bulgaria', '欧洲', 'P3'),
    ('HR', '克罗地亚', 'Croatia', '欧洲', 'P3'),
    ('CY', '塞浦路斯', 'Cyprus', '欧洲', 'P3'),
    ('CZ', '捷克', 'Czechia', '欧洲', 'P3'),
    ('DK', '丹麦', 'Denmark', '欧洲', 'P3'),
    ('EE', '爱沙尼亚', 'Estonia', '欧洲', 'P3'),
    ('FI', '芬兰', 'Finland', '欧洲', 'P3'),
    ('FR', '法国', 'France', '欧洲', 'P3'),
    ('DE', '德国', 'Germany', '欧洲', 'P3'),
    ('GR', '希腊', 'Greece', '欧洲', 'P3'),
    ('HU', '匈牙利', 'Hungary', '欧洲', 'P3'),
    ('IE', '爱尔兰', 'Ireland', '欧洲', 'P3'),
    ('IT', '意大利', 'Italy', '欧洲', 'P3'),
    ('LV', '拉脱维亚', 'Latvia', '欧洲', 'P3'),
    ('LT', '立陶宛', 'Lithuania', '欧洲', 'P3'),
    ('LU', '卢森堡', 'Luxembourg', '欧洲', 'P3'),
    ('MT', '马耳他', 'Malta', '欧洲', 'P3'),
    ('NL', '荷兰', 'Netherlands', '欧洲', 'P3'),
    ('PL', '波兰', 'Poland', '欧洲', 'P3'),
    ('PT', '葡萄牙', 'Portugal', '欧洲', 'P3'),
    ('RO', '罗马尼亚', 'Romania', '欧洲', 'P3'),
    ('SK', '斯洛伐克', 'Slovakia', '欧洲', 'P3'),
    ('SI', '斯洛文尼亚', 'Slovenia', '欧洲', 'P3'),
    ('ES', '西班牙', 'Spain', '欧洲', 'P3'),
    ('SE', '瑞典', 'Sweden', '欧洲', 'P3')
ON CONFLICT (code) DO NOTHING;

INSERT INTO jurisdiction_inheritance (
    parent_code,
    child_code,
    relation_type,
    reason,
    effective_from,
    enabled
)
VALUES
    ('EU', 'AT', 'member_state', 'Austria is an EU Member State; EU-level cybersecurity product regulations apply to the Austrian market.', '1995-01-01', TRUE),
    ('EU', 'BE', 'member_state', 'Belgium is an EU Member State; EU-level cybersecurity product regulations apply to the Belgian market.', '1958-01-01', TRUE),
    ('EU', 'BG', 'member_state', 'Bulgaria is an EU Member State; EU-level cybersecurity product regulations apply to the Bulgarian market.', '2007-01-01', TRUE),
    ('EU', 'HR', 'member_state', 'Croatia is an EU Member State; EU-level cybersecurity product regulations apply to the Croatian market.', '2013-07-01', TRUE),
    ('EU', 'CY', 'member_state', 'Cyprus is an EU Member State; EU-level cybersecurity product regulations apply to the Cypriot market.', '2004-05-01', TRUE),
    ('EU', 'CZ', 'member_state', 'Czechia is an EU Member State; EU-level cybersecurity product regulations apply to the Czech market.', '2004-05-01', TRUE),
    ('EU', 'DK', 'member_state', 'Denmark is an EU Member State; EU-level cybersecurity product regulations apply to the Danish market.', '1973-01-01', TRUE),
    ('EU', 'EE', 'member_state', 'Estonia is an EU Member State; EU-level cybersecurity product regulations apply to the Estonian market.', '2004-05-01', TRUE),
    ('EU', 'FI', 'member_state', 'Finland is an EU Member State; EU-level cybersecurity product regulations apply to the Finnish market.', '1995-01-01', TRUE),
    ('EU', 'FR', 'member_state', 'France is an EU Member State; EU-level cybersecurity product regulations apply to the French market.', '1958-01-01', TRUE),
    ('EU', 'DE', 'member_state', 'Germany is an EU Member State; EU-level cybersecurity product regulations apply to the German market.', '1958-01-01', TRUE),
    ('EU', 'GR', 'member_state', 'Greece is an EU Member State; EU-level cybersecurity product regulations apply to the Greek market.', '1981-01-01', TRUE),
    ('EU', 'HU', 'member_state', 'Hungary is an EU Member State; EU-level cybersecurity product regulations apply to the Hungarian market.', '2004-05-01', TRUE),
    ('EU', 'IE', 'member_state', 'Ireland is an EU Member State; EU-level cybersecurity product regulations apply to the Irish market.', '1973-01-01', TRUE),
    ('EU', 'IT', 'member_state', 'Italy is an EU Member State; EU-level cybersecurity product regulations apply to the Italian market.', '1958-01-01', TRUE),
    ('EU', 'LV', 'member_state', 'Latvia is an EU Member State; EU-level cybersecurity product regulations apply to the Latvian market.', '2004-05-01', TRUE),
    ('EU', 'LT', 'member_state', 'Lithuania is an EU Member State; EU-level cybersecurity product regulations apply to the Lithuanian market.', '2004-05-01', TRUE),
    ('EU', 'LU', 'member_state', 'Luxembourg is an EU Member State; EU-level cybersecurity product regulations apply to the Luxembourg market.', '1958-01-01', TRUE),
    ('EU', 'MT', 'member_state', 'Malta is an EU Member State; EU-level cybersecurity product regulations apply to the Maltese market.', '2004-05-01', TRUE),
    ('EU', 'NL', 'member_state', 'Netherlands is an EU Member State; EU-level cybersecurity product regulations apply to the Dutch market.', '1958-01-01', TRUE),
    ('EU', 'PL', 'member_state', 'Poland is an EU Member State; EU-level cybersecurity product regulations apply to the Polish market.', '2004-05-01', TRUE),
    ('EU', 'PT', 'member_state', 'Portugal is an EU Member State; EU-level cybersecurity product regulations apply to the Portuguese market.', '1986-01-01', TRUE),
    ('EU', 'RO', 'member_state', 'Romania is an EU Member State; EU-level cybersecurity product regulations apply to the Romanian market.', '2007-01-01', TRUE),
    ('EU', 'SK', 'member_state', 'Slovakia is an EU Member State; EU-level cybersecurity product regulations apply to the Slovak market.', '2004-05-01', TRUE),
    ('EU', 'SI', 'member_state', 'Slovenia is an EU Member State; EU-level cybersecurity product regulations apply to the Slovenian market.', '2004-05-01', TRUE),
    ('EU', 'ES', 'member_state', 'Spain is an EU Member State; EU-level cybersecurity product regulations apply to the Spanish market.', '1986-01-01', TRUE),
    ('EU', 'SE', 'member_state', 'Sweden is an EU Member State; EU-level cybersecurity product regulations apply to the Swedish market.', '1995-01-01', TRUE)
ON CONFLICT (parent_code, child_code, relation_type) DO UPDATE SET
    reason = EXCLUDED.reason,
    effective_from = EXCLUDED.effective_from,
    effective_to = EXCLUDED.effective_to,
    enabled = EXCLUDED.enabled,
    updated_at = NOW();
